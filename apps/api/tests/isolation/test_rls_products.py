"""Product and delivery tables (0003): tenant A can never select, insert, update or delete tenant B's products,
product document sets, product releases and their items, customers, deliveries or machines.

The two release tables are insert-only for `seedoc_app` (and immutable for everyone, tests/immutability), so they get
the read and insert checks plus "update and delete are refused"; the other five get the same five checks as 0002."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Table, delete, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.db.base import Base
from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models import (
    AccessLevel,
    Customer,
    Delivery,
    DeliveryKind,
    DocType,
    Document,
    DocumentVersion,
    Folder,
    Machine,
    Product,
    ProductDocument,
    ProductRelease,
    ProductReleaseItem,
    Space,
)
from tests.isolation.conftest import AsApp, TwoTenants, insert_as


@dataclass(frozen=True)
class Catalog:
    """One row of every product/delivery table of one tenant, plus a document not yet in the product's set."""

    tenant_id: UUID
    document_id: UUID
    spare_document_id: UUID
    version_id: UUID
    spare_version_id: UUID
    product_id: UUID
    release_id: UUID
    release_item_id: UUID
    customer_id: UUID
    delivery_id: UUID
    machine_id: UUID


def _token() -> str:
    return secrets.token_urlsafe(32)


def new_product(cat: Catalog) -> Product:
    return Product(tenant_id=cat.tenant_id, name=f"Laser {secrets.token_hex(3)}")


def new_product_document(cat: Catalog) -> ProductDocument:
    return ProductDocument(tenant_id=cat.tenant_id, product_id=cat.product_id, document_id=cat.spare_document_id)


def new_release(cat: Catalog) -> ProductRelease:
    return ProductRelease(tenant_id=cat.tenant_id, product_id=cat.product_id, release_no=secrets.randbelow(10**6) + 10)


def new_release_item(cat: Catalog) -> ProductReleaseItem:
    return ProductReleaseItem(
        tenant_id=cat.tenant_id,
        release_id=cat.release_id,
        document_id=cat.spare_document_id,
        version_id=cat.spare_version_id,
        group_id=UUID(int=secrets.randbits(128)),
        title="Betriebsanleitung",
        doc_type=DocType.OPERATING_MANUAL,
        language="de",
        access_level=AccessLevel.PUBLIC,
        folder_path="Handbücher/Laser",
    )


def new_customer(cat: Catalog) -> Customer:
    return Customer(tenant_id=cat.tenant_id, name=f"Kunde {secrets.token_hex(3)}")


def new_delivery(cat: Catalog) -> Delivery:
    return Delivery(
        tenant_id=cat.tenant_id,
        customer_id=cat.customer_id,
        kind=DeliveryKind.SYSTEM,
        name=f"Anlage {secrets.token_hex(3)}",
        public_token=_token(),
    )


def new_machine(cat: Catalog) -> Machine:
    return Machine(
        tenant_id=cat.tenant_id,
        delivery_id=cat.delivery_id,
        product_id=cat.product_id,
        name="Laser 3030",
        serial_no=f"SN-{secrets.token_hex(4)}",
        public_token=_token(),
    )


def _document(tenant_id: UUID, folder_id: UUID) -> Document:
    return Document(
        tenant_id=tenant_id,
        folder_id=folder_id,
        title="Betriebsanleitung",
        doc_type=DocType.OPERATING_MANUAL,
        language="de",
        access_level=AccessLevel.PUBLIC,
    )


async def seed_catalog(db: AsyncSession, tenant_id: UUID) -> Catalog:
    space = Space(tenant_id=tenant_id, name="Handbücher")
    db.add(space)
    await db.flush()
    folder = Folder(tenant_id=tenant_id, space_id=space.id, name="Laser")
    db.add(folder)
    await db.flush()
    document, spare = _document(tenant_id, folder.id), _document(tenant_id, folder.id)
    db.add_all([document, spare])
    await db.flush()
    version, spare_version = (
        DocumentVersion(
            tenant_id=tenant_id,
            document_id=owner.id,
            version_no=1,
            storage_key=f"tenants/{tenant_id}/versions/{secrets.token_hex(8)}.pdf",
            file_name="manual.pdf",
            size_bytes=1024,
            sha256=hashlib.sha256(secrets.token_bytes(16)).digest(),
        )
        for owner in (document, spare)
    )
    product = Product(tenant_id=tenant_id, name="Laser 3030")
    customer = Customer(tenant_id=tenant_id, name="Muster AG")
    db.add_all([version, spare_version, product, customer])
    await db.flush()
    document.current_version_id = version.id
    release = ProductRelease(tenant_id=tenant_id, product_id=product.id, release_no=1)
    delivery = Delivery(
        tenant_id=tenant_id, customer_id=customer.id, kind=DeliveryKind.SYSTEM, name="Anlage", public_token=_token()
    )
    db.add_all(
        [ProductDocument(tenant_id=tenant_id, product_id=product.id, document_id=document.id), release, delivery]
    )
    await db.flush()
    item = ProductReleaseItem(
        tenant_id=tenant_id,
        release_id=release.id,
        document_id=document.id,
        version_id=version.id,
        group_id=document.group_id,
        title=document.title,
        doc_type=document.doc_type,
        language=document.language,
        access_level=document.access_level,
        folder_path="Handbücher/Laser",
    )
    machine = Machine(
        tenant_id=tenant_id,
        delivery_id=delivery.id,
        product_id=product.id,
        name="Laser 3030",
        serial_no=f"SN-{secrets.token_hex(4)}",
        public_token=_token(),
    )
    db.add_all([item, machine])
    await db.flush()
    return Catalog(
        tenant_id=tenant_id,
        document_id=document.id,
        spare_document_id=spare.id,
        version_id=version.id,
        spare_version_id=spare_version.id,
        product_id=product.id,
        release_id=release.id,
        release_item_id=item.id,
        customer_id=customer.id,
        delivery_id=delivery.id,
        machine_id=machine.id,
    )


@dataclass(frozen=True)
class TwoCatalogs:
    a: Catalog
    b: Catalog


@pytest.fixture
async def catalogs(two_tenants: TwoTenants) -> TwoCatalogs:
    async with get_admin_sessionmaker()() as db, db.begin():
        a = await seed_catalog(db, two_tenants.a.tenant_id)
        b = await seed_catalog(db, two_tenants.b.tenant_id)
    return TwoCatalogs(a, b)


@dataclass(frozen=True)
class TableCase:
    table: Table
    key: str  # a column that identifies the row (product_documents has a composite primary key)
    row_key: Callable[[Catalog], UUID]
    new_row: Callable[[Catalog], Base]
    change: dict[str, Any] | None  # None: immutable release table


def _case(
    name: str,
    row_key: Callable[[Catalog], UUID],
    new_row: Callable[[Catalog], Base],
    change: dict[str, Any] | None,
    key: str = "id",
) -> TableCase:
    return TableCase(Base.metadata.tables[name], key, row_key, new_row, change)


WRITABLE = [
    _case("products", lambda cat: cat.product_id, new_product, {"name": "Renamed"}),
    _case(
        "product_documents",
        lambda cat: cat.document_id,
        new_product_document,
        {"added_at": datetime.now(UTC)},
        key="document_id",
    ),
    _case("customers", lambda cat: cat.customer_id, new_customer, {"contact_name": "Erika Muster"}),
    _case("deliveries", lambda cat: cat.delivery_id, new_delivery, {"order_no": "A-4711"}),
    _case("machines", lambda cat: cat.machine_id, new_machine, {"sort_order": 3}),
]
RELEASES = [
    _case("product_releases", lambda cat: cat.release_id, new_release, None),
    _case("product_release_items", lambda cat: cat.release_item_id, new_release_item, None),
]
ALL = WRITABLE + RELEASES


def _ids(cases: list[TableCase]) -> list[str]:
    return [case.table.name for case in cases]


@pytest.mark.parametrize("case", ALL, ids=_ids(ALL))
async def test_no_tenant_set_sees_no_rows(catalogs: TwoCatalogs, as_app: AsApp, case: TableCase) -> None:
    async with as_app() as db:
        assert (await db.scalars(select(case.table.c[case.key]))).all() == []


@pytest.mark.parametrize("case", ALL, ids=_ids(ALL))
async def test_sees_only_own_rows(catalogs: TwoCatalogs, as_app: AsApp, case: TableCase) -> None:
    key = case.table.c[case.key]
    async with as_app(catalogs.a.tenant_id) as db:
        rows = (await db.execute(select(case.table.c.tenant_id, key))).all()
    assert {row.tenant_id for row in rows} == {catalogs.a.tenant_id}
    assert case.row_key(catalogs.a) in {row[1] for row in rows}


@pytest.mark.parametrize("case", ALL, ids=_ids(ALL))
async def test_cannot_insert_row_for_other_tenant(catalogs: TwoCatalogs, as_app: AsApp, case: TableCase) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await insert_as(as_app, catalogs.a.tenant_id, case.new_row(catalogs.b))


@pytest.mark.parametrize("case", WRITABLE, ids=_ids(WRITABLE))
async def test_cannot_update_or_delete_other_tenants_rows(
    catalogs: TwoCatalogs, as_app: AsApp, case: TableCase
) -> None:
    table, key, b_key = case.table, case.table.c[case.key], case.row_key(catalogs.b)
    assert case.change is not None
    async with as_app(catalogs.a.tenant_id) as db:
        updated = await db.scalars(update(table).where(key == b_key).values(**case.change).returning(key))
        assert updated.all() == []
        deleted = await db.scalars(delete(table).where(key == b_key).returning(key))
        assert deleted.all() == []

    async with get_admin_sessionmaker()() as admin:
        assert await admin.scalar(select(key).where(key == b_key)) == b_key


@pytest.mark.parametrize("case", WRITABLE, ids=_ids(WRITABLE))
async def test_own_rows_are_writable(catalogs: TwoCatalogs, as_app: AsApp, case: TableCase) -> None:
    """Guards against a policy that denies everything."""
    table, key = case.table, case.table.c[case.key]
    assert case.change is not None
    async with as_app(catalogs.a.tenant_id) as db:
        row = case.new_row(catalogs.a)
        db.add(row)
        await db.flush()
        row_key = getattr(row, case.key)
        changed = await db.scalars(update(table).where(key == row_key).values(**case.change).returning(key))
        assert changed.all() == [row_key]
        removed = await db.scalars(delete(table).where(key == row_key).returning(key))
        assert removed.all() == [row_key]


@pytest.mark.parametrize("case", RELEASES, ids=_ids(RELEASES))
async def test_own_release_rows_can_be_added_but_never_changed(
    catalogs: TwoCatalogs, as_app: AsApp, case: TableCase
) -> None:
    async with as_app(catalogs.a.tenant_id) as db:
        db.add(case.new_row(catalogs.a))
        await db.flush()  # insert is allowed

    for statement in (
        update(case.table).where(case.table.c.id == case.row_key(catalogs.a)).values(tenant_id=catalogs.a.tenant_id),
        delete(case.table).where(case.table.c.id == case.row_key(catalogs.a)),
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_app(catalogs.a.tenant_id) as db:
                await db.execute(statement)
