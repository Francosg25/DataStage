import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.dialects import mssql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable, CreateIndex

from app.persistence import Base, get_business_table, make_engine, persist_business_rows, session_factory
from app.persistence.business import BUSINESS_TABLES, EXTENSION_TABLES
from app.persistence.models import Period, ProcessingFile, Run


@pytest.fixture
def database():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield engine, session_factory(engine)
    engine.dispose()


def source_run(session):
    period = Period(scope_id="test", year=2026, month=4, name="Abril_2026")
    session.add(period)
    session.flush()
    run = Run(scope_id="test", year=2026, period_id=period.id, input_fingerprint="a" * 64)
    session.add(run)
    session.flush()
    source = ProcessingFile(run_id=run.id, period_id=period.id, file_name="request_501.asc", table_code="501", sha256="b" * 64, ordinal=0)
    session.add(source)
    session.flush()
    return period, run, source


def payload(source):
    return {
        "tableCode": "501",
        "headers": ["Periodo", "ArchivoOrigen", "FolioOrigen", "PedimentoCompleto", "Patente", "FechaPagoReal", "FechaNueva", "NuevaColumna"],
        "rows": [["Abril_2026", source.file_name, "request", "26 24 0036 0000009", "0036", "2026-04-20T00:00:00", "2026-04-21T12:30:00", "0009"]],
        "rowSources": [{"fileId": source.id, "fileName": source.file_name, "period": "Abril_2026", "folio": "request", "rowNumber": 2, "originalDates": {"FechaPagoReal": "20/04/2026", "FechaNueva": "21/04/2026 12:30"}}],
    }


def test_all_official_tables_have_explicit_columns_and_typed_dates(database):
    engine, _ = database
    assert len(BUSINESS_TABLES) == 26
    assert len(EXTENSION_TABLES) == 26
    assert set(BUSINESS_TABLES) == {str(n) for n in range(501, 513)} | {"520"} | {str(n) for n in range(551, 559)} | {"701", "702", "sel", "inci", "resumen"}
    assert "fecha_pago_real" in get_business_table("501").c
    assert "tipo_fecha" in get_business_table("506").c
    assert len(inspect(engine).get_table_names()) == 65
    assert get_business_table("unknown") is None
    assert set(inspect(engine).get_view_names()) == {"processing_errors", "processing_warnings"}
    Base.metadata.create_all(engine)  # Local restart is idempotent, including views.


def test_business_insert_preserves_text_dates_extensions_and_trace(database):
    _, factory = database
    with factory.begin() as session:
        period, run, source = source_run(session)
        assert persist_business_rows(session, run.id, payload(source), {period.name: period}) == 1
        row = session.execute(select(get_business_table("501"))).mappings().one()
        assert row["patente"] == "0036"
        assert row["fecha_pago_real"] == datetime(2026, 4, 20)
        assert row["processing_file_id"] == source.id
        assert row["source_row_number"] == 2
        assert json.loads(row["original_dates_json"])["FechaPagoReal"] == "20/04/2026"
        extensions = session.execute(select(EXTENSION_TABLES["501"])).mappings().all()
        assert {e["header_key"] for e in extensions} == {"fechanueva", "nuevacolumna"}
        date = next(e for e in extensions if e["value_kind"] == "date")
        assert date["date_value"] == datetime(2026, 4, 21, 12, 30)
        assert date["original_value"] == "21/04/2026 12:30"


def test_duplicate_source_cannot_be_inserted_twice(database):
    _, factory = database
    with factory.begin() as session:
        period, run, source = source_run(session)
        persist_business_rows(session, run.id, payload(source), {period.name: period})
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            persist_business_rows(session, run.id, payload(source), {period.name: period})
    with factory() as session:
        assert len(session.execute(select(get_business_table("501"))).all()) == 1


