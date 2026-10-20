"""Azure identity for services and an explicit, encrypted local browser login."""
import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from azure.identity import (
    AuthenticationRecord, CredentialUnavailableError, DefaultAzureCredential,
    InteractiveBrowserCredential, TokenCachePersistenceOptions,
)

FOUNDRY_SCOPE = "https://ai.azure.com/.default"


def _profile(settings):
    identity = "|".join((settings.foundry_project_endpoint.rstrip("/"),
                         settings.foundry_tenant_id, settings.foundry_client_id))
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _record_path(settings):
    # Only non-secret account metadata lives here. Azure Identity owns the
    # encrypted token cache in the operating system's standard cache location.
    return Path.home() / ".datastage" / "foundry" / (_profile(settings) + ".json")


def credential(settings, *, interactive=False):
    if settings.foundry_auth_mode == "default":
        if interactive:
            raise ValueError("Selecciona foundry_auth_mode=browser para iniciar sesión desde el navegador")
        return DefaultAzureCredential(exclude_interactive_browser_credential=True)
    if settings.environment == "production":
        raise ValueError("El login por navegador no está permitido en producción")
    record = None
    path = _record_path(settings)
    if path.is_file() and not interactive:
        try:
            record = AuthenticationRecord.deserialize(path.read_text(encoding="utf-8"))
        except (ValueError, KeyError) as error:
            raise CredentialUnavailableError("Renueva la sesión con python -m app.modules.foundry.setup --login") from error
    if record is None and not interactive:
        raise CredentialUnavailableError("Inicia sesión con python -m app.modules.foundry.setup --login")
    options = {
        "tenant_id": settings.foundry_tenant_id or (record.tenant_id if record else "organizations"),
        "authentication_record": record,
        "disable_automatic_authentication": True,
        "cache_persistence_options": TokenCachePersistenceOptions(
            name="datastage-foundry-" + _profile(settings), allow_unencrypted_storage=False),
    }
    if settings.foundry_client_id:
        redirect = urlsplit(settings.foundry_redirect_uri)
        if (redirect.scheme != "http" or redirect.hostname not in {"localhost", "127.0.0.1"}
                or redirect.username or redirect.password or redirect.query or redirect.fragment):
            raise ValueError("Configura el redirect URI localhost registrado por TI para el cliente de desarrollo")
        options.update(client_id=settings.foundry_client_id, redirect_uri=settings.foundry_redirect_uri)
    return InteractiveBrowserCredential(**options)


def login(settings):
    """Only this explicit CLI action may launch Microsoft's sign-in page."""
    with credential(settings, interactive=True) as identity:
        record = identity.authenticate(scopes=[FOUNDRY_SCOPE])
    path = _record_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(record.serialize(), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
