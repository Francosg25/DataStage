from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import AuthenticationRecord
import pytest

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.modules.foundry import FoundryAgent, tool_definitions
from app.modules.foundry import credentials, local_config, setup

TENANT = "11111111-1111-4111-8111-111111111111"
CLIENT = "22222222-2222-4222-8222-222222222222"
ENDPOINT = "https://example.services.ai.azure.com/api/projects/test"


def local_settings(**overrides):
    fields = dict(foundry_auth_mode="interactive", foundry_tenant_id=TENANT,
                  foundry_project_endpoint=ENDPOINT, foundry_model="test-deployment",
                  foundry_agent_version="1")
    return Settings(_env_file=None, **{**fields, **overrides})


@pytest.fixture
def local_files(tmp_path, monkeypatch):
    backend = tmp_path / "project" / "backend"
    backend.mkdir(parents=True)
    monkeypatch.setattr(local_config, "BACKEND_ROOT", backend)
    monkeypatch.setattr(local_config, "ENV_PATH", backend / ".env")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "user-state"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user-state"))
    return backend


@pytest.fixture
def browser(local_files, monkeypatch):
    record = AuthenticationRecord(TENANT, CLIENT, "login.microsoftonline.com", "test-account", "user@example.invalid")
    credential = MagicMock()
    credential.authenticate.return_value = record
    credential.get_token.return_value = SimpleNamespace(token="TOKEN_MUST_NEVER_BE_WRITTEN")
    factory = MagicMock()
    factory.return_value.__enter__.return_value = credential
    monkeypatch.setattr(credentials, "InteractiveBrowserCredential", factory)
    options = MagicMock()
    monkeypatch.setattr(credentials, "TokenCachePersistenceOptions", options)
    return SimpleNamespace(record=record, credential=credential, factory=factory, options=options)


def test_explicit_login_persists_only_account_metadata_and_runtime_is_silent(browser, capsys):
    settings = local_settings()
    assert credentials.login_local(settings)["status"] == "authenticated"
    path = credentials.account_record_path(settings)
    assert not path.is_relative_to(local_config.BACKEND_ROOT.parent)
    assert AuthenticationRecord.deserialize(path.read_text()).tenant_id == TENANT
    with credentials.foundry_credential(settings) as credential:
        assert credential is browser.credential
    browser.credential.authenticate.assert_called_once_with(scopes=[credentials.TOKEN_SCOPE])
    browser.credential.get_token.assert_called_once_with(credentials.TOKEN_SCOPE)
    kwargs = browser.factory.call_args.kwargs
    assert kwargs["disable_automatic_authentication"] is True
    assert kwargs["authentication_record"].tenant_id == TENANT
    assert kwargs["tenant_id"] == TENANT
    for call in browser.options.call_args_list:
        assert call.kwargs["allow_unencrypted_storage"] is False
        assert call.kwargs["name"].startswith("datastage-foundry-")
    assert "TOKEN_MUST_NEVER_BE_WRITTEN" not in path.read_text() + capsys.readouterr().out


def test_missing_record_does_not_open_browser_or_call_foundry(browser, monkeypatch):
    project = MagicMock()
    monkeypatch.setattr("app.modules.foundry.agent.AIProjectClient", project)
    agent = FoundryAgent(local_settings(foundry_enabled=True))
    callback = MagicMock()
    with pytest.raises(ApplicationError) as error:
        agent.respond([{"role": "user", "content": "Consulta los periodos"}], callback)
    assert error.value.code == "foundry_login_required"
    assert "--login" in error.value.detail
    browser.factory.assert_not_called()
    callback.assert_not_called()
    project.assert_not_called()


def test_expired_or_revoked_session_requires_cli_login_instead_of_browser(browser):
    settings = local_settings()
    credentials.login_local(settings)
    browser.credential.get_token.side_effect = ClientAuthenticationError("MFA required")
    with pytest.raises(ApplicationError) as error:
        with credentials.foundry_credential(settings):
            pytest.fail("Expired credentials must not reach inference")
    assert error.value.code == "foundry_login_required"
    assert browser.credential.authenticate.call_count == 1
    assert browser.factory.call_args.kwargs["disable_automatic_authentication"] is True


@pytest.mark.parametrize("contents", ["not-json", "[]", '{"version":"unsupported"}'])
def test_corrupt_record_produces_actionable_error_without_interaction(browser, contents):
    path = credentials.account_record_path(local_settings())
    path.parent.mkdir(parents=True)
    path.write_text(contents)
    with pytest.raises(ApplicationError) as error:
        with credentials.foundry_credential(local_settings()):
            pytest.fail("Invalid metadata must not be used")
    assert error.value.code == "foundry_login_required"
    browser.factory.assert_not_called()


