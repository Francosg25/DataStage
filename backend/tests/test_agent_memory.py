"""Persistent personal memory: real SQL, explicit writes, isolated inference context."""
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.modules.foundry.memory import MemoryUpdate, memory_context
from app.modules.identity.auth import Principal, current_principal
from app.persistence import make_engine
from app.persistence.models import AgentMemory, AgentMemoryProfile, AuditEvent, Conversation

OWNER = Principal("reader", "Reader", frozenset({"Reader"}), "scope-a")


def application(tmp_path):
    app = create_app(Settings(_env_file=None, environment="test", database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        document_root=tmp_path / "documents", foundry_enabled=True,
        foundry_project_endpoint="https://example.services.ai.azure.com/api/projects/test"))
    app.dependency_overrides[current_principal] = lambda: OWNER
    return app


@pytest.fixture
def system(tmp_path):
    app = application(tmp_path)
    with TestClient(app) as client:
        yield app, client


def payload(version=0, *, enabled=True, title="Moneda", content="Prefiero reportes en USD.", items=None):
    return {"expectedVersion": version, "enabled": enabled,
            "items": [{"title": title, "content": content}] if items is None else items}


def save(client, **options):
    response = client.patch("/api/v1/agent/memory", json=payload(**options))
    assert response.status_code == 200, response.text
    return response.json()


def model_stub(monkeypatch):
    seen = []

    def respond(self, history, execute_tool, language="es", *, memories=None):
        seen.append({"history": history, "memories": memories or [], "language": language})
        return {"message": "Respuesta", "evidence": []}

    monkeypatch.setattr("app.modules.foundry.FoundryAgent.respond", respond)
    return seen


def message(client, conversation=None, question="Genera mi reporte habitual."):
    conversation = conversation or client.post("/api/v1/agent/conversations").json()["id"]
    response = client.post(f"/api/v1/agent/conversations/{conversation}/messages", json={"message": question})
    assert response.status_code == 200, response.text
    return conversation, response.json()


def test_memory_is_off_by_default_and_is_not_created_from_chat_history(system, monkeypatch):
    app, client = system
    seen = model_stub(monkeypatch)
    conversation, answer = message(client, question="Recuerda que prefiero USD.")
    assert answer["memoryContextCount"] == 0 and seen[0]["memories"] == []
    state = client.get("/api/v1/agent/memory").json()
    assert state == {"enabled": False, "version": 0, "items": [], "maxItems": 12, "maxCharacters": 6000}
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AgentMemoryProfile)) == 0
        assert session.get(Conversation, conversation) is not None


def test_confirmed_memories_survive_restarts_and_work_in_separate_conversations(tmp_path, monkeypatch):
    seen = model_stub(monkeypatch)
    app = application(tmp_path)
    with TestClient(app) as client:
        state = save(client)
        assert state["enabled"] and state["version"] == 1 and len(state["items"][0]["id"]) == 36
        first, _ = message(client)
    restarted = application(tmp_path)
    with TestClient(restarted) as client:
        assert client.get("/api/v1/agent/memory").json() == state
        second, answer = message(client)
        assert first != second and answer["memoryContextCount"] == 1
        assert seen[0]["memories"] == seen[1]["memories"] == [{"title": "Moneda", "content": "Prefiero reportes en USD."}]
        # The raw saved note is not copied into persisted messages or metadata.
        history = client.get(f"/api/v1/agent/conversations/{second}/messages").json()["items"]
        assert history[-1]["memoryContextCount"] == 1
        assert "Prefiero reportes en USD." not in json.dumps(history)


