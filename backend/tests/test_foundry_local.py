"""Local setup must not open a browser, register versions, or enable AI implicitly."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys

from azure.identity import AuthenticationRecord, CredentialUnavailableError
import pytest

from app.core.config import Settings
from app.modules.foundry import auth, setup
from app.modules.foundry.local import validate_project, write_env

ENDPOINT = "https://example.services.ai.azure.com/api/projects/test"


def config(**kwargs):
    return Settings(_env_file=None, foundry_project_endpoint=ENDPOINT, **kwargs)


def test_default_credential_keeps_browser_disabled(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(auth, "DefaultAzureCredential", factory)
    assert auth.credential(config()) == factory.return_value
    factory.assert_called_once_with(exclude_interactive_browser_credential=True)


def test_browser_requires_explicit_login_before_backend_can_use_it(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    factory = MagicMock()
    monkeypatch.setattr(auth, "InteractiveBrowserCredential", factory)
    with pytest.raises(CredentialUnavailableError, match="setup --login"):
        auth.credential(config(foundry_auth_mode="browser"))
    factory.assert_not_called()


def test_login_persists_only_account_metadata_and_runtime_reuses_encrypted_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    record = AuthenticationRecord(authority="login.microsoftonline.com", client_id="sdk-client",
                                  home_account_id="home-account", tenant_id="corporate-tenant",
                                  username="qa@example.invalid")
    factory = MagicMock()
    identity = factory.return_value.__enter__.return_value
    identity.authenticate.return_value = record
    monkeypatch.setattr(auth, "InteractiveBrowserCredential", factory)
    settings = config(foundry_auth_mode="browser")
    auth.login(settings)
    identity.authenticate.assert_called_once_with(scopes=[auth.FOUNDRY_SCOPE])
    stored = auth._record_path(settings).read_text()
    assert "access_token" not in stored and "refresh_token" not in stored
    auth.credential(settings)
    options = factory.call_args.kwargs
    assert options["disable_automatic_authentication"] is True
    assert options["tenant_id"] == "corporate-tenant"
    assert options["authentication_record"].username == record.username
    assert options["cache_persistence_options"].allow_unencrypted_storage is False
    assert options["cache_persistence_options"].name.startswith("datastage-foundry-")
    assert auth._record_path(config(foundry_auth_mode="browser", foundry_tenant_id="another")) != auth._record_path(settings)


def test_browser_never_allowed_in_production():
    with pytest.raises(ValueError, match="identidad de servicio"):
        config(environment="production", foundry_auth_mode="browser")
    # The factory also protects callers that bypass Settings validation.
    with pytest.raises(ValueError, match="producción"):
        auth.credential(SimpleNamespace(foundry_auth_mode="browser", environment="production"))


def test_development_client_requires_registered_loopback_redirect(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(ValueError, match="localhost"):
        auth.credential(config(foundry_auth_mode="browser", foundry_client_id="client",
                               foundry_redirect_uri="https://example.invalid/callback"), interactive=True)


def test_env_update_preserves_other_configuration_and_backs_up_before_overwriting(tmp_path):
    path = tmp_path / ".env"
    original = b'# Corporate settings\r\nDATASTAGE_DATABASE_URL="private-value"\r\nDATASTAGE_FOUNDRY_MODEL=old\r\nDATASTAGE_FOUNDRY_MODEL=duplicate\r\n'
    path.write_bytes(original)
    updates = {"DATASTAGE_FOUNDRY_MODEL": "deployment-pilot", "DATASTAGE_FOUNDRY_ENABLED": "false"}
    assert write_env(path, updates) is True
    assert b'DATASTAGE_DATABASE_URL="private-value"\r\n' in path.read_bytes()
    assert path.read_text().count("DATASTAGE_FOUNDRY_MODEL=") == 1
    assert next((tmp_path / ".data/foundry-config-backups").glob("*.bak")).read_bytes() == original
    assert write_env(path, updates) is False
    assert len(list((tmp_path / ".data/foundry-config-backups").glob("*.bak"))) == 1
    assert Settings(_env_file=path).foundry_model == "deployment-pilot"


def test_prepare_local_is_offline_and_leaves_ai_and_write_tools_disabled(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    factory = MagicMock()
    monkeypatch.setattr(setup, "AIProjectClient", factory)
    monkeypatch.setattr(sys, "argv", ["setup", "--configure-local", "--project-endpoint", ENDPOINT,
                                     "--model", "exact-deployment-name"])
    setup.main()
    settings = Settings()
    assert settings.foundry_model == "exact-deployment-name"
    assert settings.foundry_auth_mode == "browser"
    assert settings.foundry_enabled is False and settings.allow_agent_commands is False
    assert settings.foundry_project_endpoint == ENDPOINT
    factory.assert_not_called()


def test_activation_saves_actual_returned_version_and_failed_registration_never_enables(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    write_env(Path(".env"), {"DATASTAGE_FOUNDRY_ENABLED": "false", "DATASTAGE_FOUNDRY_PROJECT_ENDPOINT": ENDPOINT})
    register = MagicMock(side_effect=RuntimeError("access denied"))
    monkeypatch.setattr(setup, "register_agent", register)
    monkeypatch.setattr(sys, "argv", ["setup", "--apply", "--save-env"])
    with pytest.raises(RuntimeError, match="access denied"):
        setup.main()
    assert Settings().foundry_enabled is False
    register.side_effect = None
    register.return_value = {"name": "datastage-assistant", "version": "7"}
    setup.main()
    assert Settings().foundry_agent_version == "7" and Settings().foundry_enabled is True


def test_check_reads_configured_version_without_creating_one(monkeypatch):
    project = MagicMock()
    project.agents.get_version.return_value = SimpleNamespace(name="qa", version="7")
    factory = MagicMock()
    factory.return_value.__enter__.return_value = project
    monkeypatch.setattr(setup, "AIProjectClient", factory)
    monkeypatch.setattr(setup, "credential", MagicMock())
    result = setup.check_agent(config(foundry_agent_name="qa", foundry_agent_version="7"))
    assert result == {"name": "qa", "version": "7"}
    project.agents.get_version.assert_called_once_with(agent_name="qa", agent_version="7")
    project.agents.create_version.assert_not_called()


def test_backend_reports_expired_login_without_starting_interactive_auth():
    from app.core.errors import ApplicationError
    from app.modules.foundry.agent import FoundryAgent
    factory = MagicMock(side_effect=CredentialUnavailableError("login required"))
    provider = FoundryAgent(config(foundry_enabled=True), client_factory=factory)
    with pytest.raises(ApplicationError) as error:
        provider.respond([{"role": "user", "content": "¿Qué meses están publicados?"}], MagicMock())
    assert error.value.code == "foundry_login_required"
    assert factory.call_count == 1


@pytest.mark.parametrize("endpoint", ["http://example/api/projects/p", ENDPOINT+"?key=secret", "https://example/models"])
def test_invalid_project_endpoint_fails_before_authentication(endpoint):
    with pytest.raises(ValueError, match="endpoint HTTPS"):
        validate_project(endpoint)
