"""Documents and their versions (API.md §3.3, BUSINESS_RULES §3).

A file reaches a document in three steps: `create_upload` records what the browser will send and hands out a
presigned PUT; the browser uploads; `create_document` / `create_document_version` then **verify the stored object**
(it exists, size and SHA-256 match the upload row, it starts with `%PDF-`), copy it to its version key and create
the rows. Network work (reading and copying the object) happens outside the database transaction; if the
transaction then fails, the copied object is removed again.

Versions start as `pending`. The worker (M1-A6) picks them up with `process_version`; until it exists they stay
`pending`.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.documents import Document, DocumentVersion, Folder, Space, Upload
from seedoc.schemas.common import Page
from seedoc.schemas.documents import (
    DocumentCreate,
    DocumentListItem,
    DocumentListQuery,
    DocumentRead,
    DocumentUpdate,
    DocumentVersionCreate,
    DocumentVersionRead,
    LanguageVariantRead,
    VersionFileUrlRead,
)
from seedoc.services.library import PATH_SEPARATOR, build_folder_paths, get_folder
from seedoc.storage.s3 import copy_object, delete_object, get_version_key, presign_get, read_object_digest

PDF_MAGIC = b"%PDF-"
# A document with its current version (outer join: the version is null only while a create is in flight).
_ListStatement = Select[Document, DocumentVersion]

log = structlog.get_logger()


# ─────────────────────────── documents ───────────────────────────


async def list_documents(db: AsyncSession, ctx: RequestContext, query: DocumentListQuery) -> Page[DocumentListItem]:
    """Documents ordered by title, `limit` per page; `next_cursor` continues after the last item. Trashed documents
    only with `include_trashed`."""
    after = _decode_cursor(query.cursor) if query.cursor else None
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        statement = (
            select(Document, DocumentVersion)
            .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
            .where(Document.tenant_id == tenant_id)
            .order_by(Document.title, Document.id)
            .limit(query.limit + 1)
        )
        statement = _apply_filters(statement, query)
        if after is not None:
            statement = statement.where(tuple_(Document.title, Document.id) > tuple_(*after))
        rows = (await db.execute(statement)).all()
        paths = await _get_folder_paths(db, tenant_id)
        items = [_to_list_item(document, version, paths) for document, version in rows[: query.limit]]

    next_cursor = _encode_cursor(items[-1].title, items[-1].id) if len(rows) > query.limit else None
    return Page(items=items, next_cursor=next_cursor)


async def create_document(db: AsyncSession, ctx: RequestContext, body: DocumentCreate) -> DocumentRead:
    """A document with its first version from a finished upload. Missing `doc_type` / `language` /
    `access_level` come from the folder's defaults; a value that is neither given nor a folder default is a 422."""
    upload = await _verify_upload(db, ctx, body.upload_id)
    version_id = uuid4()
    version_key = get_version_key(upload.tenant_id, version_id)
    await copy_object(upload.storage_key, version_key)
    try:
        async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
            await _consume_upload(db, tenant_id, upload.id)
            folder = await get_folder(db, tenant_id, body.folder_id)
            doc_type = body.doc_type or folder.default_doc_type
            language = body.language or folder.default_language
            if doc_type is None or language is None:
                missing = [name for name, value in (("doc_type", doc_type), ("language", language)) if value is None]
                raise AppError(
                    ErrorCode.VALIDATION_FAILED,
                    "not given and the folder has no default",
                    details={
                        "fields": [{"loc": ["body", name], "type": "missing", "msg": "required"} for name in missing]
                    },
                )
            duplicate_of = await _find_duplicate(db, tenant_id, upload.sha256, exclude_document_id=None)

            document = Document(
                tenant_id=tenant_id,
                folder_id=folder.id,
                title=body.title,
                doc_type=doc_type,
                language=language,
                access_level=body.access_level or folder.default_access_level,
                machine_id=body.machine_id,
                created_by=ctx.user_id,
            )
            db.add(document)
            await db.flush()
            db.add(_new_version(upload, version_id, version_key, document.id, 1, ctx.user_id))
            await db.flush()
            document.current_version_id = version_id
            await write_audit_event(
                db, ctx, "document.created", "document", document.id, {"version_id": str(version_id)}
            )
            await db.flush()
            read = await _read_document(db, tenant_id, document.id)
    except BaseException:
        await _delete_quietly(version_key)
        raise

    await _delete_quietly(upload.storage_key)
    return read.model_copy(update={"duplicate_of_document_id": duplicate_of})


async def get_document(db: AsyncSession, ctx: RequestContext, document_id: UUID) -> DocumentRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        return await _read_document(db, tenant_id, document_id)


