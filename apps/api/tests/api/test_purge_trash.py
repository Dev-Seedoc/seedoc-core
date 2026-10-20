"""`purge_trash` (M1-A7, BUSINESS_RULES §3, ARCHITECTURE §11), against real Postgres and S3.

Until the release tables exist (0004) every document counts as released, so nothing is purged. The deletion itself
is tested with "never released" forced, so it is ready when the real check arrives.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings
from seedoc.jobs.app import app as job_app
from seedoc.jobs.maintenance import MAINTENANCE_QUEUE
from seedoc.models import AuditEvent, Document, DocumentVersion, MemberRole, TextChunk
from seedoc.services import trash as trash_service
from seedoc.storage.s3 import get_s3_client
from tests.conftest import ClientAs, MemberClient, RunJobs
from tests.pdfs import make_pdf

pytestmark = pytest.mark.usefixtures("postgres", "s3")


@dataclass(frozen=True)
class Library:
    editor: MemberClient
    folder_id: str

    @property
    def base(self) -> str:
        return f"/api/v1/app/tenants/{self.editor.tenant.id}"


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    owner = await client_as(MemberRole.OWNER)
    editor = await client_as(MemberRole.EDITOR, tenant=owner.tenant)
    base = f"/api/v1/app/tenants/{owner.tenant.id}"
    space = (await owner.http.post(f"{base}/spaces", json={"name": "Handbücher"})).json()
    folder = (
        await editor.http.post(
            f"{base}/folders",
            json={
                "space_id": space["id"],
                "name": "Laser",
                "default_access_level": "customer",
                "default_doc_type": "operating_manual",
                "default_language": "de",
            },
        )
    ).json()
    return Library(editor=editor, folder_id=folder["id"])


@pytest.fixture
def never_released(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the real check answers for these documents once the release tables exist."""

    async def no_release(*_: object) -> bool:
        return False

    monkeypatch.setattr(trash_service, "is_document_released", no_release)


async def _upload(lib: Library, text: str) -> str:
    data = make_pdf([text])
    response = await lib.editor.http.post(
        f"{lib.base}/uploads",
        json={
            "file_name": "Anleitung.pdf",
            "size_bytes": len(data),
            "sha256_hex": hashlib.sha256(data).hexdigest(),
            "content_type": "application/pdf",
        },
    )
    assert response.status_code == 201, response.text
    async with httpx.AsyncClient() as browser:
        stored = await browser.put(
            response.json()["upload_url"], content=data, headers={"Content-Type": "application/pdf"}
        )
    assert stored.status_code == 200
    return response.json()["upload_id"]


async def _document(lib: Library, *, versions: int = 1) -> dict[str, Any]:
    response = await lib.editor.http.post(
        f"{lib.base}/documents",
        json={"upload_id": await _upload(lib, "Version 1"), "folder_id": lib.folder_id, "title": "Anleitung"},
    )
    assert response.status_code == 201, response.text
    document = response.json()
    for number in range(2, versions + 1):
        added = await lib.editor.http.post(
            f"{lib.base}/documents/{document['id']}/versions",
            json={"upload_id": await _upload(lib, f"Version {number}")},
        )
        assert added.status_code == 201, added.text
    return document


async def _trash(lib: Library, admin_db: AsyncSession, document: dict[str, Any], days_ago: float) -> None:
    response = await lib.editor.http.post(f"{lib.base}/documents/{document['id']}/trash")
    assert response.status_code == 200, response.text
    await admin_db.execute(
        update(Document)
        .where(Document.id == UUID(document["id"]))
        .values(trashed_at=datetime.now(UTC) - timedelta(days=days_ago))
    )
    await admin_db.commit()


async def _exists(admin_db: AsyncSession, document: dict[str, Any]) -> bool:
    count = await admin_db.scalar(select(func.count()).where(Document.id == UUID(document["id"])))
    return count == 1


