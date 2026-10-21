"""Machines (API.md §3.5): one machine (`kind = machine`) or several (`kind = system`) per delivery, each with its own
QR token, and its machine-specific documents."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.audit import write_audit_event
from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.deliveries import Delivery, DeliveryKind, DeliveryStatus, Machine
from seedoc.models.documents import Document
from seedoc.models.products import Product, ProductDocument
from seedoc.schemas.common import Page
from seedoc.schemas.deliveries import (
    MachineCreate,
    MachineDocumentAttach,
    MachineListItem,
    MachineRead,
    MachineUpdate,
)
from seedoc.schemas.documents import DocumentListItem
from seedoc.security.tokens import new_public_token
from seedoc.services.documents import list_document_items
from seedoc.services.portal import get_portal_url

_SERIAL_NO_CONSTRAINT = "uq_machines_tenant_id_serial_no"


async def create_machine(db: AsyncSession, ctx: RequestContext, delivery_id: UUID, body: MachineCreate) -> MachineRead:
    """Add a machine to the delivery. `kind = machine` takes exactly one (archived ones count, `409 conflict`). While
    the delivery is a draft, the product's languages it does not have yet are appended. A serial number already used
    in the tenant → `409 conflict`."""
    try:
        async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
            # Locked before counting, so two requests cannot both add the only machine of a `kind = machine` delivery.
            delivery = await db.scalar(
                select(Delivery).where(Delivery.id == delivery_id, Delivery.tenant_id == tenant_id).with_for_update()
            )
            if delivery is None:
                raise AppError(ErrorCode.NOT_FOUND)
            product = await db.scalar(
                select(Product).where(Product.id == body.product_id, Product.tenant_id == tenant_id)
            )
            if product is None:
                raise AppError(ErrorCode.NOT_FOUND)
            if delivery.kind == DeliveryKind.MACHINE:
                existing = await db.scalar(
                    select(func.count())
                    .select_from(Machine)
                    .where(Machine.tenant_id == tenant_id, Machine.delivery_id == delivery.id)
                )
                if existing:
                    raise AppError(ErrorCode.CONFLICT, "a machine delivery has exactly one machine")
            if delivery.status == DeliveryStatus.DRAFT:
                missing = [lang for lang in product.required_languages if lang not in delivery.required_languages]
                if missing:
                    delivery.required_languages = [*delivery.required_languages, *missing]

            machine = Machine(
                tenant_id=tenant_id,
                delivery_id=delivery.id,
                product_id=product.id,
                name=body.name,
                serial_no=body.serial_no,
                public_token=new_public_token(),  # the machine QR; never changed afterwards
            )
            db.add(machine)
            await db.flush()
            await db.refresh(machine)  # sort_order and timestamps come from the database
            await write_audit_event(db, ctx, "machine.created", "machine", machine.id)
            return await _to_read(db, tenant_id, machine)
    except IntegrityError as exc:
        if _SERIAL_NO_CONSTRAINT in str(exc.orig):
            raise _serial_no_conflict() from exc
        raise


async def get_machine(db: AsyncSession, ctx: RequestContext, machine_id: UUID) -> MachineRead:
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        machine = await get_tenant_machine(db, tenant_id, machine_id)
        return await _to_read(db, tenant_id, machine)


async def update_machine(db: AsyncSession, ctx: RequestContext, machine_id: UUID, body: MachineUpdate) -> MachineRead:
    """Change only the fields in the body. An archived machine is read-only (`409 conflict`); a serial number already
    used in the tenant → `409 conflict`. `machine.updated` only on a real change."""
    try:
        async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
            machine = await get_tenant_machine(db, tenant_id, machine_id, for_update=True)
            _ensure_not_archived(machine)
            changes = {
                field: value
                for field, value in body.model_dump(exclude_unset=True).items()
                if getattr(machine, field) != value
            }
            if changes:
                for field, value in changes.items():
                    setattr(machine, field, value)
                await db.flush()
                await db.refresh(machine)  # the new updated_at
                await write_audit_event(db, ctx, "machine.updated", "machine", machine.id, {"fields": sorted(changes)})
            return await _to_read(db, tenant_id, machine)
    except IntegrityError as exc:
        if _SERIAL_NO_CONSTRAINT in str(exc.orig):
            raise _serial_no_conflict() from exc
        raise


async def archive_machine(db: AsyncSession, ctx: RequestContext, machine_id: UUID) -> MachineRead:
    """Archive the machine (admin, owner). Archiving again changes nothing: same `archived_at`, no second audit."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        machine = await get_tenant_machine(db, tenant_id, machine_id, for_update=True)
        if machine.archived_at is None:
            machine.archived_at = func.now()
            await db.flush()
            await db.refresh(machine)
            await write_audit_event(db, ctx, "machine.archived", "machine", machine.id)
        return await _to_read(db, tenant_id, machine)


