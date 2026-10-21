"""Update only Foundry keys in backend/.env, retaining private configuration."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from app.core.config import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = BACKEND_ROOT / ".env"


def require_local(settings):
    if settings.environment != "development" or settings.auth_mode != "development":
        raise ValueError("La configuración automática solo se permite en desarrollo local")


def validate_endpoint(value):
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment
            or not re.fullmatch(r"/api/projects/[^/]+/?", url.path)):
        raise ValueError("Usa el endpoint HTTPS del proyecto: /api/projects/<proyecto>")
    return value.rstrip("/")


def update_foundry_env(updates):
    if any(not key.startswith("DATASTAGE_FOUNDRY_") and key != "DATASTAGE_ALLOW_AGENT_COMMANDS" for key in updates):
        raise ValueError("Solo se permite actualizar la configuración de Foundry")
    if ENV_PATH.is_symlink():
        raise ValueError("El archivo .env local debe ser un archivo normal")
    existed = ENV_PATH.exists()
    before = ENV_PATH.read_bytes() if existed else b""
    content = before.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in content else "\n"
    values = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in updates.items()}
    remaining = dict(values)
    lines = []
    for line in content.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        key = match.group(1) if match else None
        if key in values:
            if key in remaining:
                lines.append(f"{key}={json.dumps(remaining.pop(key), ensure_ascii=False)}")
        else:
            lines.append(line)
    if remaining:
        if lines and lines[-1]:
            lines.append("")
        lines.extend(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in remaining.items())
    after = (newline.join(lines) + newline).encode("utf-8")
    if after == before:
        return {"environmentFile": str(ENV_PATH), "backup": None}
    backup = None
    if existed:
        backup_dir = BACKEND_ROOT.parent / ".data" / "config-backups"
        backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = backup_dir / f"foundry-{stamp}-{uuid4().hex}.env"
        with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
            stream.write(before)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=BACKEND_ROOT, prefix=".env.foundry-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(after)
        if ENV_PATH.exists() != existed or (existed and ENV_PATH.read_bytes() != before):
            raise ValueError("El .env cambió durante la operación; vuelve a revisar la configuración")
        os.replace(temporary, ENV_PATH)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"environmentFile": str(ENV_PATH), "backup": str(backup) if backup else None}


def configure_local(settings=None, *, endpoint, tenant_id, model, agent_name=None, agent_version, client_id=None, redirect_uri=None):
    if not all((endpoint, tenant_id, model, agent_version)):
        raise ValueError("Indica endpoint, tenant, modelo, nombre y versión existente del agente")
    fields = dict(
        foundry_project_endpoint=validate_endpoint(endpoint), foundry_tenant_id=tenant_id,
        foundry_model=model, foundry_agent_version=agent_version,
        foundry_auth_mode="interactive", foundry_enabled=False, allow_agent_commands=False,
    )
    for key, value in (("foundry_agent_name", agent_name), ("foundry_client_id", client_id),
                       ("foundry_redirect_uri", redirect_uri)):
        if value is not None:
            fields[key] = value
    # Validate the requested configuration, not the stale Foundry values it replaces.
    # All other settings still come from their normal sources and remain validated.
    if settings is None:
        configured = Settings(_env_file=ENV_PATH, **fields)
    else:
        configured = Settings(_env_file=None, **{**settings.model_dump(), **fields})
    require_local(configured)
    if not configured.foundry_agent_name:
        raise ValueError("Indica el nombre existente del agente")
    fields.update(foundry_agent_name=configured.foundry_agent_name,
                  foundry_client_id=configured.foundry_client_id,
                  foundry_redirect_uri=configured.foundry_redirect_uri)
    result = update_foundry_env({"DATASTAGE_" + key.upper(): value for key, value in fields.items()})
    return {**result, "status": "configured", "foundryEnabled": False}