async def _version_keys(admin_db: AsyncSession, document: dict[str, Any]) -> list[str]:
    return list(
        await admin_db.scalars(
            select(DocumentVersion.storage_key).where(DocumentVersion.document_id == UUID(document["id"]))
        )
    )


def _stored_versions(key: str) -> int:
    listing = get_s3_client().list_object_versions(Bucket=get_settings().s3_bucket, Prefix=key)
    return len([*listing.get("Versions", []), *listing.get("DeleteMarkers", [])])


async def test_nothing_is_purged_while_release_tables_are_missing(lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib)
    await _trash(lib, admin_db, document, days_ago=45)

    result = await trash_service.purge_trash()

    assert result.purged == 0
    assert result.kept_released >= 1
    assert await _exists(admin_db, document)


@pytest.mark.usefixtures("never_released")
async def test_an_old_trashed_document_is_purged_with_versions_chunks_and_files(
    lib: Library, admin_db: AsyncSession, run_jobs: RunJobs
) -> None:
    document = await _document(lib, versions=2)
    await run_jobs()  # processing gives the versions chunks
    keys = await _version_keys(admin_db, document)
    version_ids = list(
        await admin_db.scalars(select(DocumentVersion.id).where(DocumentVersion.document_id == UUID(document["id"])))
    )
    assert len(keys) == 2
    assert await admin_db.scalar(select(func.count()).where(TextChunk.version_id.in_(version_ids))) == 2
    await _trash(lib, admin_db, document, days_ago=31)

    result = await trash_service.purge_trash()

    assert result.purged >= 1
    assert not await _exists(admin_db, document)
    assert await admin_db.scalar(select(func.count()).where(DocumentVersion.id.in_(version_ids))) == 0
    assert await admin_db.scalar(select(func.count()).where(TextChunk.version_id.in_(version_ids))) == 0
    assert [_stored_versions(key) for key in keys] == [0, 0]
    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == UUID(document["id"]), AuditEvent.action == "document.purged")
    )
    assert event is not None
    assert (event.tenant_id, event.actor_id, event.entity, event.detail) == (
        lib.editor.tenant.id,
        None,
        "document",
        {"version_count": 2},
    )


@pytest.mark.usefixtures("never_released")
async def test_recently_trashed_and_untrashed_documents_stay(lib: Library, admin_db: AsyncSession) -> None:
    recent, kept = await _document(lib), await _document(lib)
    await _trash(lib, admin_db, recent, days_ago=29)

    await trash_service.purge_trash()

    assert await _exists(admin_db, recent)
    assert await _exists(admin_db, kept)
    restore = await lib.editor.http.post(f"{lib.base}/documents/{recent['id']}/restore")
    assert restore.status_code == 200  # still restorable within the 30 days


@pytest.mark.usefixtures("never_released")
async def test_a_purged_document_frees_its_folder(lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib)
    await _trash(lib, admin_db, document, days_ago=31)
    blocked = await lib.editor.http.delete(f"{lib.base}/folders/{lib.folder_id}")
    assert blocked.status_code == 409  # a trashed document still holds the folder

    await trash_service.purge_trash()

    assert (await lib.editor.http.delete(f"{lib.base}/folders/{lib.folder_id}")).status_code == 204


@pytest.mark.skip(reason="enable with migration 0004 (M2): needs product/delivery releases to reference a version")
async def test_a_released_document_is_kept_forever() -> None:
    """Trash a document whose version is in a product release (or delivery release), 31 days ago: `purge_trash`
    keeps it (result.kept_released), and the release still serves the frozen version's file."""
    pytest.fail("write with the release tables")


def test_purge_trash_runs_daily_at_half_past_three_utc() -> None:
    registry: dict[tuple[str, str], Any] = job_app.periodic_registry.periodic_tasks  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    periodic = registry[("purge_trash", "purge_trash")]

    assert periodic.cron == "30 3 * * *"
    assert periodic.task.queue == MAINTENANCE_QUEUE
