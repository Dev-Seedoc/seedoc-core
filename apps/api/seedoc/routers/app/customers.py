"""Customers (API.md §3.5). HTTP only: parse, call the service function with the same name, return its schema. Every
member manages customers (`EditorCtx`, BUSINESS_RULES §1)."""

from uuid import UUID

from fastapi import APIRouter, status

from seedoc.deps import DbSession, EditorCtx
from seedoc.schemas.common import Page
from seedoc.schemas.deliveries import CustomerCreate, CustomerRead, CustomerUpdate
from seedoc.services import customers as customers_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
async def list_customers(db: DbSession, ctx: EditorCtx) -> Page[CustomerRead]:
    return await customers_service.list_customers(db, ctx)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_customer(body: CustomerCreate, db: DbSession, ctx: EditorCtx) -> CustomerRead:
    return await customers_service.create_customer(db, ctx, body)


@router.get("/{customer_id}")
async def get_customer(customer_id: UUID, db: DbSession, ctx: EditorCtx) -> CustomerRead:
    return await customers_service.get_customer(db, ctx, customer_id)


@router.patch("/{customer_id}")
async def update_customer(customer_id: UUID, body: CustomerUpdate, db: DbSession, ctx: EditorCtx) -> CustomerRead:
    return await customers_service.update_customer(db, ctx, customer_id, body)
