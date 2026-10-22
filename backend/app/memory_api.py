"""Personal memory management. Identity and scope come only from authentication."""
from fastapi import APIRouter, Query

from app.api import DB, Reader, router as api_router
from app.modules.foundry.memory import MemoryResponse, MemoryUpdate, read_memory, replace_memory

router = APIRouter(prefix="/api/v1/agent", responses=api_router.responses)


@router.get("/memory", response_model=MemoryResponse)
def get_memory(session: DB, principal: Reader):
    return read_memory(session, principal)


@router.patch("/memory", response_model=MemoryResponse)
def save_memory(body: MemoryUpdate, session: DB, principal: Reader):
    return replace_memory(session, principal, body)


@router.delete("/memory", response_model=MemoryResponse)
def forget_memory(session: DB, principal: Reader, expectedVersion: int = Query(ge=0, le=2147483646)):
    return replace_memory(session, principal, MemoryUpdate(expectedVersion=expectedVersion, enabled=False, items=[]))
