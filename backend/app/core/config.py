from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATASTAGE_", env_file=".env", extra="ignore", hide_input_in_errors=True)

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
    foundry_auth_mode: Literal["default", "interactive"] = "default"
    foundry_tenant_id: str = ""
    foundry_client_id: str = ""
    foundry_redirect_uri: str = ""
    foundry_max_tool_rounds: int = Field(default=5, ge=1, le=10)
    foundry_max_output_tokens: int = Field(default=4000, ge=512, le=16384)
    foundry_timeout_seconds: int = Field(default=45, ge=5, le=120)
    allow_agent_commands: bool = False
    project_maps_root: Path | None = None

    @model_validator(mode="after")
    def production_requirements(self):
        if self.foundry_auth_mode == "interactive":
            if self.environment != "development" or self.auth_mode != "development":
                raise ValueError("La sesión personal de Foundry solo se permite en desarrollo local")
            try:
                UUID(self.foundry_tenant_id)
                if self.foundry_client_id:
                    UUID(self.foundry_client_id)
            except (ValueError, TypeError) as error:
                raise ValueError("Configura un tenant ID y, si corresponde, client ID válidos para Foundry") from error
            if bool(self.foundry_client_id) != bool(self.foundry_redirect_uri):
                raise ValueError("Un cliente interactivo propio requiere su client ID y redirect URI local")
            if self.foundry_redirect_uri:
                redirect = urlsplit(self.foundry_redirect_uri)
                if (redirect.scheme != "http" or redirect.hostname not in {"localhost", "127.0.0.1"}
                        or not redirect.port or redirect.username or redirect.password or redirect.query or redirect.fragment):
                    raise ValueError("El redirect URI de Foundry debe ser HTTP loopback con puerto explícito")
        if self.environment == "production":
            if self.auth_mode != "entra":
                raise ValueError("Producción requiere autenticación Entra ID")
            if not self.database_url.startswith("mssql+pyodbc://"):
                raise ValueError("Producción requiere SQL Server mediante mssql+pyodbc")
            validate_sqlserver_url(self.database_url)
            if not self.document_root.is_absolute() or self.document_root.resolve().is_relative_to(ROOT.resolve()):
                raise ValueError("Producción requiere documentos persistentes fuera del directorio de la aplicación")
            if not self.cors_origins or any(
                urlsplit(origin).scheme != "https" or not urlsplit(origin).hostname
                or urlsplit(origin).path not in ("", "/") or urlsplit(origin).query
                or urlsplit(origin).fragment or urlsplit(origin).username or "*" in origin
                for origin in self.cors_origins
            ):
                raise ValueError("Producción requiere orígenes CORS HTTPS explícitos")
        if self.auth_mode == "entra" and not all((self.entra_tenant_id, self.entra_client_id, self.entra_audience, self.entra_api_scope)):
            raise ValueError("Entra requiere tenant, cliente SPA, audiencia API y scope")
        if self.foundry_enabled and not self.foundry_project_endpoint.startswith("https://"):
            raise ValueError("Foundry requiere endpoint HTTPS de proyecto")
        return self


def validate_sqlserver_url(value: str):
    """Require explicit transport encryption; disallow hidden DSN/ODBC overrides."""
    try:
        url = make_url(value)
        options = {k.lower(): v for k, v in url.query.items()}
        valid = (
            url.drivername == "mssql+pyodbc" and url.host and url.database and url.username
            and len(options) == len(url.query)
            and set(options) <= {"driver", "encrypt", "trustservercertificate"}
            and options.get("driver") == "ODBC Driver 18 for SQL Server"
            and options.get("encrypt", "").lower() in {"yes", "true", "mandatory", "strict"}
            and options.get("trustservercertificate", "").lower() in {"no", "false"}
        )
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("SQL Server requiere URL explícito, ODBC Driver 18, Encrypt=yes y TrustServerCertificate=no")
    return url
