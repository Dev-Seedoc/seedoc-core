"""Folders (API.md §3.2), following routers/app/spaces.py: HTTP only, one service function per operation_id. Every
route is open to any member of the tenant (`EditorCtx`)."""

from uuid import UUID

from fastapi import APIRouter, status

from seedoc.deps import DbSession, EditorCtx
from seedoc.schemas.common import Page
from seedoc.schemas.folders import FolderCreate, FolderRead, FolderUpdate
from seedoc.services import folders as folders_service

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("")
async def list_folders(space_id: UUID, db: DbSession, ctx: EditorCtx) -> Page[FolderRead]:
    return await folders_service.list_folders(db, ctx, space_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_folder(body: FolderCreate, db: DbSession, ctx: EditorCtx) -> FolderRead:
    return await folders_service.create_folder(db, ctx, body)


@router.patch("/{folder_id}")
async def update_folder(folder_id: UUID, body: FolderUpdate, db: DbSession, ctx: EditorCtx) -> FolderRead:
    return await folders_service.update_folder(db, ctx, folder_id, body)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: UUID, db: DbSession, ctx: EditorCtx) -> None:
    await folders_service.delete_folder(db, ctx, folder_id)
