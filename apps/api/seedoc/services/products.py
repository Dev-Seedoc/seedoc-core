"""Products (API.md §3.4): CRUD, the document set, the language matrix and reading product releases. Releases are
created by `services/releases.py` (`create_product_release`); this module never writes to the release tables."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.documents import Document, DocumentVersion
from seedoc.models.products import Product, ProductDocument, ProductRelease, ProductReleaseItem
from seedoc.models.users import User
from seedoc.schemas.common import Page
from seedoc.schemas.documents import DocumentListItem
from seedoc.schemas.products import (
    LanguageMatrixCell,
    LanguageMatrixRead,
    LanguageMatrixRow,
    ProductCreate,
    ProductDocumentsSet,
    ProductRead,
    ProductReleaseDetailRead,
    ProductReleaseItemRead,
    ProductReleaseRead,
    ProductUpdate,
)
from seedoc.services.documents import list_document_items
from seedoc.services.library import get_sort_key, get_space


async def list_products(db: AsyncSession, ctx: RequestContext) -> Page[ProductRead]:
    """All products of the tenant by name (DIN 5007-1). A tenant has a manageable number, so never paged."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        products = await db.scalars(select(Product).where(Product.tenant_id == tenant_id))
        ordered = sorted(products, key=lambda product: (get_sort_key(product.name), product.id))
        return Page(items=await _to_reads(db, tenant_id, ordered), next_cursor=None)


async def create_product(db: AsyncSession, ctx: RequestContext, body: ProductCreate) -> ProductRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        if body.space_id is not None:
            await get_space(db, tenant_id, body.space_id)
        product = Product(
            tenant_id=tenant_id, name=body.name, space_id=body.space_id, required_languages=body.required_languages
        )
        db.add(product)
        await db.flush()
        await db.refresh(product)  # created_at / updated_at come from the database
        await write_audit_event(db, ctx, "product.created", "product", product.id)
        [read] = await _to_reads(db, tenant_id, [product])
        return read


async def get_product(db: AsyncSession, ctx: RequestContext, product_id: UUID) -> ProductRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        product = await _get_product(db, tenant_id, product_id)
        [read] = await _to_reads(db, tenant_id, [product])
        return read


async def update_product(db: AsyncSession, ctx: RequestContext, product_id: UUID, body: ProductUpdate) -> ProductRead:
    """Change only the fields in the body (`space_id: null` clears the space). `product.updated` is written only
    when a value really changed."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        product = await _get_product(db, tenant_id, product_id, for_update=True)
        changes = {
            field: value
            for field, value in body.model_dump(exclude_unset=True).items()
            if getattr(product, field) != value
        }
        if changes.get("space_id") is not None:
            await get_space(db, tenant_id, changes["space_id"])
        if changes:
            for field, value in changes.items():
                setattr(product, field, value)
            await db.flush()
            await db.refresh(product)  # the new updated_at
            await write_audit_event(db, ctx, "product.updated", "product", product.id, {"fields": sorted(changes)})
        [read] = await _to_reads(db, tenant_id, [product])
        return read


async def list_product_documents(db: AsyncSession, ctx: RequestContext, product_id: UUID) -> Page[DocumentListItem]:
    """The set's untrashed documents by title, then language; never paged."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        product = await _get_product(db, tenant_id, product_id)
        return Page(items=await _list_set_items(db, tenant_id, product.id), next_cursor=None)


