from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InputFile:
    file_name: str
    content: str
    period: str
    table_code: str | None = None
    file_id: str = ""


@dataclass(frozen=True)
class EngineOptions:
    ambiguous_date_order: str = "DMY"
    preferred_date_headers: tuple[str, ...] = (
        "FechaPagoReal", "FechaValidacionPagoR", "FechaPago", "FechaOperacion", "FechaRecepcionPedimento",
    )
    max_rows: int = 1_048_575
    max_columns: int = 16_384

    def __post_init__(self) -> None:
        if self.ambiguous_date_order not in ("DMY", "MDY"):
            raise ValueError("ambiguous_date_order debe ser DMY o MDY.")
        if self.max_rows < 1 or self.max_columns < 1:
            raise ValueError("Los límites de filas y columnas deben ser positivos.")
