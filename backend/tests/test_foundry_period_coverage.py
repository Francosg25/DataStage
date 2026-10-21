"""Availability must come from active monthly publications, not annual ranges."""
from datetime import datetime
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.modules.identity.auth import Principal, current_principal
from app.persistence.models import Period, Run

MONTHS = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
          "Septiembre", "Octubre", "Noviembre", "Diciembre")


@pytest.fixture
def system(tmp_path):
    app = create_app(Settings(_env_file=None, environment="test", database_url="sqlite://",
                             document_root=tmp_path / "documents", auto_annual=False,
                             foundry_enabled=True,
                             foundry_project_endpoint="https://example.services.ai.azure.com/api/projects/test"))
    app.dependency_overrides[current_principal] = lambda: Principal(
        "reader", "Reader", frozenset({"Reader"}), "authorized")
    with TestClient(app) as client:
        yield app, client


def monthly(session, year, month, *, scope="authorized", published=True, active=True):
    period = Period(scope_id=scope, year=year, month=month, name=f"{MONTHS[month - 1]}_{year}")
    session.add(period)
    session.flush()
    run = Run(scope_id=scope, kind="monthly", period_id=period.id, year=year,
              input_fingerprint=uuid4().hex * 2, status="completed",
              publication_status="published" if published else "pending", created_at=datetime(2026, 10, 1))
    session.add(run)
    session.flush()
    period.active_run_id = run.id if active else None
    return period, run


def annual(session):
    row = Run(scope_id="authorized", kind="annual", year=2025, range_name="Enero - Julio",
              input_fingerprint=uuid4().hex * 2, status="completed", publication_status="published",
              created_at=datetime(2026, 10, 2), options_json=json.dumps({"consolidation_range": {
                  "start_year": 2025, "start_month": 1, "end_year": 2025, "end_month": 7}}))
    session.add(row)
    session.flush()
    return row.id


def query_coverage(client, monkeypatch, limit=1):
    captured = {}

    def model(self, history, execute_tool, language="es"):
        result = execute_tool("list_runs", {"limit": limit}, "coverage-test")
        captured.update(result)
        return {"message": "Read from verified monthly coverage", "evidence": result["evidence"]}

    monkeypatch.setattr("app.modules.foundry.FoundryAgent.respond", model)
    conversation = client.post("/api/v1/agent/conversations").json()["id"]
    response = client.post(f"/api/v1/agent/conversations/{conversation}/messages",
                           json={"message": "Which months are available?", "language": "en"})
    assert response.status_code == 200
    return captured


def test_may_and_june_are_not_expanded_to_the_annual_january_july_range(system, monkeypatch):
    app, client = system
    with app.state.session_factory.begin() as session:
        monthly(session, 2025, 5)
        monthly(session, 2025, 6)
        monthly(session, 2026, 9)
        annual_id = annual(session)
    result = query_coverage(client, monkeypatch)
    assert [row["id"] for row in result["data"]["items"]] == [annual_id]
    coverage = result["data"]["publishedPeriodCoverage"]
    assert coverage["source"] == "published" and coverage["complete"] is True
    assert coverage["basis"] == "active_published_monthly_runs"
    assert coverage["years"] == [{"year": 2026, "months": [9]}, {"year": 2025, "months": [5, 6]}]
    assert coverage["annualRangesRepresentCoverage"] is False
    assert result["evidence"][0]["publishedPeriodCoverage"] == coverage


def test_coverage_excludes_foreign_unpublished_inactive_and_replaced_publications(system, monkeypatch):
    app, client = system
    with app.state.session_factory.begin() as session:
        monthly(session, 2025, 5)
        monthly(session, 2025, 6)
        _, foreign = monthly(session, 2025, 1, scope="foreign")
        monthly(session, 2025, 2, published=False)
        monthly(session, 2025, 3, active=False)
        period, _ = monthly(session, 2025, 7)
        replacement = Run(scope_id="authorized", kind="monthly", period_id=period.id, year=2025,
                          input_fingerprint=uuid4().hex * 2, publication_status="pending")
        session.add(replacement)
        session.flush()
        period.active_run_id = replacement.id
        corrupted = Period(scope_id="authorized", year=2025, month=8, name="Agosto_2025", active_run_id=foreign.id)
        session.add(corrupted)
        annual(session)
    result = query_coverage(client, monkeypatch, limit=100)
    assert result["data"]["publishedPeriodCoverage"]["years"] == [{"year": 2025, "months": [5, 6]}]
    assert all(row["period"] != "Enero_2025" for row in result["data"]["items"])


def test_an_annual_run_alone_does_not_claim_any_published_month(system, monkeypatch):
    app, client = system
    with app.state.session_factory.begin() as session:
        annual(session)
    result = query_coverage(client, monkeypatch)
    assert len(result["data"]["items"]) == 1
    assert result["data"]["publishedPeriodCoverage"]["years"] == []
    assert result["data"]["publishedPeriodCoverage"]["complete"] is True
