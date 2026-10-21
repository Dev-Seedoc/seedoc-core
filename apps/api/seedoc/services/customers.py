"""Customers (API.md §3.5): the manufacturer's customers, each with its deliveries."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.deliveries import Customer, Delivery
from seedoc.schemas.common import Page
from seedoc.schemas.deliveries import CustomerCreate, CustomerRead, CustomerUpdate
from seedoc.services.library import get_sort_key


async def list_customers(db: AsyncSession, ctx: RequestContext) -> Page[CustomerRead]:
    """All customers of the tenant by name (DIN 5007-1); never paged."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        customers = await db.scalars(select(Customer).where(Customer.tenant_id == tenant_id))
        ordered = sorted(customers, key=lambda customer: (get_sort_key(customer.name), customer.id))
        return Page(items=await _to_reads(db, tenant_id, ordered), next_cursor=None)


async def create_customer(db: AsyncSession, ctx: RequestContext, body: CustomerCreate) -> CustomerRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        customer = Customer(
            tenant_id=tenant_id, name=body.name, contact_name=body.contact_name, contact_email=body.contact_email
        )
        db.add(customer)
        await db.flush()
        await db.refresh(customer)  # created_at / updated_at come from the database
        await write_audit_event(db, ctx, "customer.created", "customer", customer.id)
        [read] = await _to_reads(db, tenant_id, [customer])
        return read


async def get_customer(db: AsyncSession, ctx: RequestContext, customer_id: UUID) -> CustomerRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        customer = await get_tenant_customer(db, tenant_id, customer_id)
        [read] = await _to_reads(db, tenant_id, [customer])
        return read


async def update_customer(
    db: AsyncSession, ctx: RequestContext, customer_id: UUID, body: CustomerUpdate
) -> CustomerRead:
    """Change only the fields in the body (`null` clears a contact field). `customer.updated` only on a real change."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        customer = await get_tenant_customer(db, tenant_id, customer_id, for_update=True)
        changes = {
            field: value
            for field, value in body.model_dump(exclude_unset=True).items()
            if getattr(customer, field) != value
        }
        if changes:
            for field, value in changes.items():
                setattr(customer, field, value)
            await db.flush()
            await db.refresh(customer)  # the new updated_at
            await write_audit_event(db, ctx, "customer.updated", "customer", customer.id, {"fields": sorted(changes)})
        [read] = await _to_reads(db, tenant_id, [customer])
        return read


async def get_tenant_customer(
    db: AsyncSession, tenant_id: UUID, customer_id: UUID, for_update: bool = False
) -> Customer:
    """The tenant's customer, or `404 not_found` (also for another tenant's id). Call inside a tenant transaction."""
    statement = select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
    if for_update:
        statement = statement.with_for_update()
    customer = await db.scalar(statement)
    if customer is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return customer


async def _to_reads(db: AsyncSession, tenant_id: UUID, customers: Sequence[Customer]) -> list[CustomerRead]:
    """`CustomerRead`s in the given order; `delivery_count` comes from one query for all of them."""
    customer_ids = [customer.id for customer in customers]
    if not customer_ids:
        return []
    rows = await db.execute(
        select(Delivery.customer_id, func.count())
        .where(Delivery.tenant_id == tenant_id, Delivery.customer_id.in_(customer_ids))
        .group_by(Delivery.customer_id)
    )
    delivery_counts: dict[UUID, int] = {row[0]: row[1] for row in rows}
    return [
        CustomerRead(
            id=customer.id,
            name=customer.name,
            contact_name=customer.contact_name,
            contact_email=customer.contact_email,
            delivery_count=delivery_counts.get(customer.id, 0),
            created_at=customer.created_at,
            updated_at=customer.updated_at,
        )
        for customer in customers
    ]
