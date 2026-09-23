import json
from datetime import datetime

import pytest
from sqlalchemy import select

from app.modules.engine import InputFile, process_monthly
from app.persistence import Base, get_business_table, make_engine, persist_business_rows, session_factory
from app.persistence.business import EXTENSION_TABLES, _datetime_value
from app.persistence.models import Period, ProcessingFile, Run


@pytest.mark.parametrize("value", ["1899-12-31T00:00:00", "2101-01-01T00:00:00", "2200-01-01T00:00:00"])
def test_out_of_range_date_is_sql_null_and_original_is_preserved(value):
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    try:
        with factory.begin() as session:
            period = Period(id="period", scope_id="test", year=2026, month=4, name="Abril_2026")
            session.add(period)
            session.flush()
            run = Run(id="run", scope_id="test", year=2026, period_id=period.id, input_fingerprint="bounds")
            session.add(run)
            session.flush()
            source = ProcessingFile(id="file", run_id=run.id, period_id=period.id, file_name="source_501.asc",
                                    table_code="501", sha256="a" * 64, ordinal=0)
            session.add(source)
            session.flush()
            result = process_monthly(period.name, [InputFile(source.file_name,
                                     f"FechaPagoReal|FechaNueva\n{value}|{value}", period.name, file_id=source.id)])
            assert len(result["warnings"]) == 2
            persist_business_rows(session, run.id, result["tables"][0], {period.name: period})
            row = session.execute(select(get_business_table("501"))).mappings().one()
            assert row["fecha_pago_real"] is None
            assert json.loads(row["original_dates_json"])["fechapagoreal"] == value
            extension = session.execute(select(EXTENSION_TABLES["501"])).mappings().one()
            assert extension["date_value"] is None
            assert extension["original_value"] == value
    finally:
        engine.dispose()


def test_datetime_input_obeys_same_calendar_year_bounds():
    assert _datetime_value(datetime(1899, 12, 31)) is None
    assert _datetime_value(datetime(2101, 1, 1)) is None
    assert _datetime_value(datetime(1900, 1, 1)) == datetime(1900, 1, 1)
    assert _datetime_value(datetime(2100, 12, 31)) == datetime(2100, 12, 31)
