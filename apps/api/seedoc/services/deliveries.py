"""Deliveries (API.md §3.5): what a customer received — one machine (`kind = machine`) or a system of several
(`kind = system`, with its own QR). Drafts, checks and publishing are `services/releases.py` (M2-B4/B5)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.deliveries import Customer, Delivery, DeliveryStatus, Machine
from seedoc.schemas.common import Page
from seedoc.schemas.deliveries import (
    DeliveryCreate,
    DeliveryListItem,
    DeliveryListQuery,
    DeliveryRead,
    DeliveryUpdate,
)
from seedoc.security.tokens import new_public_token
from seedoc.services.customers import get_tenant_customer
from seedoc.services.library import get_sort_key
from seedoc.services.machines import list_machine_items
from seedoc.services.portal import get_portal_url


async def list_deliveries(db: AsyncSession, ctx: RequestContext, query: DeliveryListQuery) -> Page[DeliveryListItem]:
    """Deliveries by name (DIN 5007-1), filtered by customer and status; never paged."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        statement = (
            select(Delivery, Customer.name)
            .join(Customer, Customer.id == Delivery.customer_id)
            .where(Delivery.tenant_id == tenant_id)
        )
        if query.customer_id is not None:
            statement = statement.where(Delivery.customer_id == query.customer_id)
        if query.status is not None:
            statement = statement.where(Delivery.status == query.status)
        rows = (await db.execute(statement)).all()
        count_rows = await db.execute(
            select(Machine.delivery_id, func.count())
            .where(Machine.tenant_id == tenant_id, Machine.delivery_id.in_([row[0].id for row in rows]))
            .group_by(Machine.delivery_id)
        )
        machine_counts: dict[UUID, int] = {row[0]: row[1] for row in count_rows}
        items = [
            DeliveryListItem(
                id=delivery.id,
                customer_id=delivery.customer_id,
                customer_name=customer_name,
                kind=delivery.kind,
                name=delivery.name,
                order_no=delivery.order_no,
                status=delivery.status,
                machine_count=machine_counts.get(delivery.id, 0),  # archived machines too
                current_release_no=None,  # the release tables come with M2-B4
                updated_at=delivery.updated_at,
            )
            for delivery, customer_name in rows
        ]
        items.sort(key=lambda item: (get_sort_key(item.name), item.id))
        return Page(items=items, next_cursor=None)


async def create_delivery(db: AsyncSession, ctx: RequestContext, body: DeliveryCreate) -> DeliveryRead:
    """Without `required_languages` the delivery starts with `[]`; `create_machine` adds the product languages."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        await get_tenant_customer(db, tenant_id, body.customer_id)
        delivery = Delivery(
            tenant_id=tenant_id,
            customer_id=body.customer_id,
            kind=body.kind,
            name=body.name,
            order_no=body.order_no,
            required_languages=body.required_languages if body.required_languages is not None else [],
            public_token=new_public_token(),  # the system QR; never changed afterwards
            created_by=ctx.user_id,
        )
        db.add(delivery)
        await db.flush()
        await db.refresh(delivery)  # status and timestamps come from the database
        await write_audit_event(db, ctx, "delivery.created", "delivery", delivery.id)
        return await _to_read(db, tenant_id, delivery)


async def get_delivery(db: AsyncSession, ctx: RequestContext, delivery_id: UUID) -> DeliveryRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        delivery = await get_tenant_delivery(db, tenant_id, delivery_id)
        return await _to_read(db, tenant_id, delivery)


async def update_delivery(
    db: AsyncSession, ctx: RequestContext, delivery_id: UUID, body: DeliveryUpdate
) -> DeliveryRead:
    """Change only the fields in the body (`null` clears `order_no`). The languages are fixed after the first publish
    (`409 conflict`). `delivery.updated` only on a real change."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        delivery = await get_tenant_delivery(db, tenant_id, delivery_id, for_update=True)
        changes = {
            field: value
            for field, value in body.model_dump(exclude_unset=True).items()
            if getattr(delivery, field) != value
        }
        if "required_languages" in changes and delivery.status != DeliveryStatus.DRAFT:
            raise AppError(
                ErrorCode.CONFLICT,
                "the languages are fixed after the first publish",
                details={"field": "required_languages"},
            )
        if changes:
            for field, value in changes.items():
                setattr(delivery, field, value)
            await db.flush()
            await db.refresh(delivery)  # the new updated_at
            await write_audit_event(db, ctx, "delivery.updated", "delivery", delivery.id, {"fields": sorted(changes)})
        return await _to_read(db, tenant_id, delivery)


async def get_tenant_delivery(
    db: AsyncSession, tenant_id: UUID, delivery_id: UUID, for_update: bool = False
) -> Delivery:
    """The tenant's delivery, or `404 not_found` (also for another tenant's id). Call inside a tenant transaction."""
    statement = select(Delivery).where(Delivery.id == delivery_id, Delivery.tenant_id == tenant_id)
    if for_update:
        statement = statement.with_for_update()
    delivery = await db.scalar(statement)
    if delivery is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return delivery


async def _to_read(db: AsyncSession, tenant_id: UUID, delivery: Delivery) -> DeliveryRead:
    customer = await get_tenant_customer(db, tenant_id, delivery.customer_id)
    return DeliveryRead(
        id=delivery.id,
        customer_id=delivery.customer_id,
        customer_name=customer.name,
        kind=delivery.kind,
        name=delivery.name,
        order_no=delivery.order_no,
        status=delivery.status,
        required_languages=list(delivery.required_languages),
        public_token=delivery.public_token,
        portal_url=await get_portal_url(db, tenant_id, "system", delivery.public_token),
        current_release_no=None,  # the release tables come with M2-B4
        has_open_draft=False,
        machines=await list_machine_items(db, tenant_id, delivery.id),
    )
