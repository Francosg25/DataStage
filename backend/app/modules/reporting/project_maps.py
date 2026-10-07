"""Read-only, deployment-scoped maps from the supplied project presentation."""
import json
from functools import lru_cache
from pathlib import Path

from app.core.errors import ApplicationError


RESOURCE_DIR = Path(__file__).resolve().parents[2] / "resources" / "project-maps"


@lru_cache(maxsize=1)
def _catalog():
    try:
        return json.loads((RESOURCE_DIR / "manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ApplicationError(503, "MAPS_UNAVAILABLE", "Los mapas del proyecto no están disponibles") from None


def catalog(principal, settings):
    principal.require("Reader", "Operator", "Reprocessor", "Auditor")
    if principal.scope_id != settings.scope_id:
        raise ApplicationError(404, "MAPS_NOT_FOUND", "No se encontraron mapas para este ámbito")
    return _catalog()


def image_path(principal, settings, map_id, thumbnail=False):
    pages = catalog(principal, settings)["pages"]
    page = next((page for page in pages if page["id"] == map_id), None)
    if not page:
        raise ApplicationError(404, "MAP_NOT_FOUND", "No se encontró el mapa")
    # Only catalogued identifiers reach the filesystem; no client-controlled paths.
    path = RESOURCE_DIR / f"{page['id']}{'-thumb' if thumbnail else ''}.png"
    if not path.is_file():
        raise ApplicationError(503, "MAPS_UNAVAILABLE", "La imagen del mapa no está disponible")
    return path