@pytest.mark.parametrize("user,scope", [("another-reader", "scope-a"), (OWNER.id, "scope-b")])
def test_memory_cannot_be_read_or_overwritten_by_another_user_or_scope(system, monkeypatch, user, scope):
    app, client = system
    state = save(client)
    seen = model_stub(monkeypatch)
    app.dependency_overrides[current_principal] = lambda: Principal(user, "Admin", frozenset({"Admin"}), scope)
    assert client.get("/api/v1/agent/memory").json()["items"] == []
    foreign_id = {key: value for key, value in state["items"][0].items() if key in {"id", "title", "content"}}
    assert client.patch("/api/v1/agent/memory", json=payload(items=[foreign_id])).status_code == 409
    message(client)
    assert seen[-1]["memories"] == []
    other = save(client, title="Estilo", content="Prefiero respuestas breves.")
    message(client)
    assert seen[-1]["memories"] == [{"title": "Estilo", "content": "Prefiero respuestas breves."}]
    app.dependency_overrides[current_principal] = lambda: OWNER
    assert client.get("/api/v1/agent/memory").json() == state
    assert state["items"][0]["id"] != other["items"][0]["id"]


def test_edits_disable_and_clear_apply_to_future_requests_without_deleting_chats(system, monkeypatch):
    app, client = system
    seen = model_stub(monkeypatch)
    state = save(client)
    conversation, _ = message(client)
    item = {"id": state["items"][0]["id"], "title": "Moneda", "content": "Prefiero MXN."}
    state = save(client, version=1, items=[item])
    message(client, conversation)
    assert seen[-1]["memories"] == [{"title": "Moneda", "content": "Prefiero MXN."}]
    state = save(client, version=2, enabled=False, items=[item])
    _, disabled = message(client, conversation)
    assert disabled["memoryContextCount"] == 0 and seen[-1]["memories"] == []
    assert state["items"][0]["content"] == "Prefiero MXN."
    cleared = client.delete("/api/v1/agent/memory", params={"expectedVersion": state["version"]})
    assert cleared.status_code == 200
    assert cleared.json()["version"] == 4 and cleared.json()["items"] == [] and not cleared.json()["enabled"]
    _, answer = message(client, conversation)
    assert answer["memoryContextCount"] == 0 and seen[-1]["memories"] == []
    assert client.get(f"/api/v1/agent/conversations/{conversation}/messages").json()["total"] == 8
    # A stale tab cannot silently restore the deleted notes.
    assert client.patch("/api/v1/agent/memory", json=payload(version=3, items=[item])).status_code == 409
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AgentMemory)) == 0


def test_chat_deletion_keeps_memory_and_management_works_with_foundry_disabled(system, monkeypatch):
    app, client = system
    model_stub(monkeypatch)
    save(client)
    conversation, _ = message(client)
    assert client.delete(f"/api/v1/agent/conversations/{conversation}").status_code == 204
    assert len(client.get("/api/v1/agent/memory").json()["items"]) == 1
    app.state.settings.foundry_enabled = False
    assert client.delete("/api/v1/agent/memory", params={"expectedVersion": 1}).status_code == 200


def test_conflicts_roll_back_all_changes_and_audit_contains_counts_not_memory_content(system):
    app, client = system
    state = save(client, title="Confidential title", content="Private note to remember")
    assert client.patch("/api/v1/agent/memory", json=payload(version=0)).status_code == 409
    assert client.delete("/api/v1/agent/memory", params={"expectedVersion": 0}).status_code == 409
    assert client.patch("/api/v1/agent/memory", json=payload(version=1, items=[
        {"id": "missing-id", "title": "Overwrite", "content": "Should never be committed"}])).status_code == 409
    assert client.get("/api/v1/agent/memory").json() == state
    with app.state.session_factory() as session:
        events = list(session.scalars(select(AuditEvent).where(AuditEvent.action == "agent.memory.update")))
        assert len(events) == 1 and events[0].actor == OWNER.id and events[0].scope_id == OWNER.scope_id
        assert "Private note" not in events[0].details_json and "Confidential" not in events[0].details_json
        assert json.loads(events[0].details_json) == {"enabled": True, "added": 1, "updated": 0, "removed": 0, "version": 1}