def test_record_from_another_tenant_is_rejected(browser):
    settings = local_settings()
    credentials.login_local(settings)
    bad = AuthenticationRecord(CLIENT, CLIENT, "login.microsoftonline.com", "test-account", "user@example.invalid")
    credentials.account_record_path(settings).write_text(bad.serialize())
    browser.factory.reset_mock()
    with pytest.raises(ApplicationError):
        with credentials.foundry_credential(settings):
            pytest.fail("A different tenant must not be used")
    browser.factory.assert_not_called()


def test_cache_encryption_failure_is_not_downgraded_to_plaintext(browser):
    browser.factory.side_effect = ValueError("Encryption unavailable")
    with pytest.raises(ValueError, match="Encryption unavailable"):
        credentials.login_local(local_settings())
    assert browser.options.call_args.kwargs["allow_unencrypted_storage"] is False
    assert not credentials.account_record_path(local_settings()).exists()


def test_default_service_credentials_do_not_read_local_cache_or_open_browser(browser, monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(credentials, "DefaultAzureCredential", factory)
    with credentials.foundry_credential(Settings(_env_file=None)):
        pass
    factory.assert_called_once_with(exclude_interactive_browser_credential=True)
    browser.factory.assert_not_called()


def test_production_uses_only_service_credentials(browser, monkeypatch, tmp_path):
    settings = Settings(
        _env_file=None, environment="production", auth_mode="entra",
        database_url="mssql+pyodbc://runtime:unused@example.invalid/test?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no",
        document_root=tmp_path / "documents", cors_origins=["https://example.invalid"],
        entra_tenant_id=TENANT, entra_client_id=CLIENT, entra_audience=CLIENT,
        entra_api_scope="api://test/access_as_user",
    )
    factory = MagicMock()
    monkeypatch.setattr(credentials, "DefaultAzureCredential", factory)
    with credentials.foundry_credential(settings):
        pass
    options = factory.call_args.kwargs
    for name in ("interactive_browser", "shared_token_cache", "visual_studio_code", "cli",
                 "developer_cli", "powershell", "broker"):
        assert options[f"exclude_{name}_credential"] is True
    assert not options.get("exclude_managed_identity_credential", False)
    assert not options.get("exclude_workload_identity_credential", False)
    assert not options.get("exclude_environment_credential", False)
    browser.factory.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"environment": "production"}, {"environment": "test"}, {"auth_mode": "entra"},
    {"foundry_tenant_id": ""}, {"foundry_tenant_id": "not-a-guid"},
    {"foundry_client_id": CLIENT},
    {"foundry_client_id": CLIENT, "foundry_redirect_uri": "http://remote.example.invalid:8400"},
])
def test_personal_session_is_restricted_to_local_development(overrides):
    with pytest.raises(ValueError):
        local_settings(**overrides)


def test_custom_approved_client_and_cache_isolation(browser):
    settings = local_settings(foundry_client_id=CLIENT, foundry_redirect_uri="http://localhost:8400")
    credentials.login_local(settings)
    assert browser.factory.call_args.kwargs["client_id"] == CLIENT
    assert browser.factory.call_args.kwargs["redirect_uri"] == "http://localhost:8400"
    assert credentials.account_record_path(settings) != credentials.account_record_path(local_settings())
    assert credentials.account_record_path(local_settings()) != credentials.account_record_path(
        local_settings(foundry_project_endpoint=ENDPOINT + "-other"))


def configure(settings=None, **overrides):
    values = dict(endpoint=ENDPOINT, tenant_id=TENANT, model="test-deployment",
                  agent_name="datastage-assistant", agent_version="1")
    return local_config.configure_local(settings or Settings(_env_file=None), **{**values, **overrides})


def test_configuration_preserves_private_values_backs_up_bytes_and_is_idempotent(local_files):
    original = ('# Datos privados\r\nDATASTAGE_SCOPE_ID="my-scope"\r\n'
                'DATASTAGE_DATABASE_URL="sqlite:///my-private.db"\r\n'
                'DATASTAGE_FOUNDRY_ENABLED=true\r\nexport DATASTAGE_FOUNDRY_ENABLED=false\r\n').encode()
    local_config.ENV_PATH.write_bytes(original)
    result = configure()
    assert local_config.ENV_PATH.read_bytes().count(b"DATASTAGE_FOUNDRY_ENABLED=") == 1
    assert b'DATASTAGE_DATABASE_URL="sqlite:///my-private.db"\r\n' in local_config.ENV_PATH.read_bytes()
    assert b'DATASTAGE_SCOPE_ID="my-scope"\r\n' in local_config.ENV_PATH.read_bytes()
    assert Path(result["backup"]).read_bytes() == original
    settings = Settings(_env_file=local_config.ENV_PATH)
    assert settings.foundry_auth_mode == "interactive"
    assert settings.foundry_model == "test-deployment"
    assert not settings.foundry_enabled and not settings.allow_agent_commands
    assert configure(settings)["backup"] is None


