"""Non-secret local configuration; preserve unrelated settings and take a backup."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4


def validate_project(endpoint):
    parsed = urlsplit(endpoint)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not re.fullmatch(r"/api/projects/[^/]+/?", parsed.path)):
        raise ValueError("Usa el endpoint HTTPS del proyecto: https://RECURSO.services.ai.azure.com/api/projects/PROYECTO")
    return endpoint.rstrip("/")


def write_env(path: Path, updates: dict):
    """Write only Foundry keys, never print or rewrite unrelated credentials."""
    if any(not (key.startswith("DATASTAGE_FOUNDRY_") or key == "DATASTAGE_ALLOW_AGENT_COMMANDS") for key in updates):
        raise ValueError("Solo se permite actualizar la configuración de Foundry")
    original = path.read_bytes() if path.exists() else b""
    newline = "\r\n" if b"\r\n" in original else "\n"
    lines, seen = [], set()
    for line in original.decode("utf-8-sig").splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=", line)
        key = match.group(1) if match else None
        if key in updates:
            if key not in seen:
                lines.append(key + "=" + json.dumps(str(updates[key]), ensure_ascii=False))
                seen.add(key)
        else:
            lines.append(line)
    lines.extend(key + "=" + json.dumps(str(value), ensure_ascii=False)
                 for key, value in updates.items() if key not in seen)
    content = (newline.join(lines) + newline).encode("utf-8")
    if content == original:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if original:
        backups = path.parent / ".data" / "foundry-config-backups"
        backups.mkdir(parents=True, exist_ok=True)
        backup = backups / ("env-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid4().hex + ".bak")
        backup.write_bytes(original)
        backup.chmod(0o600)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(content)
        temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
        if (path.read_bytes() if path.exists() else b"") != original:
            raise RuntimeError("El archivo .env cambió durante la configuración; vuelve a intentarlo")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
