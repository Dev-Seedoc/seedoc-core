"""Folders (API.md §3.2), following the pattern of services/spaces.py. `path` is not stored: it is built from the
names of the folder and its parents, so renaming a folder changes the paths of all its subfolders at once."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.documents import Document, Folder
from seedoc.schemas.common import Page
from seedoc.schemas.folders import FolderCreate, FolderRead, FolderUpdate
from seedoc.services.library import build_folder_paths, get_folder, get_path_sort_key, get_space

# DATA_MODEL §3: a name is unique among the folders with the same parent in one space (root folders: parent null).
SIBLING_NAME_CONSTRAINT = "uq_folders_space_id_parent_id_name"


async def list_folders(db: AsyncSession, ctx: RequestContext, space_id: UUID) -> Page[FolderRead]:
    """Every folder of the space as a flat list sorted by `path` (folder by folder, German-friendly); the client
    builds the tree from `parent_id`. A space's tree is needed whole, so the list is never paged (`next_cursor`
    null)."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        await get_space(db, tenant_id, space_id)
        folders = await _list_space_folders(db, tenant_id, space_id)
        paths = build_folder_paths(folders)
        items = sorted(
            (_to_read(folder, paths[folder.id]) for folder in folders), key=lambda item: get_path_sort_key(item.path)
        )
        return Page(items=items, next_cursor=None)


async def create_folder(db: AsyncSession, ctx: RequestContext, body: FolderCreate) -> FolderRead:
    """A folder in the space, at the root (`parent_id` null) or below a parent of the same space."""
    try:
        async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
            await get_space(db, tenant_id, body.space_id)
            if body.parent_id is not None:
                parent = await get_folder(db, tenant_id, body.parent_id)  # another tenant's folder → 404
                if parent.space_id != body.space_id:
                    raise AppError(
                        ErrorCode.VALIDATION_FAILED, "parent folder is in another space", details={"field": "parent_id"}
                    )
            await _ensure_name_is_free(db, tenant_id, body.space_id, body.parent_id, body.name)

            folder = Folder(
                tenant_id=tenant_id,
                space_id=body.space_id,
                parent_id=body.parent_id,
                name=body.name,
                default_access_level=body.default_access_level,
                default_doc_type=body.default_doc_type,
                default_language=body.default_language,
            )
            db.add(folder)
            await db.flush()
            await db.refresh(folder)  # sort_order, created_at and updated_at come from the database
            await write_audit_event(db, ctx, "folder.created", "folder", folder.id)
            return await _read_folder(db, tenant_id, folder)
    except IntegrityError as exc:
        if _is_sibling_name_conflict(exc):
            raise _name_taken() from exc
        raise


async def update_folder(db: AsyncSession, ctx: RequestContext, folder_id: UUID, body: FolderUpdate) -> FolderRead:
    """Change only the fields in the body. The audit event lists the fields whose value really changed; a request
    that changes nothing writes none."""
    try:
        async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
            folder = await get_folder(db, tenant_id, folder_id)
            changes: dict[str, Any] = {
                field: value
                for field, value in body.model_dump(exclude_unset=True).items()
                if getattr(folder, field) != value
            }
            if "name" in changes:
                await _ensure_name_is_free(db, tenant_id, folder.space_id, folder.parent_id, changes["name"])
            if changes:
                for field, value in changes.items():
                    setattr(folder, field, value)
                await db.flush()
                await db.refresh(folder)  # updated_at is set by the database
                await write_audit_event(db, ctx, "folder.updated", "folder", folder.id, {"fields": sorted(changes)})
            return await _read_folder(db, tenant_id, folder)
    except IntegrityError as exc:
        if _is_sibling_name_conflict(exc):
            raise _name_taken() from exc
        raise


async def delete_folder(db: AsyncSession, ctx: RequestContext, folder_id: UUID) -> None:
    """Only an empty folder: no subfolders and no documents — trashed documents count too, since they can still be
    restored into it (API.md §3.2). Otherwise `409 conflict`."""
    try:
        async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
            folder = await get_folder(db, tenant_id, folder_id)
            has_subfolders = await db.scalar(
                select(exists().where(Folder.tenant_id == tenant_id, Folder.parent_id == folder.id))
            )
            has_documents = await db.scalar(
                select(exists().where(Document.tenant_id == tenant_id, Document.folder_id == folder.id))
            )
            if has_subfolders or has_documents:
                raise AppError(ErrorCode.CONFLICT, "folder is not empty")
            await db.delete(folder)
            await write_audit_event(db, ctx, "folder.deleted", "folder", folder.id)
    except IntegrityError as exc:
        # A subfolder or document added at the same moment: the foreign keys refuse the delete.
        raise AppError(ErrorCode.CONFLICT, "folder is not empty") from exc


async def _ensure_name_is_free(
    db: AsyncSession, tenant_id: UUID, space_id: UUID, parent_id: UUID | None, name: str
) -> None:
    """`409 conflict` if a sibling already has this name. The unique constraint backs this up for two requests at
    the same moment (`_is_sibling_name_conflict`)."""
    taken = await db.scalar(
        select(
            exists().where(
                Folder.tenant_id == tenant_id,
                Folder.space_id == space_id,
                Folder.parent_id.is_not_distinct_from(parent_id),
                Folder.name == name,
            )
        )
    )
    if taken:
        raise _name_taken()


def _name_taken() -> AppError:
    return AppError(ErrorCode.CONFLICT, "a folder with this name already exists here", details={"field": "name"})


def _is_sibling_name_conflict(exc: IntegrityError) -> bool:
    """The sibling-name constraint fired; any other integrity error stays unexpected (500)."""
    return SIBLING_NAME_CONSTRAINT in str(exc.orig)


async def _list_space_folders(db: AsyncSession, tenant_id: UUID, space_id: UUID) -> Sequence[Folder]:
    rows = await db.scalars(select(Folder).where(Folder.tenant_id == tenant_id, Folder.space_id == space_id))
    return rows.all()


async def _read_folder(db: AsyncSession, tenant_id: UUID, folder: Folder) -> FolderRead:
    """One folder with its path; loads the space's folders, since any parent's name is part of it."""
    paths = build_folder_paths(await _list_space_folders(db, tenant_id, folder.space_id))
    return _to_read(folder, paths[folder.id])


def _to_read(folder: Folder, path: str) -> FolderRead:
    return FolderRead(
        id=folder.id,
        space_id=folder.space_id,
        parent_id=folder.parent_id,
        name=folder.name,
        path=path,
        sort_order=folder.sort_order,
        default_access_level=folder.default_access_level,
        default_doc_type=folder.default_doc_type,
        default_language=folder.default_language,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )
