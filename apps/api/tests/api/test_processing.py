"""Processing of uploaded versions (M1-A6, ARCHITECTURE §9/§11, BUSINESS_RULES §3), against real Postgres and S3.

The API queues `process_version` after a create; the tests then run the worker once, the same way production does
(as `seedoc_admin`, through Procrastinate), and look at the version and its chunks.
"""

import hashlib
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
import procrastinate
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.jobs import processing as processing_jobs
from seedoc.models import DocumentVersion, MemberRole, TextChunk
from seedoc.services import processing as processing_service
from seedoc.storage.s3 import delete_object, put_object
from tests.conftest import ClientAs, MemberClient, RunJobs
from tests.pdfs import make_pdf

pytestmark = pytest.mark.usefixtures("postgres", "s3")

MANUAL_PAGES = [
    "Sicherheitshinweise für Bediener\nVor dem Einschalten die Schutzhaube schließen.",
    "",
    "Wartung\nDie Linse täglich reinigen.",
]


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


async def _upload(lib: Library, data: bytes) -> str:
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


async def _document(lib: Library, data: bytes, **fields: Any) -> dict[str, Any]:
    body = {"upload_id": await _upload(lib, data), "folder_id": lib.folder_id, "title": "Betriebsanleitung", **fields}
    response = await lib.editor.http.post(f"{lib.base}/documents", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _versions(lib: Library, document: dict[str, Any]) -> list[dict[str, Any]]:
    response = await lib.editor.http.get(f"{lib.base}/documents/{document['id']}/versions")
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _chunks(admin_db: AsyncSession, version_id: str) -> list[TextChunk]:
    statement = select(TextChunk).where(TextChunk.version_id == UUID(version_id)).order_by(TextChunk.chunk_index)
    return list(await admin_db.scalars(statement.execution_options(populate_existing=True)))


# ─────────────────────────── queueing ───────────────────────────


@pytest.mark.usefixtures("run_jobs")  # starts from an empty queue
async def test_create_document_queues_process_version(lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))
    version_id = (await _versions(lib, document))[0]["id"]

    jobs = (
        await admin_db.execute(
            text("select task_name, queue_name, status::text, args, queueing_lock from procrastinate_jobs")
        )
    ).all()

    assert [tuple(job) for job in jobs] == [
        ("process_version", "processing", "todo", {"version_id": version_id}, version_id)
    ]
    assert document["processing_status"] == "pending"


async def test_a_queue_failure_does_not_fail_the_upload(lib: Library, monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_queue(*_: object, **__: object) -> procrastinate.App:
        raise OSError("queue down")

    monkeypatch.setattr(processing_jobs, "open_job_app", broken_queue)

    document = await _document(lib, make_pdf(MANUAL_PAGES))

    assert document["processing_status"] == "pending"


# ─────────────────────────── processing ───────────────────────────


async def test_worker_processes_a_pdf_to_ready(run_jobs: RunJobs, lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))

    await run_jobs()

    version = (await _versions(lib, document))[0]
    assert (version["processing_status"], version["page_count"], version["processing_error"]) == ("ready", 3, None)
    assert version["processed_at"] is not None
    detail = (await lib.editor.http.get(f"{lib.base}/documents/{document['id']}")).json()
    assert detail["processing_status"] == "ready"

    chunks = await _chunks(admin_db, version["id"])
    assert [(chunk.page_no, chunk.chunk_index) for chunk in chunks] == [(1, 0), (3, 1)]  # page 2 has no text
    assert chunks[0].content == MANUAL_PAGES[0]
    assert {chunk.tenant_id for chunk in chunks} == {lib.editor.tenant.id}
    assert all(chunk.embedding is None for chunk in chunks)  # embeddings come with M2-A1


async def test_chunks_are_searchable_in_the_documents_language(
    run_jobs: RunJobs, lib: Library, admin_db: AsyncSession
) -> None:
    german = await _document(lib, make_pdf(MANUAL_PAGES))
    english = await _document(lib, make_pdf(["Safety instructions\nClose the protective hood."]), language="en")

    await run_jobs()

    german_version = (await _versions(lib, german))[0]["id"]
    english_version = (await _versions(lib, english))[0]["id"]
    configs = dict(
        (
            await admin_db.execute(
                text("select distinct version_id::text, ts_config::text from text_chunks where version_id in (:a, :b)"),
                {"a": UUID(german_version), "b": UUID(english_version)},
            )
        ).all()
    )
    assert configs == {german_version: "german", english_version: "english"}
    # German stemming: the plural "Linsen" finds the singular "Linse" in the text.
    found = await admin_db.scalar(
        text("select count(*) from text_chunks where version_id = :v and tsv @@ plainto_tsquery('german', 'Linsen')"),
        {"v": UUID(german_version)},
    )
    assert found == 1


