"""Machines (API.md §3.5; created under their delivery, `routers/app/deliveries.py`). HTTP only: parse, call the
service function with the same name, return its schema. Archiving is for admins and owners (BUSINESS_RULES §1)."""

from uuid import UUID

from fastapi import APIRouter, status

from seedoc.deps import AdminCtx, DbSession, EditorCtx
from seedoc.schemas.common import Page
from seedoc.schemas.deliveries import MachineDocumentAttach, MachineRead, MachineUpdate
from seedoc.schemas.documents import DocumentListItem
from seedoc.services import machines as machines_service

router = APIRouter(prefix="/machines", tags=["machines"])


@router.get("/{machine_id}")
async def get_machine(machine_id: UUID, db: DbSession, ctx: EditorCtx) -> MachineRead:
    return await machines_service.get_machine(db, ctx, machine_id)


@router.patch("/{machine_id}")
async def update_machine(machine_id: UUID, body: MachineUpdate, db: DbSession, ctx: EditorCtx) -> MachineRead:
    return await machines_service.update_machine(db, ctx, machine_id, body)


@router.post("/{machine_id}/archive")
async def archive_machine(machine_id: UUID, db: DbSession, ctx: AdminCtx) -> MachineRead:
    return await machines_service.archive_machine(db, ctx, machine_id)


@router.get("/{machine_id}/documents")
async def list_machine_documents(machine_id: UUID, db: DbSession, ctx: EditorCtx) -> Page[DocumentListItem]:
    return await machines_service.list_machine_documents(db, ctx, machine_id)


@router.post("/{machine_id}/documents")
async def attach_machine_document(
    machine_id: UUID, body: MachineDocumentAttach, db: DbSession, ctx: EditorCtx
) -> DocumentListItem:
    return await machines_service.attach_machine_document(db, ctx, machine_id, body)


@router.delete("/{machine_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_machine_document(machine_id: UUID, document_id: UUID, db: DbSession, ctx: EditorCtx) -> None:
    await machines_service.detach_machine_document(db, ctx, machine_id, document_id)
