from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.modules.identity.auth import Principal
from app.modules.processing.service import create_annual, create_monthly, json_text, run_response
from app.modules.storage.filesystem import FileSystemStorage
from app.persistence import Base, make_engine, session_factory
from app.persistence.models import Issue, Job, OutboxMessage, Period, Run, StoredDocument, utcnow
from app.worker import _read_source_document, claim_job, dispatch_outbox, fail_job, inputs_for_run, job_guard


@pytest.fixture
def context(tmp_path):
    settings = Settings(environment="test", database_url=f"sqlite:///{(tmp_path / 'review.db').as_posix()}",
                        document_root=tmp_path / "documents", auto_annual=False, job_lease_seconds=30)
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    factory = session_factory(engine)
    store = FileSystemStorage(settings.document_root)
    yield factory, settings, store
    engine.dispose()


def seed_job(factory, *, expired=False, kind="process", publication="pending"):
    with factory() as session:
        run = Run(id=str(uuid4()), scope_id="local", year=2026,
                  input_fingerprint=uuid4().hex, publication_status=publication)
        session.add(run)
        session.flush()
        job = Job(id=str(uuid4()), run_id=run.id, kind=kind, status="running", attempts=1,
                  lease_owner="original", fence=1,
                  lease_until=utcnow() + timedelta(seconds=-60 if expired else 30))
        session.add(job)
        session.commit()
        return run, job


def seed_month(factory, month=4, *, replace_period=None):
    with factory() as session:
        period = session.get(Period, replace_period) if replace_period else Period(
            id=str(uuid4()), scope_id="local", year=2026, month=month, name="Abril_2026" if month == 4 else "Mayo_2026")
        if not replace_period:
            session.add(period)
            session.flush()
        run = Run(id=str(uuid4()), scope_id="local", year=2026, period_id=period.id,
                  kind="monthly", publication_status="published", status="completed", input_fingerprint=uuid4().hex)
        session.add(run)
        session.flush()
        period.active_run_id = run.id
        period.version += 1
        session.commit()
        return run, period


def test_expired_lease_cannot_be_renewed_or_fail_current_run(context):
    factory, settings, _ = context
    run, job = seed_job(factory, expired=True)
    with factory() as session:
        with pytest.raises(ApplicationError) as caught:
            job_guard(session, job.id, job.lease_owner, job.fence, settings)
        assert caught.value.code == "LEASE_LOST"
    fail_job(factory, settings, job, ValueError("stale failure"))
    with factory() as session:
        assert session.get(Job, job.id).status == "running"
        assert session.get(Run, run.id).status == "queued"
    reclaimed = claim_job(factory, settings, "new-owner")
    assert reclaimed.fence == 2
    assert reclaimed.lease_owner == "new-owner"


def test_transient_retry_then_permanent_failure_records_diagnostics(context):
    factory, settings, _ = context
    run, job = seed_job(factory)
    fail_job(factory, settings, job, OSError("temporary disk failure"))
    with factory() as session:
        retry = session.get(Job, job.id)
        assert retry.status == "pending"
        assert retry.available_at > utcnow()
        assert retry.lease_owner is None
        assert session.get(Run, run.id).phase == "retry_pending"
        session.execute(update(Job).where(Job.id == job.id).values(available_at=utcnow() - timedelta(seconds=1)))
        session.commit()
    retry = claim_job(factory, settings, "second-owner")
    assert retry.attempts == 2
    fail_job(factory, settings, retry, ValueError("deterministic problem"))
    with factory() as session:
        assert session.get(Job, job.id).status == "failed"
        assert session.get(Run, run.id).publication_status == "rejected"
        assert session.scalar(select(Issue).where(Issue.run_id == run.id)).code == "WORKER_FAILURE"


def test_failed_export_preserves_published_data(context):
    factory, settings, _ = context
    run, job = seed_job(factory, kind="export", publication="published")
    fail_job(factory, settings, job, ValueError("invalid Excel width"))
    with factory() as session:
        current = session.get(Run, run.id)
        assert current.publication_status == "published"
        assert current.export_status == "failed"