async def set_product_documents(
    db: AsyncSession, ctx: RequestContext, product_id: UUID, body: ProductDocumentsSet
) -> Page[DocumentListItem]:
    """Replace the document set. Every id is checked before anything changes: unknown or another tenant's → 404,
    trashed → 409, machine-specific → 422. Trashed members are not part of what the client sees, so they stay in the
    set (until `purge_trash` deletes the document) and come back with a restore. `product.documents_set` is written
    only when the set changed."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        # Locked, so two saves at the same time cannot mix their additions and removals.
        product = await _get_product(db, tenant_id, product_id, for_update=True)
        wanted = list(dict.fromkeys(body.document_ids))  # duplicates ignored, order kept
        # Locked (in id order, so two saves cannot deadlock), so a parallel `attach_machine_document` cannot make one
        # of them machine-specific in between.
        documents = list(
            await db.scalars(
                select(Document)
                .where(Document.tenant_id == tenant_id, Document.id.in_(wanted))
                .order_by(Document.id)
                .with_for_update()
            )
        )
        if len(documents) != len(wanted):
            raise AppError(ErrorCode.NOT_FOUND)
        if any(document.trashed_at is not None for document in documents):
            raise AppError(ErrorCode.CONFLICT, "a document is in the trash; restore it first")
        if any(document.machine_id is not None for document in documents):
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                "a machine-specific document cannot belong to a product",
                details={"field": "document_ids"},
            )

        visible = set(
            await db.scalars(
                select(ProductDocument.document_id)
                .join(Document, Document.id == ProductDocument.document_id)
                .where(
                    ProductDocument.tenant_id == tenant_id,
                    ProductDocument.product_id == product.id,
                    Document.trashed_at.is_(None),
                )
            )
        )
        added = [document_id for document_id in wanted if document_id not in visible]
        removed = visible.difference(wanted)
        if removed:
            await db.execute(
                delete(ProductDocument).where(
                    ProductDocument.tenant_id == tenant_id,
                    ProductDocument.product_id == product.id,
                    ProductDocument.document_id.in_(removed),
                )
            )
        if added:
            await db.execute(
                insert(ProductDocument),
                [
                    {
                        "tenant_id": tenant_id,
                        "product_id": product.id,
                        "document_id": document_id,
                        "added_by": ctx.user_id,
                    }
                    for document_id in added
                ],
            )
        if added or removed:
            await write_audit_event(
                db, ctx, "product.documents_set", "product", product.id, {"added": len(added), "removed": len(removed)}
            )
        return Page(items=await _list_set_items(db, tenant_id, product.id), next_cursor=None)


async def get_product_language_matrix(db: AsyncSession, ctx: RequestContext, product_id: UUID) -> LanguageMatrixRead:
    """One row per language group of the set's untrashed documents (by title). A cell is `present` only when a
    document **of the set** has that language; a variant outside the set leaves it `missing`. Products never have
    `waived` cells (BUSINESS_RULES §6)."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        product = await _get_product(db, tenant_id, product_id)
        languages = list(product.required_languages)
        documents = await db.scalars(
            select(Document)
            .join(ProductDocument, ProductDocument.document_id == Document.id)
            .where(
                ProductDocument.tenant_id == tenant_id,
                ProductDocument.product_id == product.id,
                Document.trashed_at.is_(None),
            )
            .order_by(Document.language, Document.id)
        )
        groups: dict[UUID, dict[str, Document]] = {}
        for document in documents:
            groups.setdefault(document.group_id, {}).setdefault(document.language, document)

        rows: list[LanguageMatrixRow] = []
        for group_id, by_language in groups.items():
            # The row's face: the document in the first required language it has, else the first by language.
            shown = next((by_language[lang] for lang in languages if lang in by_language), None)
            if shown is None:
                shown = by_language[min(by_language)]
            cells = {
                lang: LanguageMatrixCell(status="present", document_id=by_language[lang].id)
                if lang in by_language
                else LanguageMatrixCell(status="missing")
                for lang in languages
            }
            rows.append(LanguageMatrixRow(group_id=group_id, title=shown.title, doc_type=shown.doc_type, cells=cells))
        rows.sort(key=lambda row: (get_sort_key(row.title), str(row.group_id)))
        return LanguageMatrixRead(languages=languages, rows=rows)


