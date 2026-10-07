from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ConsolidationRange:
    start_year: int
    start_month: int
    end_year: int
    end_month: int

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            lower, upper = (1900, 2100) if name.endswith("year") else (1, 12)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name}: valor fuera del intervalo {lower}-{upper}.")
        if self.start_index > self.end_index:
            raise ValueError("El mes final no puede ser anterior al mes inicial.")

    @property
    def start_index(self) -> int:
        return self.start_year * 12 + self.start_month

    @property
    def end_index(self) -> int:
        return self.end_year * 12 + self.end_month

    @property
    def label(self) -> str:
        return f"{self.start_year:04d}-{self.start_month:02d} - {self.end_year:04d}-{self.end_month:02d}"

    def contains(self, year: int, month: int) -> bool:
        return self.start_index <= year * 12 + month <= self.end_index

    def payload(self) -> dict[str, int]:
        return {"startYear": self.start_year, "startMonth": self.start_month,
                "endYear": self.end_year, "endMonth": self.end_month}


def consolidation_range(snapshot: dict) -> ConsolidationRange | None:
    value = snapshot.get("consolidation_range")
    return ConsolidationRange(**value) if value is not None else None


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
