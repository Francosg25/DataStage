"""Alembic supports both corporate SQL Server and the explicit SQLite local profile."""
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.persistence import Base
from app.core.config import Settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
# A caller-supplied connection or explicit Alembic URL wins. Otherwise use the
# same Settings/env precedence as API and worker, including backend/.env when
# Alembic is invoked from the repository root with -c backend/alembic.ini.
if config.attributes.get("connection") is None and not config.get_main_option("sqlalchemy.url"):
    environment_file = Path(config.config_file_name).resolve().parent / ".env" if config.config_file_name else Path(".env")
    database_url = Settings(_env_file=environment_file).database_url
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    connectable = engine_from_config(config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
