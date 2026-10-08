"""Adversarial integration checks for authorization boundaries and archive intake."""
from datetime import datetime, timedelta, timezone
import stat
from types import SimpleNamespace
from uuid import uuid4
import zipfile

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import jwt
import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.main import create_app
from app.modules.identity import auth
from app.modules.identity.auth import Principal, current_principal
from app.modules.ingestion.zip_reader import read_zip, scan_document
from app.persistence.models import Conversation, Period, Run, StoredDocument


@pytest.fixture
def local_app(tmp_path):
    settings = Settings(_env_file=None, environment="test", database_url="sqlite://",
                        document_root=tmp_path / "documents", auto_annual=False,
                        max_upload_mb=1, max_file_mb=1,
                        foundry_enabled=True,
                        foundry_project_endpoint="https://example.services.ai.azure.com/api/projects/test")
    app = create_app(settings)
    app.dependency_overrides[current_principal] = lambda: Principal(
        "reviewer", "Security reviewer", frozenset({"Reader"}), "authorized"
    )
    with TestClient(app) as client:
        yield app, client


def seed_run(app, scope):
    with app.state.session_factory.begin() as session:
        period = Period(scope_id=scope, year=2026, month=4, name="Abril_2026")
        session.add(period)
        session.flush()
        run = Run(scope_id=scope, period_id=period.id, year=2026,
                  input_fingerprint=uuid4().hex * 2, status="completed", publication_status="published")
        session.add(run)
        session.flush()
        period.active_run_id = run.id
        run_id = run.id
    return run_id


@pytest.mark.parametrize("suffix", ["", "/files", "/tables", "/issues", "/control"])
def test_run_resources_do_not_disclose_another_scope(local_app, suffix):
    app, client = local_app
    foreign_id = seed_run(app, "foreign")
    reply = client.get(f"/api/v1/runs/{foreign_id}{suffix}")
    assert reply.status_code == 404
    assert reply.json()["title"] == "RUN_NOT_FOUND"
    assert reply.headers["x-correlation-id"]
    assert reply.headers["cache-control"] == "no-store"


def test_run_period_and_report_lists_filter_scope(local_app):
    app, client = local_app
    authorized_id = seed_run(app, "authorized")
    foreign_id = seed_run(app, "foreign")
    response = client.get("/api/v1/runs").json()
    assert response["total"] == 1
    assert [run["id"] for run in response["items"]] == [authorized_id]
    periods = client.get("/api/v1/periods").json()
    assert len(periods) == 1
    assert periods[0]["activeRunId"] == authorized_id
    report = client.get("/api/v1/reports/overview").json()
    assert report["runsCount"] == 1
    assert foreign_id not in str(report)


def test_document_and_data_access_cannot_switch_scope(local_app):
    app, client = local_app
    foreign_id = seed_run(app, "foreign")
    with app.state.session_factory.begin() as session:
        doc = StoredDocument(scope_id="foreign", run_id=foreign_id, kind="excel", original_name="private.xlsx",
                             storage_key="private.xlsx", sha256="a" * 64, size_bytes=5)
        session.add(doc)
        session.flush()
        document_id = doc.id
    assert client.get(f"/api/v1/documents/{document_id}/download").status_code == 404
    assert client.get("/api/v1/data/501", params={"runId": foreign_id}).status_code == 404


def test_reader_cannot_create_annual_reprocess_or_read_audit(local_app):
    app, client = local_app
    own_id = seed_run(app, "authorized")
    headers = {"Idempotency-Key": "security-review-123"}
    assert client.post("/api/v1/annual-runs", headers=headers,
                       json={"anio": 2026, "rangoNombre": "Ene-Abr"}).status_code == 403
    assert client.post(f"/api/v1/runs/{own_id}/reprocess", headers=headers,
                       json={"reason": "Intento sin permiso", "expectedVersion": 0}).status_code == 403
    assert client.post(f"/api/v1/runs/{own_id}/exports", headers=headers).status_code == 403
    assert client.get("/api/v1/audit").status_code == 403


