from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATASTAGE_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = f"sqlite:///{(ROOT / '.data/datastage.db').as_posix()}"
    document_root: Path = ROOT / ".data/documents"
    auth_mode: Literal["development", "entra"] = "development"
    scope_id: str = "local"
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_audience: str = ""
    entra_api_scope: str = ""
    cors_origins: list[str] = ["http://localhost:4200", "http://127.0.0.1:4200"]
    max_upload_mb: int = Field(default=50, ge=1, le=1024)
    max_extracted_mb: int = Field(default=500, ge=1, le=4096)
    max_file_mb: int = Field(default=100, ge=1, le=1024)
    max_zip_entries: int = Field(default=2000, ge=1, le=10000)
    max_compression_ratio: int = Field(default=500, ge=1, le=10000)
    max_rows: int = Field(default=1_048_575, ge=1, le=1_048_575)
    max_columns: int = Field(default=1024, ge=1, le=16384)
    asc_encoding: Literal["utf-8-sig", "cp1252"] = "utf-8-sig"
    ambiguous_date_order: Literal["DMY", "MDY"] = "DMY"
    preferred_date_headers: list[str] = ["FechaPagoReal", "FechaValidacionPagoR", "FechaPago", "FechaOperacion", "FechaRecepcionPedimento"]
    worker_poll_seconds: float = Field(default=2, ge=0.1)
    job_lease_seconds: int = Field(default=120, ge=10)
    max_job_attempts: int = Field(default=4, ge=1, le=10)
    auto_annual: bool = True
    analytics_reference_file: Path | None = None
    foundry_enabled: bool = False
    foundry_project_endpoint: str = ""
    foundry_agent_name: str = "datastage-assistant"
    foundry_agent_version: str = "1"
    foundry_model: str = ""
    foundry_max_tool_rounds: int = Field(default=5, ge=1, le=10)
    foundry_timeout_seconds: int = Field(default=45, ge=5, le=120)
    allow_agent_commands: bool = False
    antivirus_command: list[str] = []
    antivirus_timeout_seconds: int = Field(default=120, ge=1, le=600)

    @model_validator(mode="after")
    def production_requirements(self):
        if self.environment == "production":
            if self.auth_mode != "entra":
                raise ValueError("Producción requiere autenticación Entra ID")
            if not self.database_url.startswith("mssql+pyodbc://"):
                raise ValueError("Producción requiere SQL Server mediante mssql+pyodbc")
            if not self.antivirus_command:
                raise ValueError("Producción requiere configurar el escáner antivirus")
            if "*" in self.cors_origins:
                raise ValueError("Producción requiere orígenes CORS explícitos")
        if self.auth_mode == "entra" and not all((self.entra_tenant_id, self.entra_client_id, self.entra_audience, self.entra_api_scope)):
            raise ValueError("Entra requiere tenant, cliente SPA, audiencia API y scope")
        if self.foundry_enabled and not self.foundry_project_endpoint.startswith("https://"):
            raise ValueError("Foundry requiere endpoint HTTPS de proyecto")
        return self
