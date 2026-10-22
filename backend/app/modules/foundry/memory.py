"""Explicit private preferences, stored locally; no automatic extraction or training."""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.modules.processing.service import audit
from app.persistence.models import AgentMemory, AgentMemoryProfile, utcnow

MAX_MEMORIES = 12
MAX_MEMORY_CHARACTERS = 6000


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(default="", max_length=36)
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=600)

    @field_validator("title", "content")
    @classmethod
    def meaningful_text(cls, value):
        value = value.strip()
        if not value or any(ord(character) < 32 and character not in "\n\r\t" for character in value):
            raise ValueError("Escribe texto válido")
        return value


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expectedVersion: int = Field(ge=0, le=2147483646)
    enabled: bool
    items: list[MemoryInput] = Field(max_length=MAX_MEMORIES)

    @model_validator(mode="after")
    def bounded_unique_memories(self):
        ids = [item.id for item in self.items if item.id]
        titles = [item.title.casefold() for item in self.items]
        if len(ids) != len(set(ids)) or len(titles) != len(set(titles)):
            raise ValueError("Las memorias deben tener identificadores y títulos únicos")
        if sum(len(item.title) + len(item.content) for item in self.items) > MAX_MEMORY_CHARACTERS:
            raise ValueError("La memoria supera el límite conjunto de texto")
        return self


class MemoryItemResponse(BaseModel):
    id: str
    title: str
    content: str
    createdAt: str
    updatedAt: str


class MemoryResponse(BaseModel):
    enabled: bool
    version: int
    items: list[MemoryItemResponse]
    maxItems: int = MAX_MEMORIES
    maxCharacters: int = MAX_MEMORY_CHARACTERS


def owner_profile(session, principal):
    return session.scalar(select(AgentMemoryProfile).where(
        AgentMemoryProfile.scope_id == principal.scope_id, AgentMemoryProfile.user_id == principal.id)
        .execution_options(populate_existing=True))


def read_memory(session, principal):
    profile = owner_profile(session, principal)
    if profile is None:
        return {"enabled": False, "version": 0, "items": [], "maxItems": MAX_MEMORIES,
                "maxCharacters": MAX_MEMORY_CHARACTERS}
    items = session.scalars(select(AgentMemory).where(AgentMemory.profile_id == profile.id)
                           .order_by(AgentMemory.created_at, AgentMemory.id))
    return {"enabled": profile.enabled, "version": profile.version, "items": [
        {"id": item.id, "title": item.title, "content": item.content,
         "createdAt": item.created_at.isoformat() + "Z", "updatedAt": item.updated_at.isoformat() + "Z"}
        for item in items], "maxItems": MAX_MEMORIES, "maxCharacters": MAX_MEMORY_CHARACTERS}


def replace_memory(session, principal, body):
    conflict = ApplicationError(409, "MEMORY_CHANGED", "La memoria cambió. Vuelve a abrirla antes de guardar.")
    try:
        profile = owner_profile(session, principal)
        if profile is None:
            if body.expectedVersion != 0 or any(item.id for item in body.items):
                raise conflict
            profile = AgentMemoryProfile(scope_id=principal.scope_id, user_id=principal.id,
                                         version=1, enabled=body.enabled)
            session.add(profile)
            session.flush()
        else:
            result = session.execute(update(AgentMemoryProfile).where(
                AgentMemoryProfile.id == profile.id, AgentMemoryProfile.version == body.expectedVersion)
                .values(version=AgentMemoryProfile.version + 1, enabled=body.enabled, updated_at=utcnow())
                .execution_options(synchronize_session=False))
            if result.rowcount != 1:
                raise conflict
        existing = {item.id: item for item in session.scalars(select(AgentMemory).where(
            AgentMemory.profile_id == profile.id))}
        keep = {item.id for item in body.items if item.id}
        if not keep.issubset(existing):
            raise conflict
        removed, added, changed = 0, 0, 0
        for identifier, item in existing.items():
            if identifier not in keep:
                session.delete(item)
                removed += 1
        for values in body.items:
            if not values.id:
                session.add(AgentMemory(profile_id=profile.id, title=values.title, content=values.content))
                added += 1
            else:
                item = existing[values.id]
                if item.title != values.title or item.content != values.content:
                    item.title, item.content = values.title, values.content
                    changed += 1
        audit(session, principal.scope_id, principal.id, "agent.memory.update",
              enabled=body.enabled, added=added, updated=changed, removed=removed,
              version=body.expectedVersion + 1)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise conflict from error
    except BaseException:
        session.rollback()
        raise
    return read_memory(session, principal)


def memory_context(session, principal):
    state = read_memory(session, principal)
    if not state["enabled"]:
        return [], state["version"]
    # Only this user's confirmed notes enter inference. No history mining and
    # no model-generated memories. Never use notes as operational evidence.
    values = [{"title": item["title"], "content": item["content"]} for item in state["items"]]
    MemoryUpdate(expectedVersion=0, enabled=True, items=values)
    return values, state["version"]
