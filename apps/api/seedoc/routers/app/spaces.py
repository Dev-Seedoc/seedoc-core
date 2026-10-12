"""Spaces (API.md §3.2). The reference pattern for /app routers: HTTP only — parse, call one service function with
the same name, return its schema. Roles come from the `EditorCtx` / `AdminCtx` / `OwnerCtx` dependency."""

from uuid import UUID

from fastapi import APIRouter, status

from seedoc.deps import AdminCtx, DbSession, EditorCtx
from seedoc.schemas.common import Page
from seedoc.schemas.spaces import SpaceCreate, SpaceRead, SpaceUpdate
from seedoc.services import spaces as spaces_service

router = APIRouter(prefix="/spaces", tags=["spaces"])


@router.get("")
async def list_spaces(db: DbSession, ctx: EditorCtx) -> Page[SpaceRead]:
    return await spaces_service.list_spaces(db, ctx)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_space(body: SpaceCreate, db: DbSession, ctx: AdminCtx) -> SpaceRead:
    return await spaces_service.create_space(db, ctx, body)


@router.patch("/{space_id}")
async def update_space(space_id: UUID, body: SpaceUpdate, db: DbSession, ctx: AdminCtx) -> SpaceRead:
    return await spaces_service.update_space(db, ctx, space_id, body)
