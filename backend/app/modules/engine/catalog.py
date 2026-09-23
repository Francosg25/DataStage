"""Stable DataStage catalog and input normalization primitives."""
from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

ENGINE_VERSION = "1.0.0"
TABLE_ORDER = tuple(str(n) for n in range(501, 513)) + ("520",) + tuple(str(n) for n in range(551, 559)) + ("701", "702", "sel", "inci", "resumen")
TABLE_NAMES = dict(zip(TABLE_ORDER, (
    "501 Datos generales", "502 Transporte", "503 Guias", "504 Contenedores",
    "505 Facturas", "506 Fechas pedimento", "507 Casos pedimento", "508 Cuentas garantia",
    "509 Tasas pedimento", "510 Contribuciones", "511 Observaciones", "512 Descargos",
    "520 Destinatarios", "551 Partidas", "552 Mercancias", "553 Permiso partida",
    "554 Casos partida", "555 Cuentas partida", "556 Tasas partida", "557 Contribuciones partida",
    "558 Observaciones partida", "701 Rectificaciones", "702 Dif contribuciones",
    "Sel Automatizada", "Inci Reconocimiento", "Resumen",
)))
MONTH_NAMES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
_MONTH_ALIASES = (
    ("ene", "enero", "jan", "january"), ("feb", "febrero", "february"),
    ("mar", "marzo", "march"), ("abr", "abril", "apr", "april"),
    ("may", "mayo"), ("jun", "junio", "june"), ("jul", "julio", "july"),
    ("ago", "agosto", "aug", "august"), ("sep", "sept", "septiembre", "set", "setiembre", "september"),
    ("oct", "octubre", "october"), ("nov", "noviembre", "november"),
    ("dic", "diciembre", "dec", "december"),
)
MONTH_NUMBERS = {alias: index for index, aliases in enumerate(_MONTH_ALIASES, 1) for alias in aliases}
TRACE_HEADERS = ("Periodo", "ArchivoOrigen", "FolioOrigen")


def normalize_text(value: object) -> str:
    return "" if value is None else str(value).replace("\ufeff", "").strip()


def normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFD", normalize_text(value).lower())
    return re.sub(r"[^a-z0-9]", "", text)


def parse_period(text: str) -> tuple[int, int, str]:
    match = re.fullmatch(r"([A-Za-zÀ-ÿ]+)[_\s-]+(\d{4})", normalize_text(text))
    if not match:
        raise ValueError("Periodo inválido; utiliza Mes_Año, por ejemplo Abril_2026.")
    month = MONTH_NUMBERS.get(normalize_header(match[1]))
    year = int(match[2])
    if month is None or not 1900 <= year <= 2100:
        raise ValueError("Periodo inválido; mes no reconocido o año fuera de 1900–2100.")
    return year, month, f"{MONTH_NAMES[month - 1]}_{year}"


def range_end_month(range_name: str) -> int | None:
    tokens = [normalize_header(token) for token in re.split(r"[_\s\-/–—]+", normalize_text(range_name)) if token]
    if not tokens or tokens[-1] not in MONTH_NUMBERS:
        return None
    return MONTH_NUMBERS[tokens[-1]]


def file_stem(name: str) -> str:
    return PurePosixPath(normalize_text(name).replace("\\", "/")).stem


def detect_table_code(name: str, explicit: str | None = None) -> str:
    if normalize_text(explicit):
        return normalize_text(explicit).lower()
    stem = file_stem(name).lower()
    normalized = unicodedata.normalize("NFD", stem)
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    if "resumen" in normalized:
        return "resumen"
    if "inci" in normalized:
        return "inci"
    if "seleccion" in normalized or re.search(r"(?:^|[_\s-])sel(?:$|[_\s-])", normalized):
        return "sel"
    numbers = re.findall(r"(?<![^_\s-])\d{3}(?=$|[_\s-])", normalized)
    if numbers:
        return numbers[-1]
    segments = re.split(r"[_\s-]+", stem)
    return segments[-1] if segments else stem


def folio_from_name(name: str, code: str) -> str:
    stem = file_stem(name)
    stem = re.sub(r"(?:^|[_\s-])" + re.escape(code) + r"$", "", stem, flags=re.IGNORECASE).rstrip("_ -")
    segments = re.split(r"[_\s-]+", stem)
    return segments[-1] if segments else ""


def table_sort_key(code: str) -> tuple[int, str]:
    return (TABLE_ORDER.index(code), "") if code in TABLE_ORDER else (len(TABLE_ORDER), code)


def make_sheet_names(codes: list[str]) -> dict[str, str]:
    occupied = {"control_proceso"}
    result = {}
    for code in sorted(codes, key=table_sort_key):
        raw = TABLE_NAMES.get(code, code)
        base = re.sub(r"[\[\]:*?/\\\x00-\x1f]", "", raw).strip("'")[:31] or "Tabla"
        # Excel reserves History (case-insensitive) for revision tracking.
        if base.lower() == "history":
            base = "History_"
        name, suffix = base, 2
        while name.casefold() in occupied:
            tail = f"_{suffix}"
            name = base[:31 - len(tail)] + tail
            suffix += 1
        occupied.add(name.casefold())
        result[code] = name
    return result