def test_normalized_date_keys_are_preserved_without_mutating_source(database):
    _, factory = database
    with factory.begin() as session:
        period, run, source = source_run(session)
        data = payload(source)
        originals = {"fechapagoreal": "20/04/2026", "fechanueva": "21/04/2026 12:30"}
        data["rowSources"][0]["originalDates"] = originals
        persist_business_rows(session, run.id, data, {period.name: period})
        row = session.execute(select(get_business_table("501"))).mappings().one()
        assert json.loads(row["original_dates_json"]) == originals
        assert len(originals) == 2
        extensions = session.execute(select(EXTENSION_TABLES["501"])).mappings().all()
        assert next(e for e in extensions if e["header_key"] == "fechanueva")["original_value"] == "21/04/2026 12:30"


def test_failed_unit_of_work_rolls_back_all_business_rows(database):
    _, factory = database
    with factory.begin() as session:
        period, run, source = source_run(session)
    with pytest.raises(RuntimeError):
        with factory.begin() as session:
            persist_business_rows(session, run.id, payload(source), {period.name: period})
            raise RuntimeError("Simulated publication failure")
    with factory() as session:
        assert session.execute(select(get_business_table("501"))).first() is None


def test_invalid_date_retains_original_and_nullable_date(database):
    _, factory = database
    with factory.begin() as session:
        period, run, source = source_run(session)
        data = payload(source)
        data["rows"][0][5] = "impossible"
        data["rowSources"][0]["originalDates"]["FechaPagoReal"] = "impossible"
        persist_business_rows(session, run.id, data, {period.name: period})
        row = session.execute(select(get_business_table("501"))).mappings().one()
        assert row["fecha_pago_real"] is None
        assert json.loads(row["original_dates_json"])["FechaPagoReal"] == "impossible"


def test_foreign_keys_and_period_uniqueness_are_enforced(database):
    _, factory = database
    with factory.begin() as session:
        session.add(Period(scope_id="test", year=2026, month=4, name="Abril_2026"))
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(Period(scope_id="test", year=2026, month=4, name="Apr_2026"))
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.add(Run(scope_id="test", year=2026, period_id="missing", input_fingerprint="c" * 64))


def test_sql_server_ddl_compiles_with_datetime2_and_nvarchar_max():
    dialect = mssql.dialect()
    for table in Base.metadata.tables.values():
        str(CreateTable(table).compile(dialect=dialect))
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=dialect))
    ddl = str(CreateTable(get_business_table("501")).compile(dialect=dialect))
    assert "DATETIME2" in ddl
    assert "NVARCHAR(max)" in ddl
    assert "IDENTITY" in ddl


def test_alembic_upgrade_matches_metadata_and_downgrade(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    path = tmp_path / "migration.db"
    url = "sqlite:///" + str(path).replace("\\", "/")
    monkeypatch.setenv("DATASTAGE_DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = make_engine(url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    engine.dispose()
    command.downgrade(config, "base")
    engine = make_engine(url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    assert inspect(engine).get_view_names() == []
    engine.dispose()


@pytest.mark.skipif(not os.getenv("DATASTAGE_TEST_SQLSERVER_URL"), reason="Dedicated SQL Server test URL not supplied")
def test_live_sqlserver_schema_and_transactional_business_insert():
    """Opt-in only: URL must name a pre-provisioned, dedicated empty test database.

    Creates schema only when empty. Inserts roll back, and no DROP is performed.
    On later runs, validates the existing schema instead of recreating it.
    """
    engine = make_engine(os.environ["DATASTAGE_TEST_SQLSERVER_URL"])
    assert engine.dialect.name == "mssql", "Opt-in integration URL must target SQL Server"
    existing = inspect(engine).get_table_names()
    if not existing:
        Base.metadata.create_all(engine)
    assert set(Base.metadata.tables).issubset(set(inspect(engine).get_table_names()))
    with engine.connect() as connection:
        transaction = connection.begin()
        factory = session_factory(connection)
        with factory() as session:
            period, run, source = source_run(session)
            assert persist_business_rows(session, run.id, payload(source), {period.name: period}) == 1
            row = session.execute(select(get_business_table("501"))).mappings().one()
            assert row["patente"] == "0036"
            assert row["fecha_pago_real"] == datetime(2026, 4, 20)
        if transaction.is_active:
            transaction.rollback()
    engine.dispose()
