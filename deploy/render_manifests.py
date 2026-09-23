"""Render non-secret deployment settings; fail on missing or malformed input."""
from __future__ import annotations

import json
import argparse
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def validate_value(name: str, value: str):
    if "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("Valor de despliegue inválido: " + name)
    if name == "NAMESPACE" and not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value):
        raise ValueError("NAMESPACE debe ser un nombre DNS de hasta 63 caracteres")
    if name in {"PUBLIC_HOST", "STORAGE_CLASS", "INGRESS_CLASS"} and (
        len(value) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", value)
    ):
        raise ValueError("Nombre DNS de despliegue inválido: " + name)
    if name == "SCOPE_ID" and not 1 <= len(value) <= 100:
        raise ValueError("SCOPE_ID debe contener entre 1 y 100 caracteres")
    if name in {"BACKEND_IMAGE", "FRONTEND_IMAGE"} and not re.fullmatch(r"[^\s@]+@sha256:[a-f0-9]{64}", value):
        raise ValueError(name + " debe fijar un digest sha256 de 64 caracteres")
    if name == "CORS_ORIGINS":
        try:
            origins = json.loads(value)
            valid = isinstance(origins, list) and bool(origins) and all(
                isinstance(origin, str) and urlsplit(origin).scheme == "https"
                and bool(urlsplit(origin).hostname) and not urlsplit(origin).username
                and not urlsplit(origin).password and urlsplit(origin).path in ("", "/")
                and not urlsplit(origin).query and not urlsplit(origin).fragment
                for origin in origins
            )
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError("CORS_ORIGINS debe ser un array JSON de orígenes HTTPS explícitos")


def render(source: str, environ: dict[str, str]) -> str:
    names = set(re.findall(r"\$\{([A-Z_]+)\}", source))
    missing = sorted(name for name in names if not environ.get(name))
    if missing:
        raise ValueError("Faltan variables de despliegue: " + ", ".join(missing))
    for name in names:
        value = environ[name]
        validate_value(name, value)
        source = source.replace("${" + name + "}", json.dumps(value))
    return source


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--migration", action="store_true")
    args = parser.parse_args()
    template = Path(__file__).parent / "kubernetes" / ("migration.yaml.template" if args.migration else "application.yaml.template")
    try:
        sys.stdout.write(render(template.read_text(encoding="utf-8"), dict(os.environ)))
    except ValueError as exc:
        sys.exit(str(exc))