async def update_document(
    db: AsyncSession, ctx: RequestContext, document_id: UUID, body: DocumentUpdate
) -> DocumentRead:
    """Change only the fields in the body. A trashed document must be restored first (`409 conflict`). A new
    `language` must not already exist in the document's language group (`409 conflict`)."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        document = await _get_document(db, tenant_id, document_id, for_update=True)
        if document.trashed_at is not None:
            raise AppError(ErrorCode.CONFLICT, "the document is in the trash; restore it first")
        changes = {
            field: value
            for field, value in body.model_dump(exclude_unset=True).items()
            if getattr(document, field) != value
        }
        if "folder_id" in changes:
            await get_folder(db, tenant_id, changes["folder_id"])
        if "language" in changes:
            await _ensure_language_free(db, tenant_id, document.group_id, changes["language"], document.id)
        if changes:
            for field, value in changes.items():
                setattr(document, field, value)
            await db.flush()
            await write_audit_event(db, ctx, "document.updated", "document", document.id, {"fields": sorted(changes)})
        return await _read_document(db, tenant_id, document.id)


async def trash_document(db: AsyncSession, ctx: RequestContext, document_id: UUID) -> DocumentRead:
    """Move to the trash (BUSINESS_RULES §3). Trashing a trashed document changes nothing."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        document = await _get_document(db, tenant_id, document_id, for_update=True)
        if document.trashed_at is None:
            document.trashed_at = datetime.now(UTC)
            document.trashed_by = ctx.user_id
            await db.flush()
            await write_audit_event(db, ctx, "document.trashed", "document", document.id)
        return await _read_document(db, tenant_id, document.id)


async def restore_document(db: AsyncSession, ctx: RequestContext, document_id: UUID) -> DocumentRead:
    """Take out of the trash. Restoring a document that is not trashed changes nothing."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        document = await _get_document(db, tenant_id, document_id, for_update=True)
        if document.trashed_at is not None:
            document.trashed_at = None
            document.trashed_by = None
            await db.flush()
            await write_audit_event(db, ctx, "document.restored", "document", document.id)
        return await _read_document(db, tenant_id, document.id)


# ─────────────────────────── versions ───────────────────────────


async def list_document_versions(db: AsyncSession, ctx: RequestContext, document_id: UUID) -> Page[DocumentVersionRead]:
    """Every version, newest first. A document has a handful, so the list is never paged (`next_cursor` null)."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        document = await _get_document(db, tenant_id, document_id)
        versions = await db.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.tenant_id == tenant_id, DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_no.desc())
        )
        items = [_to_version_read(version, document.current_version_id) for version in versions]
    return Page(items=items, next_cursor=None)


async def create_document_version(
    db: AsyncSession, ctx: RequestContext, document_id: UUID, body: DocumentVersionCreate
) -> DocumentVersionRead:
    """A new version from a finished upload; it becomes the current version at once (BUSINESS_RULES §3)."""
    upload = await _verify_upload(db, ctx, body.upload_id)
    version_id = uuid4()
    version_key = get_version_key(upload.tenant_id, version_id)
    await copy_object(upload.storage_key, version_key)
    try:
        async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
            document = await _get_document(db, tenant_id, document_id, for_update=True)  # serialises version_no
            if document.trashed_at is not None:
                raise AppError(ErrorCode.CONFLICT, "the document is in the trash; restore it first")
            await _consume_upload(db, tenant_id, upload.id)
            duplicate_of = await _find_duplicate(db, tenant_id, upload.sha256, exclude_document_id=document.id)
            last_no = await db.scalar(
                select(func.max(DocumentVersion.version_no)).where(
                    DocumentVersion.tenant_id == tenant_id, DocumentVersion.document_id == document.id
                )
            )
            version = _new_version(upload, version_id, version_key, document.id, (last_no or 0) + 1, ctx.user_id)
            db.add(version)
            await db.flush()
            document.current_version_id = version.id
            await write_audit_event(
                db, ctx, "document.version_added", "document", document.id, {"version_no": version.version_no}
            )
            await db.flush()
            await db.refresh(version)
            read = _to_version_read(version, version.id)
    except BaseException:
        await _delete_quietly(version_key)
        raise

    await _delete_quietly(upload.storage_key)
    return read.model_copy(update={"duplicate_of_document_id": duplicate_of})


