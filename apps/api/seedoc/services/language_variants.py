"""Language variants (API.md §3.3, BUSINESS_RULES §3): documents with the same `group_id` are translations of each
other, at most one document per language — trashed members included, so restoring one never breaks the rule.

The database has no unique constraint on (group_id, language), so both operations lock every document of the groups
involved (`SELECT … FOR UPDATE`, always ordered by id so two requests cannot deadlock) before they check and write.
The response is read afterwards with `get_document`, in its own transaction, so it shows the committed state.
"""

from collections.abc import Iterable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.documents import Document
from seedoc.schemas.documents import DocumentRead, LanguageVariantLink
from seedoc.services.documents import get_document


async def link_language_variant(
    db: AsyncSession, ctx: RequestContext, document_id: UUID, body: LanguageVariantLink
) -> DocumentRead:
    """Put the whole language group of `body.document_id` into the group of `document_id`, which keeps its
    `group_id`. Nothing changes if any language would then appear twice."""
    if body.document_id == document_id:
        raise AppError(
            ErrorCode.VALIDATION_FAILED, "a document is not its own language variant", details={"field": "document_id"}
        )
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        document, variant = await _lock_documents(db, tenant_id, document_id, body.document_id)
        if document.trashed_at is not None or variant.trashed_at is not None:
            raise AppError(ErrorCode.CONFLICT, "a trashed document cannot be linked")
        # Already one group (asked from either side): nothing to do, nothing to audit.
        if document.group_id != variant.group_id:
            members = await _lock_groups(db, tenant_id, (document.group_id, variant.group_id))
            own_languages = {member.language for member in members if member.group_id == document.group_id}
            joining = [member for member in members if member.group_id == variant.group_id]
            if own_languages & {member.language for member in joining}:
                raise AppError(
                    ErrorCode.CONFLICT,
                    "both language groups have a document in the same language",
                    details={"field": "language"},
                )
            for member in joining:
                member.group_id = document.group_id
            await db.flush()
            await write_audit_event(
                db,
                ctx,
                "document.language_linked",
                "document",
                document.id,
                {"variant_document_id": str(variant.id)},
            )
    return await get_document(db, ctx, document_id)


async def unlink_language_variant(
    db: AsyncSession, ctx: RequestContext, document_id: UUID, variant_document_id: UUID
) -> DocumentRead:
    """Take `variant_document_id` out of the group of `document_id`: it gets a new group of its own, the rest of the
    group stays. A trashed variant may leave; a trashed path document cannot be changed."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        # A document is not its own variant: same answer as for any document outside the group.
        if variant_document_id == document_id:
            raise AppError(ErrorCode.NOT_FOUND)
        document, variant = await _lock_documents(db, tenant_id, document_id, variant_document_id)
        if variant.group_id != document.group_id:
            raise AppError(ErrorCode.NOT_FOUND)
        if document.trashed_at is not None:
            raise AppError(ErrorCode.CONFLICT, "a trashed document cannot be changed")
        variant.group_id = uuid4()
        await db.flush()
        await write_audit_event(
            db,
            ctx,
            "document.language_unlinked",
            "document",
            document.id,
            {"variant_document_id": str(variant.id)},
        )
    return await get_document(db, ctx, document_id)


async def _lock_documents(
    db: AsyncSession, tenant_id: UUID, document_id: UUID, other_id: UUID
) -> tuple[Document, Document]:
    """Both documents of the tenant (trashed ones too), locked; `404 not_found` if either is missing or belongs to
    another tenant, so the other tenant's ids reveal nothing."""
    rows = await db.scalars(
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.id.in_((document_id, other_id)))
        .order_by(Document.id)
        .with_for_update()
    )
    by_id = {row.id: row for row in rows}
    document, other = by_id.get(document_id), by_id.get(other_id)
    if document is None or other is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return document, other


async def _lock_groups(db: AsyncSession, tenant_id: UUID, group_ids: Iterable[UUID]) -> list[Document]:
    """Every document of these groups, trashed ones too, locked in id order."""
    rows = await db.scalars(
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.group_id.in_(set(group_ids)))
        .order_by(Document.id)
        .with_for_update()
    )
    return list(rows)
