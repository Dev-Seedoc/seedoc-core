"""Emptying the trash (BUSINESS_RULES §3, ARCHITECTURE §11): the daily `purge_trash` job.

A document trashed more than 30 days ago is hard-deleted with its versions, chunks and files — **only if no release
references any of its versions**; otherwise it stays trashed forever (the release keeps showing its frozen version).
Runs in the worker as `seedoc_admin` across all tenants, one document per transaction, so a failure leaves the
others done and the next run picks the rest up.

Until the release tables exist (migration 0004, M2) "is it released?" cannot be answered, so every document counts
as released and nothing is purged yet.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import get_admin_sessionmaker
from seedoc.deps import RequestContext
from seedoc.models.documents import Document, DocumentVersion
from seedoc.storage.s3 import purge_object

log = structlog.get_logger()

TRASH_RETENTION = timedelta(days=30)
PURGE_BATCH = 200  # documents per run; a bigger backlog is finished on the following days

# Audit events of the job have no user, session or request.
_JOB_CONTEXT = RequestContext(
    user_id=None,
    tenant_id=None,
    role=None,
    is_staff=False,
    session_id=None,
    fresh_auth_at=None,
    portal_session_id=None,
    operator_org_ids=(),
    ip_hash=None,
    request_id="purge_trash",
)


@dataclass(frozen=True)
class PurgeResult:
    purged: int
    kept_released: int


async def purge_trash(now: datetime | None = None) -> PurgeResult:
    """Hard-delete what is due; returns how many documents were purged and how many were kept because released."""
    cutoff = (now or datetime.now(UTC)) - TRASH_RETENTION
    async with get_admin_sessionmaker()() as db:
        async with db.begin():
            due = list(
                await db.scalars(
                    select(Document.id)
                    .where(Document.trashed_at.is_not(None), Document.trashed_at < cutoff)
                    .order_by(Document.trashed_at)
                    .limit(PURGE_BATCH)
                )
            )
        purged = kept = 0
        for document_id in due:
            keys = await _purge_document(db, document_id, cutoff)
            if keys is None:
                kept += 1
                continue
            purged += 1
            for key in keys:  # after the commit: a file left behind is only storage, a missing row would be worse
                try:
                    await purge_object(key)
                except Exception as exc:
                    log.error("purge_file_failed", document_id=str(document_id), error=type(exc).__name__)
    log.info("trash_purged", purged=purged, kept_released=kept)
    return PurgeResult(purged=purged, kept_released=kept)


async def _purge_document(db: AsyncSession, document_id: UUID, cutoff: datetime) -> list[str] | None:
    """Delete one document in its own transaction; the storage keys of its versions, or `None` if it was kept."""
    async with db.begin():
        document = await db.scalar(select(Document).where(Document.id == document_id).with_for_update())
        # Restored (or purged by a parallel run) since it was selected.
        if document is None or document.trashed_at is None or document.trashed_at >= cutoff:
            return None
        if await is_document_released(db, document.id):
            return None
        versions = list(await db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)))
        await db.execute(update(Document).where(Document.id == document.id).values(current_version_id=None))
        await db.execute(delete(DocumentVersion).where(DocumentVersion.document_id == document.id))  # chunks cascade
        await db.execute(delete(Document).where(Document.id == document.id))
        await write_audit_event(
            db,
            _JOB_CONTEXT,
            "document.purged",
            "document",
            document.id,
            {"version_count": len(versions)},
            tenant_id=document.tenant_id,
        )
    return [version.storage_key for version in versions]


async def is_document_released(db: AsyncSession, document_id: UUID) -> bool:
    """Does any product or delivery release reference a version of the document?

    TODO(M2, migration 0004): check `product_release_items` and `delivery_release_items`. Until those tables exist
    the answer is always "yes", so `purge_trash` purges nothing (WORK_PLAN M1-A7).
    """
    return True
