"""Documents and versions (API.md §3.3): any member (`EditorCtx`). HTTP only; the rules live in
services/documents.py."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from seedoc.deps import DbSession, EditorCtx
from seedoc.schemas.common import Page
from seedoc.schemas.documents import (
    DocumentCreate,
    DocumentListItem,
    DocumentListQuery,
    DocumentRead,
    DocumentUpdate,
    DocumentVersionCreate,
    DocumentVersionRead,
    VersionFileUrlRead,
)
from seedoc.services import documents as documents_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
async def list_documents(
    query: Annotated[DocumentListQuery, Query()], db: DbSession, ctx: EditorCtx
) -> Page[DocumentListItem]:
    return await documents_service.list_documents(db, ctx, query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_document(body: DocumentCreate, db: DbSession, ctx: EditorCtx) -> DocumentRead:
    return await documents_service.create_document(db, ctx, body)


@router.get("/{document_id}")
async def get_document(document_id: UUID, db: DbSession, ctx: EditorCtx) -> DocumentRead:
    return await documents_service.get_document(db, ctx, document_id)


@router.patch("/{document_id}")
async def update_document(document_id: UUID, body: DocumentUpdate, db: DbSession, ctx: EditorCtx) -> DocumentRead:
    return await documents_service.update_document(db, ctx, document_id, body)


@router.post("/{document_id}/trash")
async def trash_document(document_id: UUID, db: DbSession, ctx: EditorCtx) -> DocumentRead:
    return await documents_service.trash_document(db, ctx, document_id)


@router.post("/{document_id}/restore")
async def restore_document(document_id: UUID, db: DbSession, ctx: EditorCtx) -> DocumentRead:
    return await documents_service.restore_document(db, ctx, document_id)


@router.get("/{document_id}/versions")
async def list_document_versions(document_id: UUID, db: DbSession, ctx: EditorCtx) -> Page[DocumentVersionRead]:
    return await documents_service.list_document_versions(db, ctx, document_id)


@router.post("/{document_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_document_version(
    document_id: UUID, body: DocumentVersionCreate, db: DbSession, ctx: EditorCtx
) -> DocumentVersionRead:
    return await documents_service.create_document_version(db, ctx, document_id, body)


@router.get("/{document_id}/versions/{version_id}/file")
async def get_version_file_url(
    document_id: UUID, version_id: UUID, db: DbSession, ctx: EditorCtx
) -> VersionFileUrlRead:
    return await documents_service.get_version_file_url(db, ctx, document_id, version_id)
