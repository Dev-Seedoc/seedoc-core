"""Releases (BUSINESS_RULES §6): frozen sets of document versions. A release row and its items are never changed
afterwards (DATA_MODEL §4, `forbid_mutation` triggers); this module is the only one that writes them.

Product releases (`create_product_release`, API.md §3.4) now; delivery drafts, the check and publishing follow with
M2-B4/B5.
"""

from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.documents import Document, DocumentVersion, ProcessingStatus
from seedoc.models.products import Product, ProductDocument, ProductRelease, ProductReleaseItem
from seedoc.models.users import User
from seedoc.schemas.products import ProductReleaseCreate, ProductReleaseRead
from seedoc.services.documents import get_folder_paths


async def create_product_release(
    db: AsyncSession, ctx: RequestContext, product_id: UUID, body: ProductReleaseCreate
) -> ProductReleaseRead:
    """Freeze the current version of every untrashed document in the product's set (BUSINESS_RULES §6 steps 1 to 5).
    Every version must be `ready`, and there must be at least one document; otherwise `409 publish_blocked` and
    nothing is written."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        # 1. Locked, so two releases at the same time get consecutive numbers and the same set.
        product = await db.scalar(
            select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id).with_for_update()
        )
        if product is None:
            raise AppError(ErrorCode.NOT_FOUND)

        # 2. The current version of every untrashed document in the set.
        rows = (
            await db.execute(
                select(Document, DocumentVersion)
                .join(ProductDocument, ProductDocument.document_id == Document.id)
                .join(DocumentVersion, DocumentVersion.id == Document.current_version_id)
                .where(
                    ProductDocument.tenant_id == tenant_id,
                    ProductDocument.product_id == product.id,
                    Document.tenant_id == tenant_id,
                    Document.trashed_at.is_(None),
                )
                .order_by(Document.id)
            )
        ).all()

        # 3. Nothing to release, or a version that is not `ready` → blocked.
        if not rows:
            _block([{"code": "no_items"}])
        not_ready = [
            document.id for document, version in rows if version.processing_status is not ProcessingStatus.READY
        ]
        if not_ready:
            _block(
                [
                    {"code": "version_not_ready", "document_id": str(document_id)}
                    for document_id in sorted(not_ready, key=str)
                ]
            )

        # 4. The next number, and the documents' metadata as it is now.
        last_no = await db.scalar(
            select(func.max(ProductRelease.release_no)).where(
                ProductRelease.tenant_id == tenant_id, ProductRelease.product_id == product.id
            )
        )
        release = ProductRelease(
            tenant_id=tenant_id,
            product_id=product.id,
            release_no=(last_no or 0) + 1,
            change_note=body.change_note or None,
            created_by=ctx.user_id,
        )
        db.add(release)
        await db.flush()
        await db.refresh(release)  # created_at comes from the database
        folder_paths = await get_folder_paths(db, tenant_id)
        await db.execute(
            insert(ProductReleaseItem),
            [
                {
                    "tenant_id": tenant_id,
                    "release_id": release.id,
                    "document_id": document.id,
                    "version_id": version.id,
                    "group_id": document.group_id,
                    "title": document.title,
                    "doc_type": document.doc_type,
                    "language": document.language,
                    "access_level": document.access_level,
                    "folder_path": folder_paths[document.folder_id],
                }
                for document, version in rows
            ],
        )

        # 5. Audit.
        await write_audit_event(
            db,
            ctx,
            "product_release.created",
            "product_release",
            release.id,
            {"product_id": str(product.id), "release_no": release.release_no, "item_count": len(rows)},
        )
        created_by_name = await db.scalar(select(User.full_name).where(User.id == ctx.user_id))
        return ProductReleaseRead(
            id=release.id,
            release_no=release.release_no,
            change_note=release.change_note,
            item_count=len(rows),
            created_at=release.created_at,
            created_by_name=created_by_name,
        )


def _block(problems: list[dict[str, Any]]) -> NoReturn:
    raise AppError(ErrorCode.PUBLISH_BLOCKED, "the product cannot be released yet", details={"problems": problems})
