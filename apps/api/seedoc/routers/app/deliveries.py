"""Deliveries (API.md §3.5). HTTP only: parse, call the service function with the same name, return its schema.
Every member manages deliveries (`EditorCtx`, BUSINESS_RULES §1)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from seedoc.deps import DbSession, EditorCtx
from seedoc.schemas.common import Page
from seedoc.schemas.deliveries import (
    DeliveryCreate,
    DeliveryListItem,
    DeliveryListQuery,
    DeliveryRead,
    DeliveryUpdate,
    MachineCreate,
    MachineRead,
)
from seedoc.services import deliveries as deliveries_service
from seedoc.services import machines as machines_service

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("")
async def list_deliveries(
    query: Annotated[DeliveryListQuery, Query()], db: DbSession, ctx: EditorCtx
) -> Page[DeliveryListItem]:
    return await deliveries_service.list_deliveries(db, ctx, query)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_delivery(body: DeliveryCreate, db: DbSession, ctx: EditorCtx) -> DeliveryRead:
    return await deliveries_service.create_delivery(db, ctx, body)


@router.get("/{delivery_id}")
async def get_delivery(delivery_id: UUID, db: DbSession, ctx: EditorCtx) -> DeliveryRead:
    return await deliveries_service.get_delivery(db, ctx, delivery_id)


@router.patch("/{delivery_id}")
async def update_delivery(delivery_id: UUID, body: DeliveryUpdate, db: DbSession, ctx: EditorCtx) -> DeliveryRead:
    return await deliveries_service.update_delivery(db, ctx, delivery_id, body)


@router.post("/{delivery_id}/machines", status_code=status.HTTP_201_CREATED)
async def create_machine(delivery_id: UUID, body: MachineCreate, db: DbSession, ctx: EditorCtx) -> MachineRead:
    return await machines_service.create_machine(db, ctx, delivery_id, body)
