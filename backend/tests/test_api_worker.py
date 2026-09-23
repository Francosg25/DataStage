import io
import zipfile
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.config import Settings
from app.main import create_app
from app.modules.identity.auth import Principal, current_principal
from app.persistence import get_business_table
from app.persistence.models import Job
from app.worker import claim_job, job_guard, run_once

ASC = "Patente|Pedimento|SeccionAduanera|FechaPagoReal|Rfc|\n0036|0000009|240|2026-04-20 13:14:15|RFCDEMO|\n"

def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, content in entries.items():
            zipped.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), content)
    return stream.getvalue()

@pytest.fixture
def system(tmp_path):
    settings = Settings(environment="test", database_url=f"sqlite:///{(tmp_path/'test.db').as_posix()}",
                        document_root=tmp_path/"documents", auto_annual=False, job_lease_seconds=30)
    app = create_app(settings)
    with TestClient(app) as client:
        yield app, client, settings

def upload(client, entries=None, period="Abril_2026", key=None):
    return client.post("/api/v1/monthly-runs", data={"periodo": period},
                       files={"zip": ("input.zip", archive(entries or {"folio_501.asc": ASC}), "application/zip")},
                       headers={"Idempotency-Key": key or str(uuid4())})

def drain(app, settings, maximum=15):
    for _ in range(maximum):
        if not run_once(app.state.session_factory, settings, app.state.storage):
            return
    pytest.fail("Queue did not drain")

def get_run(client, response):
    assert response.status_code == 202, response.text
    return client.get(f"/api/v1/runs/{response.json()['id']}").json()

def test_monthly_roundtrip_sql_text_dates_and_excel(system):
    app, client, settings = system
    response = upload(client)
    assert response.status_code == 202, response.text
    assert response.headers["location"].endswith(response.json()["id"])
    drain(app, settings)
    result = get_run(client, response)
    assert result["status"] == "completed", result
    assert result["publicationStatus"] == "published"
    assert result["counts"]["rows"] == 1
    page = client.get("/api/v1/data/501").json()
    assert page["total"] == 1, page
    assert page["items"][0]["Patente"] == "0036"
    assert page["items"][0]["PedimentoCompleto"] == "26 24 0036 0000009"
    assert page["items"][0]["FechaPagoReal"] == "2026-04-20T13:14:15"
    downloaded = client.get(f"/api/v1/documents/{result['exportDocumentId']}/download")
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as zipped:
        assert "xl/workbook.xml" in zipped.namelist()
    control = client.get(f"/api/v1/runs/{result['id']}/control").json()
    assert control["total"] == 2
    assert client.get("/health/ready").status_code == 200

def test_idempotency_replay_and_conflicting_key(system):
    app, client, settings = system
    key = str(uuid4())
    first = upload(client, key=key)
    replay = upload(client, key=key)
    assert first.status_code == replay.status_code == 202
    assert first.json()["id"] == replay.json()["id"]
    other_key = upload(client)
    assert other_key.json()["id"] == first.json()["id"]
    conflict = upload(client, period="Mayo_2026", key=key)
    assert conflict.status_code == 409
    drain(app, settings)
    assert client.get("/api/v1/data/501").json()["total"] == 1

def test_partial_error_preserves_valid_file_and_returns_warning(system):
    app, client, settings = system
    response = upload(client, {"good_501.asc": ASC, "bad_551.asc": "Fraccion|Fracción|\n1|2|"})
    drain(app, settings)
    result = get_run(client, response)
    assert result["functionalResult"] == "WARNING", result
    assert result["status"] == "completed"
    assert result["counts"]["errors"] == 1
    assert client.get("/api/v1/data/501").json()["total"] == 1

def test_invalid_date_is_raw_text_in_query_and_nullable_in_sql(system):
    app, client, settings = system
    response = upload(client, {"source_501.asc": ASC.replace("2026-04-20 13:14:15", "2026-02-30")})
    drain(app, settings)
    result = get_run(client, response)
    assert result["functionalResult"] == "OK"
    assert result["counts"]["warnings"] >= 1
    assert client.get("/api/v1/data/501").json()["items"][0]["FechaPagoReal"] == "2026-02-30"
    with app.state.session_factory() as session:
        table = get_business_table("501")
        assert session.scalar(select(table.c.fecha_pago_real)) is None