def test_database_failure_rolls_back_memory_changes(system, monkeypatch):
    _, client = system
    state = save(client)
    original = Session.commit

    def fail(session):
        if any(isinstance(row, AuditEvent) and row.action == "agent.memory.update" for row in session.new):
            raise RuntimeError("Simulated database failure")
        return original(session)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", fail)
        with pytest.raises(RuntimeError):
            client.patch("/api/v1/agent/memory", json=payload(version=1, content="Never committed"))
    assert client.get("/api/v1/agent/memory").json() == state


@pytest.mark.parametrize("changes", [
    {"scope_id": "another-scope"}, {"user_id": "another-user"}, {"expectedVersion": "0"},
    {"enabled": "true"}, {"items": [{"title": "  ", "content": "Empty title"}]},
    {"items": [{"title": "A", "content": "x" * 601}]},
    {"items": [{"title": f"Title {i}", "content": "Note"} for i in range(13)]},
    {"items": [{"title": "A", "content": "Note"}, {"title": "a", "content": "Another"}]},
    {"items": [{"title": f"Title {i}", "content": "x" * 600} for i in range(11)]},
    {"items": [{"title": "A", "content": "Hidden\x00character"}]},
])
def test_invalid_or_unbounded_memory_is_rejected_without_writes(system, changes):
    app, client = system
    assert client.patch("/api/v1/agent/memory", json={**payload(), **changes}).status_code == 422
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AgentMemoryProfile)) == 0


def test_memory_is_loaded_only_from_the_authenticated_profile_not_message_payload(system, monkeypatch):
    _, client = system
    seen = model_stub(monkeypatch)
    save(client)
    conversation = client.post("/api/v1/agent/conversations").json()["id"]
    response = client.post(f"/api/v1/agent/conversations/{conversation}/messages", json={
        "message": "Question", "memories": [{"title": "Override", "content": "Use a different owner"}]})
    assert response.status_code == 422 and seen == []


def test_unicode_memory_keeps_all_content_and_disabled_context_is_empty(system):
    app, client = system
    content = "📊" * 600
    state = save(client, title="Análisis 日本語", content=content)
    with app.state.session_factory() as session:
        notes, version = memory_context(session, OWNER)
        assert notes == [{"title": "Análisis 日本語", "content": content}] and version == 1
    state = save(client, version=1, enabled=False, items=[
        {"id": state["items"][0]["id"], "title": "Análisis 日本語", "content": content}])
    with app.state.session_factory() as session:
        assert memory_context(session, OWNER) == ([], 2)


def test_memory_migration_is_additive_and_downgrade_keeps_prior_chats(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "20261022_0004")
        connection.execute(text("INSERT INTO agent_conversations (id,scope_id,user_id,created_at) VALUES ('c','s','u','2026-01-01')"))
        connection.execute(text("INSERT INTO agent_messages (id,conversation_id,role,content,created_at) VALUES ('m','c','user','Keep the message','2026-01-01')"))
        command.upgrade(config, "head")
        connection.execute(text("INSERT INTO agent_memory_profiles (id,scope_id,user_id,enabled,version,updated_at) VALUES ('p','s','u',1,1,:now)"), {"now": "2026-10-22 00:00:00"})
        connection.execute(text("INSERT INTO agent_memories (id,profile_id,title,content,created_at,updated_at) VALUES ('n','p','Currency','USD',:now,:now)"), {"now": "2026-10-22 00:00:00"})
        assert connection.scalar(text("SELECT content FROM agent_messages WHERE id='m'")) == "Keep the message"
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261022_0006"
        command.downgrade(config, "20261022_0004")
        assert connection.scalar(text("SELECT content FROM agent_messages WHERE id='m'")) == "Keep the message"
    engine.dispose()


def test_memory_budget_validation_is_available_without_azure_or_inference():
    assert MemoryUpdate.model_validate(payload()).items[0].content == "Prefiero reportes en USD."