async def list_product_releases(db: AsyncSession, ctx: RequestContext, product_id: UUID) -> Page[ProductReleaseRead]:
    """The product's releases, newest first; never paged. Releases are only read here (immutable, DATA_MODEL §4)."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        product = await _get_product(db, tenant_id, product_id)
        rows = await db.execute(
            _release_statement(tenant_id)
            .where(ProductRelease.product_id == product.id)
            .order_by(ProductRelease.release_no.desc())
        )
        return Page(items=[_to_release_read(*row) for row in rows], next_cursor=None)


async def get_product_release(
    db: AsyncSession, ctx: RequestContext, product_id: UUID, release_no: int
) -> ProductReleaseDetailRead:
    """One release with its frozen items (sorted by folder path, title, language); unknown `release_no` → 404."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        product = await _get_product(db, tenant_id, product_id)
        row = (
            await db.execute(
                _release_statement(tenant_id).where(
                    ProductRelease.product_id == product.id, ProductRelease.release_no == release_no
                )
            )
        ).first()
        if row is None:
            raise AppError(ErrorCode.NOT_FOUND)
        release = _to_release_read(*row)
        item_rows = await db.execute(
            select(ProductReleaseItem, DocumentVersion.version_no)
            .join(DocumentVersion, DocumentVersion.id == ProductReleaseItem.version_id)
            .where(ProductReleaseItem.tenant_id == tenant_id, ProductReleaseItem.release_id == release.id)
        )
        items = [
            ProductReleaseItemRead(
                id=item.id,
                document_id=item.document_id,
                version_id=item.version_id,
                version_no=version_no,
                title=item.title,
                doc_type=item.doc_type,
                language=item.language,
                access_level=item.access_level,
                folder_path=item.folder_path,
            )
            for item, version_no in item_rows
        ]
        items.sort(key=lambda item: (get_sort_key(item.folder_path), get_sort_key(item.title), item.language))
        return ProductReleaseDetailRead(**release.model_dump(), items=items)


async def _get_product(db: AsyncSession, tenant_id: UUID, product_id: UUID, for_update: bool = False) -> Product:
    """The tenant's product, or `404 not_found` (also for another tenant's id)."""
    statement = select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
    if for_update:
        statement = statement.with_for_update()
    product = await db.scalar(statement)
    if product is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return product


def _release_statement(tenant_id: UUID) -> Select[ProductRelease, int, str | None]:
    """Releases of the tenant with their item count and the creator's name."""
    item_count = (
        select(func.count())
        .where(ProductReleaseItem.tenant_id == tenant_id, ProductReleaseItem.release_id == ProductRelease.id)
        .scalar_subquery()
    )
    return (
        select(ProductRelease, item_count, User.full_name)
        .outerjoin(User, User.id == ProductRelease.created_by)
        .where(ProductRelease.tenant_id == tenant_id)
    )


def _to_release_read(release: ProductRelease, item_count: int, created_by_name: str | None) -> ProductReleaseRead:
    return ProductReleaseRead(
        id=release.id,
        release_no=release.release_no,
        change_note=release.change_note,
        item_count=item_count,
        created_at=release.created_at,
        created_by_name=created_by_name,
    )


async def _list_set_items(db: AsyncSession, tenant_id: UUID, product_id: UUID) -> list[DocumentListItem]:
    document_ids = list(
        await db.scalars(
            select(ProductDocument.document_id).where(
                ProductDocument.tenant_id == tenant_id, ProductDocument.product_id == product_id
            )
        )
    )
    items = await list_document_items(db, tenant_id, document_ids)
    return [item for item in items if item.trashed_at is None]


async def _to_reads(db: AsyncSession, tenant_id: UUID, products: Sequence[Product]) -> list[ProductRead]:
    """`ProductRead`s in the given order; `document_count` (untrashed documents of the set) and `latest_release_no`
    come from one query each for all products."""
    product_ids = [product.id for product in products]
    if not product_ids:
        return []
    count_rows = await db.execute(
        select(ProductDocument.product_id, func.count())
        .join(Document, Document.id == ProductDocument.document_id)
        .where(
            ProductDocument.tenant_id == tenant_id,
            ProductDocument.product_id.in_(product_ids),
            Document.trashed_at.is_(None),
        )
        .group_by(ProductDocument.product_id)
    )
    document_counts: dict[UUID, int] = {row[0]: row[1] for row in count_rows}
    release_rows = await db.execute(
        select(ProductRelease.product_id, func.max(ProductRelease.release_no))
        .where(ProductRelease.tenant_id == tenant_id, ProductRelease.product_id.in_(product_ids))
        .group_by(ProductRelease.product_id)
    )
    latest_release_nos: dict[UUID, int] = {row[0]: row[1] for row in release_rows}
    return [
        ProductRead(
            id=product.id,
            name=product.name,
            space_id=product.space_id,
            required_languages=product.required_languages,
            document_count=document_counts.get(product.id, 0),
            latest_release_no=latest_release_nos.get(product.id),
            archived_at=product.archived_at,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )
        for product in products
    ]
