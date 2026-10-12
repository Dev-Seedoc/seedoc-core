"""`document_versions` (DATA_MODEL §4): a version's file fields never change; only the processing columns may.

The trigger runs for every role, so these tests write as `seedoc_admin` (BYPASSRLS) — not even the worker or staff
code can change a stored version.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from seedoc.db.engine import get_admin_sessionmaker
from seedoc.models import (
    AccessLevel,
    DocType,
    Document,
    DocumentVersion,
    Folder,
    ProcessingStatus,
    Space,
    Tenant,
)


@pytest.fixture
async def version_id(postgres: dict[str, str]) -> UUID:
    """A stored version (with its tenant, space, folder and document)."""
    async with get_admin_sessionmaker()() as db, db.begin():
        tenant = Tenant(name="Immutability GmbH", slug=f"immutability-{uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        space = Space(tenant_id=tenant.id, name="Handbücher")
        db.add(space)
        await db.flush()
        folder = Folder(tenant_id=tenant.id, space_id=space.id, name="Laser")
        db.add(folder)
        await db.flush()
        document = Document(
            tenant_id=tenant.id,
            folder_id=folder.id,
            title="Betriebsanleitung",
            doc_type=DocType.OPERATING_MANUAL,
            language="de",
            access_level=AccessLevel.PUBLIC,
        )
        db.add(document)
        await db.flush()
        version = DocumentVersion(
            tenant_id=tenant.id,
            document_id=document.id,
            version_no=1,
            storage_key=f"tenants/{tenant.id}/versions/{uuid4()}.pdf",
            file_name="betriebsanleitung.pdf",
            size_bytes=2048,
            sha256=hashlib.sha256(b"version 1").digest(),
        )
        db.add(version)
        await db.flush()
        document.current_version_id = version.id
    return version.id


@pytest.mark.parametrize(
    "change",
    [
        {"storage_key": "tenants/other/versions/x.pdf"},
        {"file_name": "renamed.pdf"},
        {"size_bytes": 1},
        {"sha256": hashlib.sha256(b"other file").digest()},
        {"version_no": 2},
        {"created_at": datetime(2020, 1, 1, tzinfo=UTC)},
    ],
    ids=lambda change: next(iter(change)),
)
async def test_file_fields_are_immutable(version_id: UUID, change: dict[str, Any]) -> None:
    with pytest.raises(DBAPIError, match="release_immutable"):
        async with get_admin_sessionmaker()() as db, db.begin():
            await db.execute(update(DocumentVersion).where(DocumentVersion.id == version_id).values(**change))


async def test_processing_columns_may_change(version_id: UUID) -> None:
    async with get_admin_sessionmaker()() as db, db.begin():
        await db.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(
                processing_status=ProcessingStatus.READY,
                processing_error=None,
                processed_at=datetime.now(UTC),
                page_count=72,
            )
        )
    async with get_admin_sessionmaker()() as db:
        version = await db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id))
    assert version is not None
    assert (version.processing_status, version.page_count) == (ProcessingStatus.READY, 72)


async def test_unreleased_version_can_be_deleted(version_id: UUID) -> None:
    """The purge job deletes never-released versions; 0004 adds the refusal for released ones."""
    async with get_admin_sessionmaker()() as db, db.begin():
        await db.execute(
            update(Document).where(Document.current_version_id == version_id).values(current_version_id=None)
        )
        deleted = await db.scalars(
            delete(DocumentVersion).where(DocumentVersion.id == version_id).returning(DocumentVersion.id)
        )
        assert deleted.all() == [version_id]
