"""SQL Server persistence, with SQLite reserved for local development and tests."""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    options = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if ":memory:" in database_url or database_url in {"sqlite://", "sqlite+pysqlite://"}:
            options["poolclass"] = StaticPool
    elif database_url.startswith("mssql+pyodbc"):
        options["fast_executemany"] = True
    engine = create_engine(database_url, **options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _configure_sqlite(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    return engine


def session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


from . import models  # noqa: E402,F401
from .business import get_business_table, persist_business_rows  # noqa: E402,F401

__all__ = ["Base", "make_engine", "session_factory", "models", "get_business_table", "persist_business_rows"]
