"""Document tables (0002): tenant A can never select, insert, update or delete tenant B's spaces, folders, uploads,
documents, document versions or text chunks. One parametrized suite, the same five checks for every table."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Table, delete, inspect, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.db.base import Base
from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models import (
    AccessLevel,
    DocType,
    Document,
    DocumentVersion,
    Folder,
    Space,
    TextChunk,
    Upload,
)
from tests.isolation.conftest import AsApp, TwoTenants, insert_as


@dataclass(frozen=True)
class Library:
    """One row of every document table, all belonging to one tenant."""

    tenant_id: UUID
    space_id: UUID
    folder_id: UUID
    upload_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_id: int


def new_space(lib: Library) -> Space:
    return Space(tenant_id=lib.tenant_id, name=f"Space {secrets.token_hex(3)}")


def new_folder(lib: Library) -> Folder:
    return Folder(tenant_id=lib.tenant_id, space_id=lib.space_id, name=f"Folder {secrets.token_hex(3)}")


def new_upload(lib: Library) -> Upload:
    return Upload(
        tenant_id=lib.tenant_id,
        storage_key=f"tenants/{lib.tenant_id}/uploads/{secrets.token_hex(8)}",
        file_name="manual.pdf",
        size_bytes=1024,
        sha256=hashlib.sha256(secrets.token_bytes(16)).digest(),
        content_type="application/pdf",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )


def new_document(lib: Library) -> Document:
    return Document(
        tenant_id=lib.tenant_id,
        folder_id=lib.folder_id,
        title=f"Manual {secrets.token_hex(3)}",
        doc_type=DocType.OPERATING_MANUAL,
        language="de",
        access_level=AccessLevel.PUBLIC,
    )


def new_version(lib: Library, version_no: int | None = None) -> DocumentVersion:
    return DocumentVersion(
        tenant_id=lib.tenant_id,
        document_id=lib.document_id,
        version_no=version_no or secrets.randbelow(10**6) + 100,
        storage_key=f"tenants/{lib.tenant_id}/versions/{secrets.token_hex(8)}.pdf",
        file_name="manual.pdf",
        size_bytes=1024,
        sha256=hashlib.sha256(secrets.token_bytes(16)).digest(),
    )


def new_chunk(lib: Library) -> TextChunk:
    return TextChunk(
        tenant_id=lib.tenant_id,
        version_id=lib.version_id,
        page_no=1,
        chunk_index=secrets.randbelow(10**6) + 100,
        content="Vor Wartungsarbeiten den Hauptschalter ausschalten.",
        ts_config="german",
    )


async def _seed_library(db: AsyncSession, tenant_id: UUID) -> Library:
    space = Space(tenant_id=tenant_id, name="Handbücher")
    db.add(space)
    await db.flush()
    folder = Folder(tenant_id=tenant_id, space_id=space.id, name="Laser")
    db.add(folder)
    await db.flush()
    partial = Library(tenant_id, space.id, folder.id, UUID(int=0), UUID(int=0), UUID(int=0), 0)
    upload = new_upload(partial)
    document = new_document(partial)
    db.add_all([upload, document])
    await db.flush()
    version = new_version(Library(tenant_id, space.id, folder.id, upload.id, document.id, UUID(int=0), 0), 1)
    db.add(version)
    await db.flush()
    document.current_version_id = version.id
    chunk = new_chunk(Library(tenant_id, space.id, folder.id, upload.id, document.id, version.id, 0))
    db.add(chunk)
    await db.flush()
    return Library(tenant_id, space.id, folder.id, upload.id, document.id, version.id, chunk.id)


@dataclass(frozen=True)
class TwoLibraries:
    a: Library
    b: Library


@pytest.fixture
async def libraries(two_tenants: TwoTenants) -> TwoLibraries:
    async with get_admin_sessionmaker()() as db, db.begin():
        a = await _seed_library(db, two_tenants.a.tenant_id)
        b = await _seed_library(db, two_tenants.b.tenant_id)
    return TwoLibraries(a, b)


@dataclass(frozen=True)
class TableCase:
    table: Table
    row_id: Callable[[Library], UUID | int]
    new_row: Callable[[Library], Base]
    # A harmless change for the update checks (for versions one the immutability trigger allows).
    change: dict[str, Any]


def _case(
    name: str, row_id: Callable[[Library], UUID | int], new_row: Callable[[Library], Base], change: dict[str, Any]
) -> TableCase:
    return TableCase(Base.metadata.tables[name], row_id, new_row, change)


CASES = [
    _case("spaces", lambda lib: lib.space_id, new_space, {"name": "Renamed"}),
    _case("folders", lambda lib: lib.folder_id, new_folder, {"sort_order": 7}),
    _case("uploads", lambda lib: lib.upload_id, new_upload, {"consumed_at": datetime.now(UTC)}),
    _case("documents", lambda lib: lib.document_id, new_document, {"title": "Renamed"}),
    _case("document_versions", lambda lib: lib.version_id, new_version, {"page_count": 12}),
    _case("text_chunks", lambda lib: lib.chunk_id, new_chunk, {"heading": "Wartung"}),
]

pytestmark = pytest.mark.parametrize("case", CASES, ids=[case.table.name for case in CASES])


async def test_no_tenant_set_sees_no_rows(libraries: TwoLibraries, as_app: AsApp, case: TableCase) -> None:
    async with as_app() as db:
        assert (await db.scalars(select(case.table.c.id))).all() == []


async def test_sees_only_own_rows(libraries: TwoLibraries, as_app: AsApp, case: TableCase) -> None:
    async with as_app(libraries.a.tenant_id) as db:
        rows = (await db.execute(select(case.table.c.tenant_id, case.table.c.id))).all()
    assert {row.tenant_id for row in rows} == {libraries.a.tenant_id}
    assert case.row_id(libraries.a) in {row.id for row in rows}


async def test_cannot_insert_row_for_other_tenant(libraries: TwoLibraries, as_app: AsApp, case: TableCase) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        await insert_as(as_app, libraries.a.tenant_id, case.new_row(libraries.b))


async def test_cannot_update_or_delete_other_tenants_rows(
    libraries: TwoLibraries, as_app: AsApp, case: TableCase
) -> None:
    table, b_id = case.table, case.row_id(libraries.b)
    async with as_app(libraries.a.tenant_id) as db:
        updated = await db.scalars(update(table).where(table.c.id == b_id).values(**case.change).returning(table.c.id))
        assert updated.all() == []
        deleted = await db.scalars(delete(table).where(table.c.id == b_id).returning(table.c.id))
        assert deleted.all() == []

    async with get_admin_sessionmaker()() as admin:
        assert await admin.scalar(select(table.c.id).where(table.c.id == b_id)) == b_id


async def test_own_rows_are_writable(libraries: TwoLibraries, as_app: AsApp, case: TableCase) -> None:
    """Guards against a policy that denies everything."""
    table = case.table
    async with as_app(libraries.a.tenant_id) as db:
        row = case.new_row(libraries.a)
        db.add(row)
        await db.flush()
        identity = inspect(row).identity
        assert identity is not None
        row_id = identity[0]
        changed = await db.scalars(
            update(table).where(table.c.id == row_id).values(**case.change).returning(table.c.id)
        )
        assert changed.all() == [row_id]
        removed = await db.scalars(delete(table).where(table.c.id == row_id).returning(table.c.id))
        assert removed.all() == [row_id]