def test_annual_snapshot_does_not_duplicate_monthly_rows(system):
    app, client, settings = system
    april = upload(client)
    drain(app, settings)
    assert upload(client, period="Mayo_2026").status_code == 202
    drain(app, settings)
    response = client.post("/api/v1/annual-runs", json={"anio":2026, "rangoNombre":"Ene-May"},
                           headers={"Idempotency-Key":str(uuid4())})
    drain(app, settings)
    annual = get_run(client, response)
    assert annual["status"] == "completed", annual
    assert annual["counts"]["rows"] == 2
    snapshot = client.get("/api/v1/data/501", params={"runId": annual["id"]}).json()
    assert snapshot["total"] == 2, snapshot
    filtered = client.get("/api/v1/data/501", params={"runId": annual["id"], "period": "May_2026"}).json()
    assert filtered["total"] == 1, filtered
    with app.state.session_factory() as session:
        table = get_business_table("501")
        assert session.scalar(select(func.count()).select_from(table)) == 2
    assert client.get("/api/v1/reports/overview").json()["rowsCount"] == 2
    repro = client.post(f"/api/v1/runs/{april.json()['id']}/reprocess",
                        json={"reason":"Verificar reproceso", "expectedVersion":1},
                        headers={"Idempotency-Key":str(uuid4())})
    drain(app, settings)
    assert get_run(client,repro)["status"] == "completed"
    assert client.get("/api/v1/data/501", params={"runId": annual["id"]}).json() == snapshot
    assert client.get("/api/v1/data/501").json()["total"] == 2
    assert client.get(f"/api/v1/runs/{annual['id']}").json()["exportDocumentId"] == annual["exportDocumentId"]

def test_unknown_table_keeps_previous_period_version(system):
    app, client, settings = system
    previous = upload(client)
    drain(app, settings)
    candidate = upload(client, {"novel_999.asc":"Codigo|FechaNueva|\nABC|2026-04-20|"})
    drain(app, settings)
    result = get_run(client, candidate)
    assert result["status"] == "needs_attention", result
    assert result["publicationStatus"] == "awaiting_schema"
    assert result["exportStatus"] == "ready"
    assert client.get("/api/v1/periods").json()[0]["activeRunId"] == previous.json()["id"]

@pytest.mark.parametrize("name", ["../escape.asc", "/absolute.asc", "C:/outside.asc", "nested.zip"])
def test_unsafe_zip_rejected_before_publication(system,name):
    app, client, settings = system
    response = upload(client,{name:ASC})
    drain(app,settings)
    result=get_run(client,response)
    assert result["status"]=="failed",result
    assert result["publicationStatus"]=="rejected"
    assert client.get("/api/v1/data/501").json()["total"]==0

def test_exact_duplicate_files_are_not_double_loaded(system):
    app,client,settings=system
    response=upload(client,{"a_501.asc":ASC,"b_501.asc":ASC})
    drain(app,settings)
    result=get_run(client,response)
    assert result["counts"]["receivedFiles"]==2
    assert result["counts"]["skippedFiles"]==1
    assert result["counts"]["rows"]==1
    assert result["counts"]["warnings"]==1

def test_cross_scope_and_operator_authorization(system):
    app,client,settings=system
    response=upload(client)
    drain(app,settings)
    app.dependency_overrides[current_principal]=lambda: Principal("other","Other",frozenset({"Reader"}),"elsewhere")
    assert client.get(f"/api/v1/runs/{response.json()['id']}").status_code==404
    assert client.get("/api/v1/runs").json()["total"]==0
    assert client.get("/api/v1/data/501").json()["total"]==0
    assert upload(client).status_code==403

def test_lease_fencing_prevents_stale_worker(system):
    app,client,settings=system
    assert upload(client).status_code == 202
    first=claim_job(app.state.session_factory,settings,"first")
    assert first
    with app.state.session_factory() as session:
        session.execute(update(Job).where(Job.id==first.id).values(lease_until=first.lease_until-timedelta(hours=1)))
        session.commit()
    second=claim_job(app.state.session_factory,settings,"second")
    assert second.fence>first.fence
    with app.state.session_factory() as session:
        with pytest.raises(Exception,match="reservado"):
            job_guard(session,first.id,"first",first.fence,settings)

def test_auto_annual_is_dispatched_after_month_publication(system):
    app,client,settings=system
    settings.auto_annual=True
    assert upload(client).status_code == 202
    drain(app,settings)
    rows=client.get("/api/v1/runs").json()["items"]
    assert len(rows)==2
    annual=next(row for row in rows if row["kind"]=="annual")
    assert annual["status"]=="completed",annual
    assert annual["rangeName"]=="Ene-Abr"

