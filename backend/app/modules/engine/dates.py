"""Strict calendar parsing. No machine locale or implicit time-zone conversion."""
from __future__ import annotations

import re
from datetime import datetime

from .catalog import normalize_header, normalize_text

KNOWN_DATE_HEADERS = frozenset(normalize_header(x) for x in (
    "FechaPagoReal", "FechaRecepcion", "FechaRecepcionPedimento", "FechaOperacion",
    "FechaValidacion", "FechaValidacionPagoR", "FechaValidacionOPagoReal", "FechaFacturacion",
    "FechaConstancia", "FechaPago", "FechaSeleccion", "FechaSeleccionAutomatizada",
    "FechaInicioReconocimiento", "FechaFinReconocimiento", "FechaOperacionAnterior",
    "FechaPagoAnterior", "FechaOperacionOriginal", "FechaPagoOriginal",
))
DATE_EXCLUSIONS = frozenset(normalize_header(x) for x in (
    "TipoFecha", "ClaveTipoFecha", "Clave de tipo de fecha", "Tipo de fecha", "NumeroFecha", "SecuenciaFecha",
))


def is_date_header(header: str) -> bool:
    key = normalize_header(header)
    if key in DATE_EXCLUSIONS or "tipofecha" in key or "clavetipofecha" in key:
        return False
    return key in KNOWN_DATE_HEADERS or key.startswith("fecha")


def parse_date(value: str, ambiguous_order: str = "DMY") -> tuple[datetime | None, bool]:
    """Return (date, ambiguous). Compact support deliberately covered by tests."""
    value = normalize_text(value)
    if not value:
        return None, False
    if ambiguous_order not in ("DMY", "MDY"):
        raise ValueError("ambiguous_date_order debe ser DMY o MDY.")
    ambiguous = False
    year = month = day = 0
    hour = minute = second = 0
    compact = re.fullmatch(r"(\d{4})(\d{2})(\d{2})(?:(\d{2})(\d{2})(\d{2}))?", value)
    if compact:
        year, month, day = map(int, compact.group(1, 2, 3))
        hour, minute, second = (int(v or 0) for v in compact.group(4, 5, 6))
    else:
        match = re.fullmatch(
            r"(\d{1,4})([-/])(\d{1,2})\2(\d{1,4})"
            r"(?:[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?)?",
            value, re.IGNORECASE,
        )
        # A compact date may be followed by a conventional time.
        compact_time = re.fullmatch(r"(\d{4})(\d{2})(\d{2})[T\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?", value, re.IGNORECASE)
        if compact_time:
            year, month, day = map(int, compact_time.group(1, 2, 3))
            hour, minute, second = (int(v or 0) for v in compact_time.group(4, 5, 6))
            meridiem = compact_time[7]
        elif match:
            first, middle, last = int(match[1]), int(match[3]), int(match[4])
            if len(match[1]) == 4 and len(match[4]) <= 2:
                year, month, day = first, middle, last
            elif len(match[4]) == 4 and len(match[1]) <= 2:
                year = last
                if first > 12:
                    day, month = first, middle
                elif middle > 12:
                    month, day = first, middle
                elif ambiguous_order == "DMY":
                    day, month = first, middle
                    ambiguous = first != middle
                else:
                    month, day = first, middle
                    ambiguous = first != middle
            else:
                return None, False
            hour, minute, second = (int(v or 0) for v in match.group(5, 6, 7))
            meridiem = match[8]
        else:
            return None, False
        if meridiem:
            if not 1 <= hour <= 12:
                return None, False
            hour = hour % 12 + (12 if meridiem.upper() == "PM" else 0)
    if not 1900 <= year <= 2100:
        return None, False
    try:
        return datetime(year, month, day, hour, minute, second), ambiguous
    except ValueError:
        return None, False