async def test_a_new_version_is_processed_too(run_jobs: RunJobs, lib: Library) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))
    response = await lib.editor.http.post(
        f"{lib.base}/documents/{document['id']}/versions",
        json={"upload_id": await _upload(lib, make_pdf(["Neue Ausgabe", "Seite zwei"]))},
    )
    assert response.status_code == 201, response.text
    assert response.json()["processing_status"] == "pending"

    await run_jobs()

    versions = await _versions(lib, document)
    assert [(v["version_no"], v["processing_status"], v["page_count"]) for v in versions] == [
        (2, "ready", 2),
        (1, "ready", 3),
    ]


async def test_an_unreadable_pdf_fails(run_jobs: RunJobs, lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib, b"%PDF-1.7\n% looks like a PDF, is none\n%%EOF\n")

    await run_jobs()

    version = (await _versions(lib, document))[0]
    assert (version["processing_status"], version["processing_error"], version["page_count"]) == (
        "failed",
        processing_service.ERROR_NOT_READABLE,
        None,
    )
    assert await _chunks(admin_db, version["id"]) == []


async def test_a_changed_file_fails(run_jobs: RunJobs, lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))
    version_id = (await _versions(lib, document))[0]["id"]
    key = f"tenants/{lib.editor.tenant.id}/versions/{version_id}.pdf"
    await put_object(key, make_pdf(["Ausgetauscht"]), "application/pdf")

    await run_jobs()

    version = (await _versions(lib, document))[0]
    assert (version["processing_status"], version["processing_error"]) == (
        "failed",
        processing_service.ERROR_FILE_CHANGED,
    )
    assert await _chunks(admin_db, version_id) == []


async def test_a_missing_file_fails(run_jobs: RunJobs, lib: Library) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))
    version_id = (await _versions(lib, document))[0]["id"]
    await delete_object(f"tenants/{lib.editor.tenant.id}/versions/{version_id}.pdf")

    await run_jobs()

    version = (await _versions(lib, document))[0]
    assert (version["processing_status"], version["processing_error"]) == (
        "failed",
        processing_service.ERROR_FILE_MISSING,
    )


# ─────────────────────────── retries ───────────────────────────


async def test_processing_again_replaces_the_chunks(run_jobs: RunJobs, lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))
    await run_jobs()
    version_id = UUID((await _versions(lib, document))[0]["id"])
    first = [chunk.id for chunk in await _chunks(admin_db, str(version_id))]

    # A retry after a crash finds the version not yet `ready` (only the processing columns may change).
    await admin_db.execute(
        update(DocumentVersion).where(DocumentVersion.id == version_id).values(processing_status="processing")
    )
    await admin_db.commit()
    await processing_service.process_version(version_id)

    second = await _chunks(admin_db, str(version_id))
    assert len(second) == len(first) == 2
    assert {chunk.id for chunk in second}.isdisjoint(first)
    assert (await _versions(lib, document))[0]["processing_status"] == "ready"


async def test_a_ready_version_is_left_alone(run_jobs: RunJobs, lib: Library, admin_db: AsyncSession) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))
    await run_jobs()
    version = (await _versions(lib, document))[0]
    chunk_ids = [chunk.id for chunk in await _chunks(admin_db, version["id"])]

    await processing_service.process_version(UUID(version["id"]))

    assert [chunk.id for chunk in await _chunks(admin_db, version["id"])] == chunk_ids
    assert (await _versions(lib, document))[0]["processed_at"] == version["processed_at"]


async def test_an_unknown_version_is_skipped() -> None:
    await processing_service.process_version(uuid4())  # e.g. purged before the job ran; no error


@pytest.mark.parametrize(("attempts", "status"), [(0, "processing"), (3, "failed")], ids=["first_try", "last_try"])
async def test_an_unexpected_error_fails_the_version_only_after_the_last_retry(
    lib: Library, monkeypatch: pytest.MonkeyPatch, attempts: int, status: str
) -> None:
    document = await _document(lib, make_pdf(MANUAL_PAGES))
    version_id = (await _versions(lib, document))[0]["id"]

    async def storage_down(_: str) -> bytes | None:
        raise ConnectionError("storage down")

    monkeypatch.setattr(processing_service, "read_object", storage_down)
    context = cast(procrastinate.JobContext, SimpleNamespace(job=SimpleNamespace(attempts=attempts)))

    with pytest.raises(ConnectionError):  # raised on, so Procrastinate decides about the retry
        await processing_jobs.process_version.func(context, version_id=version_id)

    version = (await _versions(lib, document))[0]
    assert version["processing_status"] == status
    assert version["processing_error"] == (processing_service.ERROR_INTERNAL if status == "failed" else None)