def test_annual_retry_preserves_initial_snapshot_after_month_replaced(context):
    factory, settings, _ = context
    old, period = seed_month(factory)
    principal = Principal("operator", "Operator", frozenset({"Operator"}), "local")
    with factory() as session:
        first = create_annual(session, settings, principal, "annual-request", 2026, "Ene-Abr")
        session.commit()
    new, _ = seed_month(factory, replace_period=period.id)
    settings.ambiguous_date_order = "MDY"
    with factory() as session:
        replay = create_annual(session, settings, principal, "annual-request", 2026, "Ene-Abr")
        assert replay.id == first.id
        assert old.id in replay.source_manifest_json
        assert new.id not in replay.source_manifest_json
        another = create_annual(session, settings, principal, "new-annual-request", 2026, "Ene-Abr")
        session.commit()
        assert another.id != first.id
        assert new.id in another.source_manifest_json


def test_monthly_retry_does_not_reinterpret_changed_configuration(context):
    factory, settings, store = context
    principal = Principal("operator", "Operator", frozenset({"Operator"}), "local")
    saved = store.put_bytes(b"placeholder-zip", ".zip")
    with factory() as session:
        first = create_monthly(session, settings, principal, "monthly-request", "Abril_2026", "a.zip", saved)
        session.commit()
    settings.ambiguous_date_order = "MDY"
    with factory() as session:
        replay = create_monthly(session, settings, principal, "monthly-request", "Abril_2026", "a.zip", saved)
        assert replay.id == first.id
        assert '"DMY"' in replay.options_json


def test_outbox_integrity_race_remains_pending_and_replays(context, monkeypatch):
    factory, settings, _ = context
    run, _ = seed_month(factory)
    with factory() as session:
        message = OutboxMessage(id=str(uuid4()), run_id=run.id, event_type="monthly.published")
        session.add(message)
        session.commit()
    import app.worker as worker
    original = worker.create_annual
    def race(*args, **kwargs):
        raise IntegrityError("simulated concurrent fingerprint insert", {}, Exception("unique conflict"))
    monkeypatch.setattr(worker, "create_annual", race)
    dispatch_outbox(factory, settings)
    with factory() as session:
        assert session.get(OutboxMessage, message.id).status == "pending"
    monkeypatch.setattr(worker, "create_annual", original)
    dispatch_outbox(factory, settings)
    with factory() as session:
        assert session.get(OutboxMessage, message.id).status == "dispatched"
        assert session.scalar(select(Run).where(Run.kind == "annual")) is not None


def test_annual_size_preflight_occurs_before_any_document_access(context):
    factory, settings, _ = context
    settings.max_extracted_mb = 1
    with factory() as session:
        documents = [StoredDocument(id=str(uuid4()), scope_id="local", kind="asc", original_name=f"{i}_501.asc",
                                    storage_key=f"missing-{i}.asc", sha256="a" * 64, size_bytes=600_000)
                     for i in range(2)]
        session.add_all(documents)
        session.commit()
    run = SimpleNamespace(scope_id="local", options_json='{"encoding":"utf-8-sig"}',
                          source_manifest_json=json_text([{"documentId": doc.id, "fileName": doc.original_name,
                                                          "period": "Abril_2026"} for doc in documents]))
    class NoReadStore:
        def resolve(self, key):
            raise AssertionError("Document accessed before aggregate preflight")
    with pytest.raises(ApplicationError) as caught:
        inputs_for_run(factory, NoReadStore(), settings, run)
    assert caught.value.code == "SOURCE_SIZE_LIMIT"


def test_source_reader_enforces_actual_size_and_hash(context):
    _, _, store = context
    stored = store.put_bytes(b"12345678", ".asc")
    document = SimpleNamespace(**stored)
    assert _read_source_document(store, document, 8) == b"12345678"
    with pytest.raises(ApplicationError) as caught:
        _read_source_document(store, document, 7)
    assert caught.value.code == "SOURCE_SIZE_LIMIT"
    store.resolve(document.storage_key).write_bytes(b"12345679")
    with pytest.raises(ApplicationError) as caught:
        _read_source_document(store, document, 8)
    assert caught.value.code == "SOURCE_INTEGRITY_ERROR"


def test_initial_run_response_has_exhaustive_zero_counts(context):
    factory, _, _ = context
    run, _ = seed_job(factory)
    with factory() as session:
        counts = run_response(session, session.get(Run, run.id))["counts"]
    assert counts == {"receivedFiles": 0, "processedFiles": 0, "skippedFiles": 0, "failedFiles": 0,
                      "processedTables": 0, "rows": 0, "warnings": 0, "errors": 0}