async def get_version_file_url(
    db: AsyncSession, ctx: RequestContext, document_id: UUID, version_id: UUID
) -> VersionFileUrlRead:
    """Short-lived download link (120 s) saved as `<title>_<language>_v<version_no>.pdf` (NAMING §9)."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        row = (
            await db.execute(
                select(DocumentVersion, Document)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    DocumentVersion.id == version_id,
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.tenant_id == tenant_id,
                    Document.tenant_id == tenant_id,
                )
            )
        ).first()
        if row is None:
            raise AppError(ErrorCode.NOT_FOUND)
        version, document = row
        download_name = f"{document.title}_{document.language}_v{version.version_no}.pdf".replace(" ", "_")
    url, expires_at = presign_get(version.storage_key, download_name)
    return VersionFileUrlRead(url=url, expires_at=expires_at)


# ─────────────────────────── uploads ───────────────────────────


@dataclass(frozen=True)
class _VerifiedUpload:
    id: UUID
    tenant_id: UUID
    storage_key: str
    file_name: str
    size_bytes: int
    sha256: bytes


async def _verify_upload(db: AsyncSession, ctx: RequestContext, upload_id: UUID) -> _VerifiedUpload:
    """The tenant's open upload, checked against what is really stored (BUSINESS_RULES §3):
    unknown or another tenant's → 404; used or older than 24 h → 409 conflict; object missing or size/SHA-256
    different → 409 upload_incomplete; not starting with `%PDF-` → 415."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        upload = await db.scalar(select(Upload).where(Upload.id == upload_id, Upload.tenant_id == tenant_id))
        if upload is None:
            raise AppError(ErrorCode.NOT_FOUND)
        _check_upload_open(upload)
        verified = _VerifiedUpload(
            upload.id, tenant_id, upload.storage_key, upload.file_name, upload.size_bytes, upload.sha256
        )

    stored = await read_object_digest(verified.storage_key)
    if stored is None:
        raise AppError(ErrorCode.UPLOAD_INCOMPLETE, "the file has not been uploaded")
    if stored.size_bytes != verified.size_bytes or stored.sha256 != verified.sha256:
        raise AppError(ErrorCode.UPLOAD_INCOMPLETE, "the stored file does not match the upload (size or SHA-256)")
    if not stored.head.startswith(PDF_MAGIC):
        raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, "the file is not a PDF")
    return verified


async def _consume_upload(db: AsyncSession, tenant_id: UUID, upload_id: UUID) -> None:
    """Mark the upload used, under a row lock, so two requests can never turn one upload into two versions."""
    upload = await db.scalar(
        select(Upload).where(Upload.id == upload_id, Upload.tenant_id == tenant_id).with_for_update()
    )
    if upload is None:
        raise AppError(ErrorCode.NOT_FOUND)
    _check_upload_open(upload)
    upload.consumed_at = datetime.now(UTC)


def _check_upload_open(upload: Upload) -> None:
    if upload.consumed_at is not None:
        raise AppError(ErrorCode.CONFLICT, "this upload has already been used", details={"field": "upload_id"})
    if upload.expires_at <= datetime.now(UTC):
        raise AppError(
            ErrorCode.CONFLICT, "this upload has expired; upload the file again", details={"field": "upload_id"}
        )


def _new_version(
    upload: _VerifiedUpload, version_id: UUID, key: str, document_id: UUID, version_no: int, user_id: UUID | None
) -> DocumentVersion:
    return DocumentVersion(
        id=version_id,
        tenant_id=upload.tenant_id,
        document_id=document_id,
        version_no=version_no,
        storage_key=key,
        file_name=upload.file_name,
        size_bytes=upload.size_bytes,
        sha256=upload.sha256,
        created_by=user_id,
    )


async def _find_duplicate(
    db: AsyncSession, tenant_id: UUID, sha256: bytes, exclude_document_id: UUID | None
) -> UUID | None:
    """Another document of the tenant that already has a version with this file (BUSINESS_RULES §3: allowed, but the
    UI warns). Trashed documents count too — the file is still stored."""
    statement = select(DocumentVersion.document_id).where(
        DocumentVersion.tenant_id == tenant_id, DocumentVersion.sha256 == sha256
    )
    if exclude_document_id is not None:
        statement = statement.where(DocumentVersion.document_id != exclude_document_id)
    return await db.scalar(statement.order_by(DocumentVersion.created_at).limit(1))


async def _delete_quietly(key: str) -> None:
    """Best-effort clean-up of an object nobody references; a failure only leaves an orphan behind."""
    try:
        await delete_object(key)
    except Exception as exc:  # the request itself already succeeded or failed for its own reason
        log.warning("storage_cleanup_failed", error=type(exc).__name__)


# ─────────────────────────── reading ───────────────────────────


async def _get_document(db: AsyncSession, tenant_id: UUID, document_id: UUID, for_update: bool = False) -> Document:
    """The tenant's document (trashed ones too), or `404 not_found`."""
    statement = select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    document = await db.scalar(statement.with_for_update() if for_update else statement)
    if document is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return document


