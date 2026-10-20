"""`product_releases` and `product_release_items` (DATA_MODEL §4): written once, never updated or deleted — by any
role, so these tests write as `seedoc_admin` (BYPASSRLS)."""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models import DocumentVersion, ProductRelease, ProductReleaseItem, Tenant
from tests.isolation.test_rls_products import Catalog, seed_catalog


@pytest.fixture
async def catalog(postgres: dict[str, str]) -> Catalog:
    async with get_admin_sessionmaker()() as db, db.begin():
        tenant = Tenant(name="Immutability GmbH", slug=f"immutability-{uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        return await seed_catalog(db, tenant.id)


def _statements(catalog: Catalog) -> list[tuple[str, Any]]:
    return [
        (
            "update release",
            update(ProductRelease).where(ProductRelease.id == catalog.release_id).values(change_note="x"),
        ),
        ("delete release", delete(ProductRelease).where(ProductRelease.id == catalog.release_id)),
        (
            "update item",
            update(ProductReleaseItem).where(ProductReleaseItem.id == catalog.release_item_id).values(title="Neu"),
        ),
        ("delete item", delete(ProductReleaseItem).where(ProductReleaseItem.id == catalog.release_item_id)),
    ]


@pytest.mark.parametrize("index", range(4), ids=["update_release", "delete_release", "update_item", "delete_item"])
async def test_product_release_rows_never_change(catalog: Catalog, index: int) -> None:
    _, statement = _statements(catalog)[index]

    with pytest.raises(DBAPIError, match="release_immutable"):
        async with get_admin_sessionmaker()() as db, db.begin():
            await db.execute(statement)


async def test_a_released_version_cannot_be_deleted(catalog: Catalog) -> None:
    """The release item's foreign key keeps the version (and so its document) — what `purge_trash` relies on."""
    async with get_admin_sessionmaker()() as db, db.begin():
        with pytest.raises(DBAPIError, match="foreign key"):
            await db.execute(delete(DocumentVersion).where(DocumentVersion.id == catalog.version_id))