def test_unconfigured_foundry_is_explicit_and_no_mock_answer(system):
    _,client,_=system
    response=client.post("/api/v1/agent/conversations")
    assert response.status_code==503
    assert response.json()["title"]=="FOUNDRY_NOT_CONFIGURED"

def test_annual_registered_asc_direct_input(system):
    app,client,settings=system
    file=client.post("/api/v1/source-files",data={"periodo":"Abril_2026"},
                     files={"content":("demo_501.asc",ASC.encode(),"text/plain")})
    assert file.status_code==201,file.text
    source={k:file.json()[k] for k in ("documentId","fileName","periodo","tableCode")}
    response=client.post("/api/v1/annual-runs",json={"anio":2026,"rangoNombre":"Ene-Abr","files":[source]},
                         headers={"Idempotency-Key":str(uuid4())})
    drain(app,settings)
    result=get_run(client,response)
    assert result["status"]=="completed",result
    assert client.get("/api/v1/data/501",params={"runId":result["id"]}).json()["total"]==1
    assert client.get("/api/v1/data/501").json()["total"]==0


def test_concurrent_publications_keep_one_version_and_clean_orphans(system):
    from app.persistence.models import StoredDocument
    app, client, settings = system
    first = upload(client, {"one_501.asc": ASC})
    second = upload(client, {"two_501.asc": ASC.replace("0000009", "0000010")})
    assert first.status_code == second.status_code == 202
    drain(app, settings)
    results = [get_run(client, response) for response in (first, second)]
    assert sorted(run["status"] for run in results) == ["completed", "failed"]
    assert client.get("/api/v1/data/501").json()["total"] == 1
    with app.state.session_factory() as session:
        references = set(session.scalars(select(StoredDocument.storage_key)))
    assert {path.name for path in settings.document_root.iterdir()} == references


def test_export_retry_keeps_business_rows_and_removes_partial_file(system, monkeypatch):
    import app.worker as worker
    from app.persistence.models import StoredDocument, utcnow
    app, client, settings = system
    response = upload(client)
    assert worker.run_once(app.state.session_factory, settings, app.state.storage)
    real_export = worker.export_xlsx
    def interrupted(result, target):
        target.write_bytes(b"partial")
        raise OSError("test interrupted write")
    monkeypatch.setattr(worker, "export_xlsx", interrupted)
    assert worker.run_once(app.state.session_factory, settings, app.state.storage)
    result = get_run(client, response)
    assert result["publicationStatus"] == "published"
    assert result["phase"] == "retry_pending"
    with app.state.session_factory() as session:
        session.execute(update(Job).where(Job.kind == "export").values(available_at=utcnow() - timedelta(seconds=1)))
        session.commit()
    monkeypatch.setattr(worker, "export_xlsx", real_export)
    drain(app, settings)
    assert get_run(client, response)["exportStatus"] == "ready"
    with app.state.session_factory() as session:
        table = get_business_table("501")
        assert session.scalar(select(func.count()).select_from(table)) == 1
        references = set(session.scalars(select(StoredDocument.storage_key)))
    assert {path.name for path in settings.document_root.iterdir()} == references


def test_annual_data_matches_own_date_policy_and_range(system):
    app, client, settings = system
    assert upload(client, {"one_501.asc": ASC.replace("2026-04-20 13:14:15", "04/05/2026")}).status_code == 202
    drain(app, settings)
    assert upload(client, period="Mayo_2026").status_code == 202
    drain(app, settings)
    assert client.get("/api/v1/data/501", params={"period": "Abril_2026"}).json()["items"][0]["FechaPagoReal"] == "2026-05-04T00:00:00"
    settings.ambiguous_date_order = "MDY"
    response = client.post("/api/v1/annual-runs", json={"anio": 2026, "rangoNombre": "Ene-Abr"},
                           headers={"Idempotency-Key": str(uuid4())})
    drain(app, settings)
    result = get_run(client, response)
    page = client.get("/api/v1/data/501", params={"runId": result["id"]}).json()
    assert page["total"] == 1
    assert page["items"][0]["FechaPagoReal"] == "2026-04-05T00:00:00"


def test_table_code_is_case_insensitive(system):
    app, client, settings = system
    assert upload(client, {"one_sel.asc": "Rfc|FechaSeleccion|\nPRUEBA|2026-04-01|"}).status_code == 202
    drain(app, settings)
    lower = client.get("/api/v1/data/sel")
    upper = client.get("/api/v1/data/SEL")
    assert lower.status_code == upper.status_code == 200
    assert lower.json() == upper.json()