async def _ensure_language_free(
    db: AsyncSession, tenant_id: UUID, group_id: UUID, language: str, document_id: UUID
) -> None:
    """Documents of one language group have distinct languages (BUSINESS_RULES §3) → else `409 conflict`."""
    taken = await db.scalar(
        select(Document.id).where(
            Document.tenant_id == tenant_id,
            Document.group_id == group_id,
            Document.language == language,
            Document.id != document_id,
        )
    )
    if taken is not None:
        raise AppError(
            ErrorCode.CONFLICT, "a language variant in this language already exists", details={"field": "language"}
        )


async def _read_document(db: AsyncSession, tenant_id: UUID, document_id: UUID) -> DocumentRead:
    document = await _get_document(db, tenant_id, document_id)
    await db.refresh(document)  # updated_at is set by the database
    version = (
        await db.get(DocumentVersion, document.current_version_id) if document.current_version_id is not None else None
    )
    versions_count = await db.scalar(
        select(func.count()).where(DocumentVersion.tenant_id == tenant_id, DocumentVersion.document_id == document.id)
    )
    variants = await db.scalars(
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.group_id == document.group_id,
            Document.id != document.id,
            Document.trashed_at.is_(None),
        )
        .order_by(Document.language)
    )
    item = _to_list_item(document, version, await _get_folder_paths(db, tenant_id))
    return DocumentRead(
        **item.model_dump(),
        versions_count=versions_count or 0,
        language_variants=[
            LanguageVariantRead(document_id=variant.id, language=variant.language, title=variant.title)
            for variant in variants
        ],
        released_in_count=0,  # TODO(M2-A2): count product/delivery release items once those tables exist
    )


async def _get_folder_paths(db: AsyncSession, tenant_id: UUID) -> dict[UUID, str]:
    """`{folder id: "<space name>/<folder>/<subfolder>"}` for the whole tenant (BUSINESS_RULES §6 `folder_path`)."""
    folders = list(await db.scalars(select(Folder).where(Folder.tenant_id == tenant_id)))
    rows = await db.execute(select(Space.id, Space.name).where(Space.tenant_id == tenant_id))
    space_names = {space_id: name for space_id, name in rows.all()}
    paths = build_folder_paths(folders)
    return {folder.id: space_names[folder.space_id] + PATH_SEPARATOR + paths[folder.id] for folder in folders}


def _to_list_item(
    document: Document, version: DocumentVersion | None, folder_paths: dict[UUID, str]
) -> DocumentListItem:
    return DocumentListItem(
        id=document.id,
        title=document.title,
        doc_type=document.doc_type,
        language=document.language,
        access_level=document.access_level,
        folder_id=document.folder_id,
        folder_path=folder_paths[document.folder_id],
        current_version_no=version.version_no if version is not None else None,
        processing_status=version.processing_status if version is not None else None,
        group_id=document.group_id,
        machine_id=document.machine_id,
        trashed_at=document.trashed_at,
        updated_at=document.updated_at,
    )


def _to_version_read(version: DocumentVersion, current_version_id: UUID | None) -> DocumentVersionRead:
    return DocumentVersionRead(
        id=version.id,
        document_id=version.document_id,
        version_no=version.version_no,
        file_name=version.file_name,
        size_bytes=version.size_bytes,
        sha256_hex=version.sha256.hex(),
        page_count=version.page_count,
        processing_status=version.processing_status,
        processing_error=version.processing_error,
        processed_at=version.processed_at,
        is_current=version.id == current_version_id,
        created_by=version.created_by,
        created_at=version.created_at,
    )


# ─────────────────────────── list filters + cursor ───────────────────────────


def _apply_filters(statement: _ListStatement, query: DocumentListQuery) -> _ListStatement:
    if not query.include_trashed:
        statement = statement.where(Document.trashed_at.is_(None))
    if query.space_id is not None:
        statement = statement.where(Document.folder_id.in_(select(Folder.id).where(Folder.space_id == query.space_id)))
    if query.folder_id is not None:
        statement = statement.where(Document.folder_id == query.folder_id)
    if query.language is not None:
        statement = statement.where(Document.language == query.language)
    if query.access_level is not None:
        statement = statement.where(Document.access_level == query.access_level)
    if query.doc_type is not None:
        statement = statement.where(Document.doc_type == query.doc_type)
    if query.machine_id is not None:
        statement = statement.where(Document.machine_id == query.machine_id)
    if query.processing_status is not None:
        statement = statement.where(DocumentVersion.processing_status == query.processing_status)
    if query.q:
        pattern = "%" + query.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        statement = statement.where(Document.title.ilike(pattern, escape="\\"))
    return statement


def _encode_cursor(title: str, document_id: UUID) -> str:
    return base64.urlsafe_b64encode(json.dumps([title, str(document_id)]).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, UUID]:
    try:
        title, document_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return str(title), UUID(str(document_id))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise AppError(ErrorCode.VALIDATION_FAILED, "invalid cursor", details={"field": "cursor"}) from exc