def test_reader_upload_is_rejected_before_document_storage(local_app, monkeypatch):
    app, client = local_app
    from unittest.mock import AsyncMock
    upload = AsyncMock()
    monkeypatch.setattr(app.state.storage, "put_upload", upload)
    reply = client.post("/api/v1/monthly-runs", headers={"Idempotency-Key": "security-review-456"},
                        data={"periodo": "Abril_2026"}, files={"zip": ("source.zip", b"notzip", "application/zip")})
    assert reply.status_code == 403
    upload.assert_not_awaited()


@pytest.mark.parametrize("scope,user", [("foreign", "reviewer"), ("authorized", "another-user")])
def test_conversations_are_bound_to_both_scope_and_owner(local_app, scope, user):
    app, client = local_app
    with app.state.session_factory.begin() as session:
        conversation = Conversation(scope_id=scope, user_id=user)
        session.add(conversation)
        session.flush()
        conversation_id = conversation.id
    response = client.post(f"/api/v1/agent/conversations/{conversation_id}/messages", json={"message": "Read prior conversation"})
    assert response.status_code == 404
    assert response.json()["title"] == "CONVERSATION_NOT_FOUND"


def test_agent_callback_uses_authenticated_scope_even_for_remote_tool_call(local_app, monkeypatch):
    app, client = local_app
    foreign_id = seed_run(app, "foreign")
    with app.state.session_factory.begin() as session:
        conversation = Conversation(scope_id="authorized", user_id="reviewer")
        session.add(conversation)
        session.flush()
        conversation_id = conversation.id

    def injected_model_response(self, history, execute_tool, language='es'):
        return execute_tool("get_run", {"runId": foreign_id, "scope_id": "foreign"}, "call-test")

    monkeypatch.setattr("app.modules.foundry.FoundryAgent.respond", injected_model_response)
    reply = client.post(f"/api/v1/agent/conversations/{conversation_id}/messages", json={"message": "Read a run"})
    assert reply.status_code == 404
    assert reply.json()["title"] == "RUN_NOT_FOUND"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token_request(token, settings):
    app = SimpleNamespace(state=SimpleNamespace(settings=settings))
    return Request({"type": "http", "app": app, "client": ("127.0.0.1", 8000),
                    "headers": [(b"authorization", ("Bearer " + token).encode())]})


def identity_settings():
    return Settings(_env_file=None, environment="test", auth_mode="entra", scope_id="corporate",
                    entra_tenant_id="test-tenant", entra_client_id="spa-client",
                    entra_audience="api-audience", entra_api_scope="api://api-audience/access_as_user")


def claims():
    now = datetime.now(timezone.utc)
    return {"iss": "https://login.microsoftonline.com/test-tenant/v2.0", "aud": "api-audience",
            "tid": "test-tenant", "sub": "sub-user", "oid": "oid-user", "iat": now,
            "exp": now + timedelta(minutes=5), "roles": ["Reader"], "scope_id": "injected",
            "scp": "access_as_user"}


def test_entra_token_scope_cannot_override_deployment_scope(monkeypatch, signing_key):
    monkeypatch.setattr(auth, "jwks_client", lambda _: SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=signing_key.public_key())))
    token = jwt.encode(claims(), signing_key, algorithm="RS256")
    principal = auth.current_principal(token_request(token, identity_settings()))
    assert principal.scope_id == "corporate"
    assert principal.roles == frozenset({"Reader"})
    assert principal.id == "oid-user"


@pytest.mark.parametrize("patch", [
    {"aud": "another-api"}, {"iss": "https://untrusted.invalid"}, {"tid": "another-tenant"},
    {"exp": datetime(2020, 1, 1, tzinfo=timezone.utc)}, {"roles": ["UnrecognizedRole"]},
    {"scp": None}, {"scp": "other_scope"}, {"scp": ["access_as_user"]},
    {"scp": "prefix_access_as_user"},
])
def test_entra_rejects_invalid_identity_claims(monkeypatch, signing_key, patch):
    monkeypatch.setattr(auth, "jwks_client", lambda _: SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=signing_key.public_key())))
    token = jwt.encode({**claims(), **patch}, signing_key, algorithm="RS256")
    with pytest.raises(ApplicationError) as error:
        auth.current_principal(token_request(token, identity_settings()))
    assert error.value.status in {401, 403}