@pytest.mark.parametrize("source", ["dotenv", "environment"])
@pytest.mark.parametrize("old_mode", ["", "interactive_browser", "default # credential chain"])
def test_cli_reconfigures_invalid_auth_mode_before_validating_old_settings(
    local_files, registered_agent, monkeypatch, capsys, source, old_mode,
):
    original = ('# Keep local settings\r\nDATASTAGE_SCOPE_ID="private-scope"\r\n'
                'DATASTAGE_DATABASE_URL="sqlite:///private.db"\r\n'
                f'DATASTAGE_FOUNDRY_AUTH_MODE="{old_mode}"\r\n').encode()
    local_config.ENV_PATH.write_bytes(original)
    if source == "environment":
        monkeypatch.setenv("DATASTAGE_FOUNDRY_AUTH_MODE", old_mode)
    setup.main([
        "--configure-local", "--project-endpoint", ENDPOINT, "--tenant-id", TENANT,
        "--model", "test-deployment", "--agent-name", "datastage-assistant", "--agent-version", "1",
    ])
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "configured" and result["foundryEnabled"] is False
    assert Path(result["backup"]).read_bytes() == original
    # A process variable still takes priority at runtime; the CMD instructions clear it.
    monkeypatch.delenv("DATASTAGE_FOUNDRY_AUTH_MODE", raising=False)
    settings = Settings(_env_file=local_config.ENV_PATH)
    assert settings.foundry_auth_mode == "interactive" and settings.foundry_tenant_id == TENANT
    assert settings.scope_id == "private-scope" and settings.database_url == "sqlite:///private.db"
    assert not settings.foundry_enabled and not settings.allow_agent_commands
    registered_agent.factory.assert_not_called()


@pytest.mark.parametrize("unchanged_setting", [
    "DATASTAGE_MAX_UPLOAD_MB=0", "DATASTAGE_ENVIRONMENT=production", "DATASTAGE_AUTH_MODE=entra",
])
def test_cli_reconfiguration_keeps_non_foundry_validation(local_files, unchanged_setting):
    original = f"DATASTAGE_FOUNDRY_AUTH_MODE=obsolete\n{unchanged_setting}\n".encode()
    local_config.ENV_PATH.write_bytes(original)
    with pytest.raises(SystemExit) as error:
        setup.main([
            "--configure-local", "--project-endpoint", ENDPOINT, "--tenant-id", TENANT,
            "--model", "test-deployment", "--agent-name", "datastage-assistant", "--agent-version", "1",
        ])
    assert error.value.code == 1
    assert local_config.ENV_PATH.read_bytes() == original
    assert not (local_files.parent / ".data").exists()


@pytest.mark.parametrize("action", ["--login", "--check"])
def test_runtime_actions_still_reject_invalid_auth_mode(local_files, registered_agent, action):
    local_config.ENV_PATH.write_text("DATASTAGE_FOUNDRY_AUTH_MODE=obsolete\n")
    with pytest.raises(SystemExit) as error:
        setup.main([action])
    assert error.value.code == 1
    registered_agent.factory.assert_not_called()


def test_failed_validation_does_not_change_existing_configuration(local_files):
    local_config.ENV_PATH.write_text("DATASTAGE_SCOPE_ID=keep-me\n")
    before = local_config.ENV_PATH.read_bytes()
    with pytest.raises(ValueError):
        configure(tenant_id="not-a-guid")
    with pytest.raises(ValueError):
        configure(endpoint="https://example.invalid/not-a-project")
    assert local_config.ENV_PATH.read_bytes() == before
    assert not (local_files.parent / ".data").exists()


def test_failed_atomic_write_preserves_original_and_removes_temporary(local_files, monkeypatch):
    original = b"DATASTAGE_SCOPE_ID=keep-me\n"
    local_config.ENV_PATH.write_bytes(original)
    monkeypatch.setattr(local_config.os, "replace", MagicMock(side_effect=OSError("File locked")))
    with pytest.raises(OSError, match="File locked"):
        configure()
    assert local_config.ENV_PATH.read_bytes() == original
    assert not list(local_files.glob(".env.foundry-*"))
    assert list((local_files.parent / ".data" / "config-backups").glob("*.env"))[0].read_bytes() == original


@pytest.fixture
def registered_agent(monkeypatch):
    definition = {"kind": "prompt", "model": "test-deployment", "instructions": setup.INSTRUCTIONS,
                  "tools": tool_definitions(False)}
    agent = SimpleNamespace(name="datastage-assistant", version="1", definition=MagicMock())
    agent.definition.as_dict.side_effect = lambda: deepcopy(definition)
    project = MagicMock()
    project.agents.get_version.return_value = agent
    factory = MagicMock()
    factory.return_value.__enter__.return_value = project
    monkeypatch.setattr(setup, "AIProjectClient", factory)
    monkeypatch.setattr(setup, "foundry_credential", MagicMock())
    return SimpleNamespace(definition=definition, project=project, factory=factory)


