"""Owner-only chat deletion and retryable cleanup of generated downloads."""
import logging

from sqlalchemy import delete, exists, func, select, update

from app.core.errors import ApplicationError
from app.modules.processing.service import audit
from app.persistence.models import AgentArtifact, AgentMessage, AgentMessageDetail, Conversation, StoredDocument

log = logging.getLogger("datastage.agent")
ARTIFACT_KINDS = ("agent_excel", "agent_pdf")


def own_conversation(session, principal, conversation_id, *, lock=False):
    criteria = (Conversation.id == conversation_id, Conversation.scope_id == principal.scope_id,
                Conversation.user_id == principal.id)
    if lock:
        # A short write lock works on both SQL Server and SQLite. Serialize
        # deletion against tool persistence, without locking during inference.
        result = session.execute(update(Conversation).where(*criteria).values(
            created_at=Conversation.created_at).execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise ApplicationError(404, "CONVERSATION_NOT_FOUND", "No se encontró la conversación")
    # Do not trust an ORM identity cached before another tab deleted the chat.
    row = session.scalar(select(Conversation).where(*criteria).execution_options(populate_existing=True))
    if row is None:
        raise ApplicationError(404, "CONVERSATION_NOT_FOUND", "No se encontró la conversación")
    return row


def delete_conversation(session, principal, conversation_id):
    own_conversation(session, principal, conversation_id, lock=True)
    documents = list(session.scalars(select(StoredDocument).join(
        AgentArtifact, AgentArtifact.document_id == StoredDocument.id).where(
        AgentArtifact.conversation_id == conversation_id)))
    for document in documents:
        if (document.scope_id != principal.scope_id or document.kind not in ARTIFACT_KINDS
                or document.run_id is not None):
            raise ApplicationError(409, "CONVERSATION_DOCUMENT_CONFLICT", "No fue posible eliminar los archivos de esta conversación")
        # Revoke downloads atomically with message deletion. Files locked by
        # OneDrive/another process remain discoverable for a worker retry.
        document.status = "pending_delete"
    messages = select(AgentMessage.id).where(AgentMessage.conversation_id == conversation_id)
    count = session.scalar(select(func.count()).select_from(AgentMessage).where(
        AgentMessage.conversation_id == conversation_id))
    session.execute(delete(AgentMessageDetail).where(AgentMessageDetail.message_id.in_(messages)))
    session.execute(delete(AgentMessage).where(AgentMessage.conversation_id == conversation_id))
    session.execute(delete(AgentArtifact).where(AgentArtifact.conversation_id == conversation_id))
    session.execute(delete(Conversation).where(Conversation.id == conversation_id))
    audit(session, principal.scope_id, principal.id, "agent.conversation.delete",
          conversationId=conversation_id, messages=count, documents=len(documents))
    session.commit()


def cleanup_deleted_artifacts(factory, storage, limit=20):
    """Retry only revoked chat files; never remove operational/shared documents."""
    cleaned = 0
    with factory() as session:
        documents = list(session.scalars(select(StoredDocument).where(
            StoredDocument.status == "pending_delete", StoredDocument.kind.in_(ARTIFACT_KINDS),
            StoredDocument.run_id.is_(None), ~exists().where(AgentArtifact.document_id == StoredDocument.id))
            .order_by(StoredDocument.created_at, StoredDocument.id).limit(limit)))
        for document in documents:
            shared = session.scalar(select(StoredDocument.id).where(
                StoredDocument.storage_key == document.storage_key, StoredDocument.id != document.id).limit(1))
            if shared:
                log.warning("No se eliminó un archivo compartido", extra={"document_id": document.id})
                continue
            try:
                storage.resolve(document.storage_key).unlink(missing_ok=True)
            except (OSError, ApplicationError):
                log.warning("El archivo de chat sigue pendiente de eliminación", extra={"document_id": document.id})
                continue
            session.execute(delete(StoredDocument).where(StoredDocument.id == document.id,
                StoredDocument.status == "pending_delete"))
            session.commit()
            cleaned += 1
    return cleaned
