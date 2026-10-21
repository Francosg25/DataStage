"""Explicit browser login for local development; unattended credentials for services.

Tokens are stored only by Azure Identity's encrypted platform cache. The account
record is non-secret metadata, kept in the user's application-data directory.
HTTP requests NEVER start browser authentication.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import (
    AuthenticationRecord,
    AuthenticationRequiredError,
    CredentialUnavailableError,
    DefaultAzureCredential,
    InteractiveBrowserCredential,
    TokenCachePersistenceOptions,
)

from app.core.errors import ApplicationError

TOKEN_SCOPE = "https://ai.azure.com/.default"
LOGIN_COMMAND = "python -m app.modules.foundry.setup --login"


def _require_local(settings):
    if (settings.foundry_auth_mode != "interactive" or settings.environment != "development"
            or settings.auth_mode != "development"):
        raise ValueError("Este comando requiere Foundry interactivo en desarrollo local")


def _cache_name(settings):
    # Isolate tenants, client registrations and projects, as well as OS users.
    key = "\n".join((settings.foundry_tenant_id.lower(), settings.foundry_client_id.lower(),
                     settings.foundry_project_endpoint.rstrip("/")))
    return "datastage-foundry-" + hashlib.sha256(key.encode()).hexdigest()[:32]


def account_record_path(settings):
    _require_local(settings)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", "")
        if not base or not Path(base).is_absolute():
            raise ValueError("LOCALAPPDATA no está disponible para la sesión cifrada local")
        root = Path(base)
    else:
        root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
        if not root.is_absolute():
            raise ValueError("XDG_STATE_HOME debe ser una ruta absoluta")
    return root / "DataStage" / "Foundry" / _cache_name(settings) / "account.json"


def _browser_options(settings):
    _require_local(settings)
    options = {
        "tenant_id": settings.foundry_tenant_id,
        "cache_persistence_options": TokenCachePersistenceOptions(
            name=_cache_name(settings), allow_unencrypted_storage=False,
        ),
    }
    if settings.foundry_client_id:
        options.update(client_id=settings.foundry_client_id, redirect_uri=settings.foundry_redirect_uri)
    return options


def _validate_record(record, settings):
    authority = urlsplit(record.authority if "://" in record.authority else "https://" + record.authority)
    if (record.tenant_id.lower() != settings.foundry_tenant_id.lower()
            or authority.scheme != "https" or authority.hostname != "login.microsoftonline.com"
            or authority.username or authority.password or authority.query or authority.fragment
            or authority.port not in (None, 443)
            or (settings.foundry_client_id and record.client_id.lower() != settings.foundry_client_id.lower())):
        raise ValueError("La cuenta guardada no corresponde al tenant o cliente configurado")


def login_local(settings):
    """The ONLY path that permits browser interaction. Called explicitly by CLI."""
    options = _browser_options(settings)
    with InteractiveBrowserCredential(**options, timeout=180) as credential:
        record = credential.authenticate(scopes=[TOKEN_SCOPE])
    _validate_record(record, settings)
    path = account_record_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(record.serialize())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"tenantId": record.tenant_id, "status": "authenticated"}


def _load_record(settings):
    path = account_record_path(settings)
    try:
        if path.is_symlink() or path.stat().st_size > 16_384:
            raise ValueError("Invalid local account record")
        raw = path.read_text(encoding="utf-8")
        if not isinstance(json.loads(raw), dict):
            raise ValueError("Invalid local account record")
        record = AuthenticationRecord.deserialize(raw)
        _validate_record(record, settings)
        return record
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise ApplicationError(503, "foundry_login_required", f"Inicia sesión local con: {LOGIN_COMMAND}") from error


@contextmanager
def foundry_credential(settings):
    if settings.foundry_auth_mode == "default":
        options = {"exclude_interactive_browser_credential": True}
        if settings.environment == "production":
            options.update(
                exclude_shared_token_cache_credential=True,
                exclude_visual_studio_code_credential=True,
                exclude_cli_credential=True,
                exclude_developer_cli_credential=True,
                exclude_powershell_credential=True,
                exclude_broker_credential=True,
            )
        with DefaultAzureCredential(**options) as credential:
            yield credential
        return
    record = _load_record(settings)
    try:
        with InteractiveBrowserCredential(
            **_browser_options(settings), authentication_record=record,
            disable_automatic_authentication=True,
        ) as credential:
            # Fail before the inference call if MFA, consent or reauthentication
            # is required. The API cannot launch an interactive login window.
            credential.get_token(TOKEN_SCOPE)
            yield credential
    except (AuthenticationRequiredError, CredentialUnavailableError, ClientAuthenticationError) as error:
        raise ApplicationError(503, "foundry_login_required", f"Renueva tu sesión local con: {LOGIN_COMMAND}") from error