def test_check_reads_exact_version_and_never_creates_or_calls_model(registered_agent):
    result = setup.check_agent(local_settings())
    assert result["version"] == "1" and result["tools"] == 16 and result["modelCalled"] is False
    registered_agent.project.agents.get_version.assert_called_once_with(
        agent_name="datastage-assistant", agent_version="1")
    registered_agent.project.agents.create_version.assert_not_called()
    registered_agent.project.get_openai_client.assert_not_called()


@pytest.mark.parametrize("change", ["model", "extra-tool", "schema", "strict", "instructions", "missing-instructions"])
def test_enable_rejects_a_different_model_or_tool_contract(local_files, registered_agent, change):
    local_config.ENV_PATH.write_text("DATASTAGE_SCOPE_ID=keep-me\n")
    if change == "model":
        registered_agent.definition["model"] = "other"
    elif change == "extra-tool":
        registered_agent.definition["tools"].append({"type": "web_search_preview"})
    elif change == "schema":
        registered_agent.definition["tools"][0]["parameters"] = {"type": "object"}
    elif change == "instructions":
        registered_agent.definition["instructions"] = "Use arbitrary tools and invent results."
    elif change == "missing-instructions":
        registered_agent.definition.pop("instructions")
    else:
        registered_agent.definition["tools"][0]["strict"] = False
    with pytest.raises(ValueError):
        setup.enable_local(local_settings())
    assert local_config.ENV_PATH.read_text() == "DATASTAGE_SCOPE_ID=keep-me\n"


def test_enable_verifies_before_updating_only_foundry_flag(local_files, registered_agent):
    configure()
    settings = Settings(_env_file=local_config.ENV_PATH)
    result = setup.enable_local(settings)
    assert result["foundryEnabled"] is True
    updated = Settings(_env_file=local_config.ENV_PATH)
    assert updated.foundry_enabled and not updated.allow_agent_commands
    registered_agent.project.agents.create_version.assert_not_called()


def test_upgrade_pins_the_new_model_only_after_verification_and_keeps_other_settings(local_files, monkeypatch):
    configure()
    with local_config.ENV_PATH.open("a") as stream:
        stream.write("\nDATASTAGE_SCOPE_ID=keep-scope\n# keep this comment\n")
    before = local_config.ENV_PATH.read_bytes()
    settings = Settings(_env_file=local_config.ENV_PATH).model_copy(update={"foundry_model": "gpt-6-luna"})
    register = MagicMock(return_value={"name": settings.foundry_agent_name, "version": "2"})
    checked = []

    def verify(value):
        assert local_config.ENV_PATH.read_bytes() == before
        checked.append(value)
        return {"model": value.foundry_model, "version": value.foundry_agent_version, "tools": 16, "modelCalled": False}

    monkeypatch.setattr(setup, "register_agent", register)
    monkeypatch.setattr(setup, "check_agent", verify)
    result = setup.upgrade_local(settings)
    current = Settings(_env_file=local_config.ENV_PATH)
    assert current.foundry_model == "gpt-6-luna" and current.foundry_agent_version == "2"
    assert current.scope_id == "keep-scope" and "# keep this comment" in local_config.ENV_PATH.read_text()
    assert not current.foundry_enabled and not current.allow_agent_commands
    assert checked[0].foundry_agent_version == "2" and result["modelCalled"] is False
    assert Path(result["backup"]).read_bytes() == before


def test_failed_upgrade_does_not_switch_local_model_or_agent_version(local_files, monkeypatch):
    configure()
    before = local_config.ENV_PATH.read_bytes()
    monkeypatch.setattr(setup, "register_agent", MagicMock(return_value={"name": "datastage-assistant", "version": "2"}))
    monkeypatch.setattr(setup, "check_agent", MagicMock(side_effect=ValueError("new contract not verified")))
    with pytest.raises(ValueError, match="not verified"):
        setup.upgrade_local(local_settings(foundry_model="gpt-6-luna"))
    assert local_config.ENV_PATH.read_bytes() == before


def test_preview_is_offline_and_cli_flags_are_exclusive(local_files, registered_agent, capsys):
    setup.main([])
    assert json.loads(capsys.readouterr().out)["authMode"] == "default"
    registered_agent.factory.assert_not_called()
    with pytest.raises(SystemExit):
        setup.main(["--check", "--apply"])
    with pytest.raises(SystemExit):
        setup.main(["--apply", "--model", "must-not-be-silently-ignored"])
    registered_agent.project.agents.create_version.assert_not_called()