def test_development_identity_rejects_non_loopback_client():
    app = SimpleNamespace(state=SimpleNamespace(settings=Settings(_env_file=None)))
    request = Request({"type": "http", "app": app, "client": ("192.0.2.4", 8000), "headers": []})
    with pytest.raises(ApplicationError) as error:
        auth.current_principal(request)
    assert error.value.code == "LOCAL_ONLY"


def zip_at(tmp_path, name, payload=b"A|B\n1|2", *, special_mode=None):
    path = tmp_path / "sample.zip"
    entry = zipfile.ZipInfo(name)
    if special_mode is not None:
        entry.create_system = 3
        entry.external_attr = special_mode << 16
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry, payload, compress_type=zipfile.ZIP_DEFLATED)
    return path


@pytest.mark.parametrize("name", ["../evil.asc", "/root/evil.asc", "C:/evil.asc", "folder/../../evil.asc", "nested.zip", "payload.exe"])
def test_archive_rejects_paths_and_non_asc_payloads(tmp_path, name):
    path = zip_at(tmp_path, name)
    with pytest.raises(ApplicationError) as error:
        list(read_zip(path, Settings(_env_file=None)))
    assert error.value.status == 422


def test_archive_rejects_symlinks(tmp_path):
    path = zip_at(tmp_path, "link.asc", b"../../target", special_mode=stat.S_IFLNK | 0o777)
    with pytest.raises(ApplicationError) as error:
        list(read_zip(path, Settings(_env_file=None)))
    assert error.value.code == "ZIP_LINK_REJECTED"


def test_archive_rejects_declared_size_and_compression_ratio(tmp_path):
    path = zip_at(tmp_path, "large.asc", b"0" * (1024 * 1024 + 1))
    with pytest.raises(ApplicationError) as error:
        list(read_zip(path, Settings(_env_file=None, max_file_mb=1)))
    assert error.value.code == "ASC_SIZE_LIMIT"
    with pytest.raises(ApplicationError) as error:
        list(read_zip(path, Settings(_env_file=None, max_compression_ratio=2)))
    assert error.value.code == "ZIP_RATIO_LIMIT"


def test_archive_keeps_raw_content_and_relative_name(tmp_path):
    raw = b"\xef\xbb\xbfPatente|Pedimento|FechaPagoReal|\r\n0036|0000009|bad-date|"
    path = zip_at(tmp_path, "folder/request_501.asc", raw)
    assert list(read_zip(path, Settings(_env_file=None))) == [("folder/request_501.asc", raw)]


def test_antivirus_nonzero_status_is_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("app.modules.ingestion.zip_reader.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=1))
    settings = Settings(_env_file=None, antivirus_command=["approved-scanner"])
    with pytest.raises(ApplicationError) as error:
        scan_document(tmp_path / "file.asc", settings)
    assert error.value.code == "SCAN_REJECTED"


def test_production_rejects_unsecured_local_defaults():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")


def test_chunked_multipart_is_rejected_before_file_parsing_and_storage(local_app, monkeypatch):
    """The global body cap must cover absent Content-Length, before endpoint upload handling."""
    app, client = local_app
    from unittest.mock import AsyncMock
    app.state.settings.max_upload_mb = 1
    app.state.settings.max_file_mb = 1
    app.dependency_overrides[current_principal] = lambda: Principal(
        "operator", "Operator", frozenset({"Reader", "Operator"}), "authorized"
    )
    upload = AsyncMock(side_effect=AssertionError("Oversized body reached endpoint storage"))
    monkeypatch.setattr(app.state.storage, "put_upload", upload)
    prefix = (b"--security-boundary\r\nContent-Disposition: form-data; name=\"periodo\"\r\n\r\nAbril_2026\r\n"
              b"--security-boundary\r\nContent-Disposition: form-data; name=\"zip\"; filename=\"input.zip\"\r\n"
              b"Content-Type: application/zip\r\n\r\n")
    chunks = iter([prefix, b"0" * (3 * 1024 * 1024), b"\r\n--security-boundary--\r\n"])
    reply = client.post("/api/v1/monthly-runs", content=chunks,
                        headers={"Content-Type": "multipart/form-data; boundary=security-boundary",
                                 "Transfer-Encoding": "chunked", "Idempotency-Key": "chunked-security-123"})
    assert reply.status_code == 413
    upload.assert_not_awaited()
