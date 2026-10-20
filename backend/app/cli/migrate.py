"""Production migrations use a separate credential, never the runtime identity."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from app.core.config import Settings, validate_sqlserver_url


def migration_url(runtime, migration):
    live = validate_sqlserver_url(runtime)
    ddl = validate_sqlserver_url(migration)
    if (live.host.lower(), live.port or 1433, live.database.lower()) != (
        ddl.host.lower(), ddl.port or 1433, ddl.database.lower()
    ):
        raise ValueError("Las identidades deben apuntar al mismo servidor y base")
    if live.username.casefold() == ddl.username.casefold():
        raise ValueError("La identidad de migración debe ser distinta de la de ejecución")
    return ddl


def main():
    settings = Settings()
    if settings.environment != "production":
        raise ValueError("Este comando es exclusivo de producción; en local usa alembic")
    url = migration_url(settings.database_url, os.environ.get("DATASTAGE_MIGRATION_DATABASE_URL", ""))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # DB exceptions can contain credentials/SQL; retain diagnostics in DBA logs.
        raise SystemExit(f"Migración fallida ({type(exc).__name__}); revisar configuración y logs SQL.") from None
