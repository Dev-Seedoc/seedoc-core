"""Uploads (API.md §3.3): any member may start an upload."""

from fastapi import APIRouter, status

from seedoc.deps import DbSession, EditorCtx
from seedoc.schemas.uploads import UploadCreate, UploadRead
from seedoc.services import uploads as uploads_service

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_upload(body: UploadCreate, db: DbSession, ctx: EditorCtx) -> UploadRead:
    return await uploads_service.create_upload(db, ctx, body)