async def list_machine_documents(db: AsyncSession, ctx: RequestContext, machine_id: UUID) -> Page[DocumentListItem]:
    """The machine's untrashed machine-specific documents by title, then language; never paged."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        machine = await get_tenant_machine(db, tenant_id, machine_id)
        document_ids = list(
            await db.scalars(
                select(Document.id).where(Document.tenant_id == tenant_id, Document.machine_id == machine.id)
            )
        )
        items = await list_document_items(db, tenant_id, document_ids)
        return Page(items=[item for item in items if item.trashed_at is None], next_cursor=None)


async def attach_machine_document(
    db: AsyncSession, ctx: RequestContext, machine_id: UUID, body: MachineDocumentAttach
) -> DocumentListItem:
    """Make the document specific to this machine (`documents.machine_id`). Already attached here → nothing changes
    (no audit). Trashed, attached to another machine, in a product's document set, or the machine is archived →
    `409 conflict`."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        machine = await get_tenant_machine(db, tenant_id, machine_id)
        _ensure_not_archived(machine)
        # Locked, so a parallel `set_product_documents` (which locks the same row) cannot add it to a product at the
        # same time.
        document = await db.scalar(
            select(Document).where(Document.id == body.document_id, Document.tenant_id == tenant_id).with_for_update()
        )
        if document is None:
            raise AppError(ErrorCode.NOT_FOUND)
        if document.machine_id != machine.id:
            if document.trashed_at is not None:
                raise AppError(ErrorCode.CONFLICT, "the document is in the trash; restore it first")
            if document.machine_id is not None:
                raise AppError(ErrorCode.CONFLICT, "the document belongs to another machine")
            in_product = await db.scalar(
                select(ProductDocument.product_id)
                .where(ProductDocument.tenant_id == tenant_id, ProductDocument.document_id == document.id)
                .limit(1)
            )
            if in_product is not None:
                raise AppError(ErrorCode.CONFLICT, "the document belongs to a product's document set")
            document.machine_id = machine.id
            await db.flush()
            await write_audit_event(
                db, ctx, "machine.document_attached", "machine", machine.id, {"document_id": str(document.id)}
            )
        [item] = await list_document_items(db, tenant_id, [document.id])
        return item


async def detach_machine_document(db: AsyncSession, ctx: RequestContext, machine_id: UUID, document_id: UUID) -> None:
    """Make the document general again. Not attached to this machine → `404 not_found`; the machine is archived →
    `409 conflict`."""
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        machine = await get_tenant_machine(db, tenant_id, machine_id)
        document = await db.scalar(
            select(Document)
            .where(Document.id == document_id, Document.tenant_id == tenant_id, Document.machine_id == machine.id)
            .with_for_update()
        )
        if document is None:
            raise AppError(ErrorCode.NOT_FOUND)
        _ensure_not_archived(machine)
        document.machine_id = None
        await db.flush()
        await write_audit_event(
            db, ctx, "machine.document_detached", "machine", machine.id, {"document_id": str(document.id)}
        )


async def get_tenant_machine(db: AsyncSession, tenant_id: UUID, machine_id: UUID, for_update: bool = False) -> Machine:
    """The tenant's machine, or `404 not_found` (also for another tenant's id). Call inside a tenant transaction."""
    statement = select(Machine).where(Machine.id == machine_id, Machine.tenant_id == tenant_id)
    if for_update:
        statement = statement.with_for_update()
    machine = await db.scalar(statement)
    if machine is None:
        raise AppError(ErrorCode.NOT_FOUND)
    return machine


async def list_machine_items(db: AsyncSession, tenant_id: UUID, delivery_id: UUID) -> list[MachineListItem]:
    """The delivery's machines (archived ones too) by `sort_order`, then `created_at`. Call inside a tenant
    transaction."""
    machines = await db.scalars(
        select(Machine)
        .where(Machine.tenant_id == tenant_id, Machine.delivery_id == delivery_id)
        .order_by(Machine.sort_order, Machine.created_at, Machine.id)
    )
    return await _to_list_items(db, tenant_id, list(machines))


def _ensure_not_archived(machine: Machine) -> None:
    if machine.archived_at is not None:
        raise AppError(ErrorCode.CONFLICT, "the machine is archived")


def _serial_no_conflict() -> AppError:
    """A serial number already used in the tenant (`uq_machines_tenant_id_serial_no`); other integrity errors stay
    a 500."""
    return AppError(ErrorCode.CONFLICT, "serial number already in use", details={"field": "serial_no"})


async def _to_read(db: AsyncSession, tenant_id: UUID, machine: Machine) -> MachineRead:
    [item] = await _to_list_items(db, tenant_id, [machine])
    return MachineRead(**item.model_dump(), delivery_id=machine.delivery_id)


async def _to_list_items(db: AsyncSession, tenant_id: UUID, machines: Sequence[Machine]) -> list[MachineListItem]:
    product_ids = {machine.product_id for machine in machines}
    if not product_ids:
        return []
    rows = await db.execute(
        select(Product.id, Product.name).where(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
    )
    product_names: dict[UUID, str] = {row[0]: row[1] for row in rows}
    return [
        MachineListItem(
            id=machine.id,
            product_id=machine.product_id,
            product_name=product_names[machine.product_id],
            name=machine.name,
            serial_no=machine.serial_no,
            public_token=machine.public_token,
            portal_url=await get_portal_url(db, tenant_id, "machine", machine.public_token),
            first_published_at=machine.first_published_at,
            archived_at=machine.archived_at,
        )
        for machine in machines
    ]
