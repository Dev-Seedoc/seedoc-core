"""API tests for documents and versions (M1-A4, API.md §3.3, BUSINESS_RULES §3), against real Postgres and S3.

Each file goes the real way: `create_upload` → PUT to the presigned URL → `create_document` / `create_document_version`.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings
from seedoc.models import AuditEvent, Document, MemberRole, Upload
from seedoc.storage.s3 import get_s3_client
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres", "s3")


def _pdf(text: str = "") -> bytes:
    """A unique small PDF-like file (only the `%PDF-` magic is checked here; parsing is the worker's job)."""
    return f"%PDF-1.7\n% {text or uuid4()}\n%%EOF\n".encode()


@dataclass(frozen=True)
class Library:
    """An editor and an owner of one tenant, a space "Handbücher" and a folder "Laser" with defaults."""

    editor: MemberClient
    owner: MemberClient
    space_id: str
    folder_id: str

    @property
    def base(self) -> str:
        return f"/api/v1/app/tenants/{self.editor.tenant.id}"


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


async def _make_library(client_as: ClientAs) -> Library:
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
    return Library(editor=editor, owner=owner, space_id=space["id"], folder_id=folder["id"])


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    return await _make_library(client_as)


async def _upload(lib: Library, data: bytes, *, put: bytes | None = None, file_name: str = "Anleitung.pdf") -> str:
    """`create_upload` for `data`, then PUT `put` (default: the same bytes) like the browser; returns the upload id."""
    response = await lib.editor.http.post(
        f"{lib.base}/uploads",
        json={
            "file_name": file_name,
            "size_bytes": len(data),
            "sha256_hex": hashlib.sha256(data).hexdigest(),
            "content_type": "application/pdf",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    async with httpx.AsyncClient() as browser:
        stored = await browser.put(
            body["upload_url"], content=data if put is None else put, headers={"Content-Type": "application/pdf"}
        )
    assert stored.status_code == 200
    return body["upload_id"]


async def _create(lib: Library, data: bytes | None = None, **fields: Any) -> Response:
    upload_id = fields.pop("upload_id", None) or await _upload(lib, data or _pdf())
    body = {"upload_id": upload_id, "folder_id": lib.folder_id, "title": "Betriebsanleitung", **fields}
    return await lib.editor.http.post(f"{lib.base}/documents", json=body)


async def _document(lib: Library, data: bytes | None = None, **fields: Any) -> dict[str, Any]:
    response = await _create(lib, data, **fields)
    assert response.status_code == 201, response.text
    return response.json()


def _object_exists(key: str) -> bool:
    found = get_s3_client().list_objects_v2(Bucket=get_settings().s3_bucket, Prefix=key)
    return any(item.get("Key") == key for item in found.get("Contents", []))


# ─────────────────────────── create ───────────────────────────


async def test_create_document_uses_folder_defaults(lib: Library, admin_db: AsyncSession) -> None:
    data = _pdf()
    upload_id = await _upload(lib, data)

    response = await _create(lib, upload_id=upload_id)

    assert response.status_code == 201, response.text
    doc = response.json()
    assert (doc["title"], doc["doc_type"], doc["language"], doc["access_level"]) == (
        "Betriebsanleitung",
        "operating_manual",
        "de",
        "customer",
    )
    assert doc["folder_path"] == "Handbücher/Laser"
    assert (doc["current_version_no"], doc["processing_status"], doc["versions_count"]) == (1, "pending", 1)
    assert (doc["language_variants"], doc["released_in_count"], doc["duplicate_of_document_id"]) == ([], 0, None)
    assert doc["trashed_at"] is None

    # The file moved from the upload key to the version key; the upload is used up.
    upload = await admin_db.scalar(select(Upload).where(Upload.id == UUID(upload_id)))
    assert upload is not None
    assert upload.consumed_at is not None
    assert not _object_exists(upload.storage_key)
    versions = (await lib.editor.http.get(f"{lib.base}/documents/{doc['id']}/versions")).json()["items"]
    version_key = f"tenants/{lib.editor.tenant.id}/versions/{versions[0]['id']}.pdf"
    stored = get_s3_client().get_object(Bucket=get_settings().s3_bucket, Key=version_key)["Body"].read()
    assert stored == data
    assert versions[0]["sha256_hex"] == hashlib.sha256(data).hexdigest()

    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == UUID(doc["id"]), AuditEvent.action == "document.created")
    )
    assert event is not None
    assert (event.tenant_id, event.actor_id) == (lib.editor.tenant.id, lib.editor.user.id)


async def test_given_values_override_folder_defaults(lib: Library) -> None:
    doc = await _document(lib, doc_type="datasheet", language="en", access_level="internal", title="  Data sheet  ")

    assert (doc["title"], doc["doc_type"], doc["language"], doc["access_level"]) == (
        "Data sheet",
        "datasheet",
        "en",
        "internal",
    )


async def test_create_document_needs_type_and_language_without_folder_default(lib: Library) -> None:
    bare = (
        await lib.editor.http.post(
            f"{lib.base}/folders",
            json={"space_id": lib.space_id, "name": "Ohne Vorgaben", "default_access_level": "public"},
        )
    ).json()

    response = await _create(lib, folder_id=bare["id"])
    given = await _create(lib, folder_id=bare["id"], doc_type="other", language="en")

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"
    assert given.status_code == 201
    assert given.json()["access_level"] == "public"


async def test_upload_that_was_never_sent_is_incomplete(lib: Library) -> None:
    data = _pdf()
    response = await lib.editor.http.post(
        f"{lib.base}/uploads",
        json={
            "file_name": "a.pdf",
            "size_bytes": len(data),
            "sha256_hex": hashlib.sha256(data).hexdigest(),
            "content_type": "application/pdf",
        },
    )

    created = await _create(lib, upload_id=response.json()["upload_id"])

    assert created.status_code == 409
    assert _error_code(created) == "upload_incomplete"


@pytest.mark.parametrize(
    "stored",
    [b"%PDF-1.7 a longer file than announced", b"%PDF-1.7 THE FILE"],
    ids=["other_size", "same_size_other_hash"],
)
async def test_stored_file_must_match_the_upload(lib: Library, stored: bytes) -> None:
    """The presigned URL does not fix the content, so the API compares what was really stored."""
    upload_id = await _upload(lib, b"%PDF-1.7 the file", put=stored)

    response = await _create(lib, upload_id=upload_id)

    assert response.status_code == 409
    assert _error_code(response) == "upload_incomplete"


async def test_file_that_is_not_a_pdf_is_refused(lib: Library) -> None:
    upload_id = await _upload(lib, b"<html>not a pdf</html>")

    response = await _create(lib, upload_id=upload_id)

    assert response.status_code == 415
    assert _error_code(response) == "unsupported_file_type"


async def test_upload_can_be_used_only_once(lib: Library) -> None:
    upload_id = await _upload(lib, _pdf())
    await _document(lib, upload_id=upload_id)

    again = await _create(lib, upload_id=upload_id)

    assert again.status_code == 409
    assert _error_code(again) == "conflict"


async def test_expired_upload_is_refused(lib: Library, admin_db: AsyncSession) -> None:
    upload_id = await _upload(lib, _pdf())
    await admin_db.execute(
        update(Upload).where(Upload.id == UUID(upload_id)).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await admin_db.commit()

    response = await _create(lib, upload_id=upload_id)

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


async def test_same_file_twice_is_allowed_with_duplicate_hint(lib: Library) -> None:
    data = _pdf()
    first = await _document(lib, data)

    second = await _document(lib, data, title="Kopie")

    assert second["duplicate_of_document_id"] == first["id"]
    assert first["duplicate_of_document_id"] is None


async def test_machine_specific_documents_are_not_available_yet(lib: Library) -> None:
    response = await _create(lib, machine_id=str(uuid4()))

    assert response.status_code == 422


async def test_other_tenants_upload_and_folder_are_not_found(lib: Library, client_as: ClientAs) -> None:
    other = await _make_library(client_as)
    other_upload = await _upload(other, _pdf())

    with_their_upload = await _create(lib, upload_id=other_upload)
    into_their_folder = await _create(lib, folder_id=other.folder_id)

    assert (with_their_upload.status_code, into_their_folder.status_code) == (404, 404)


# ─────────────────────────── list ───────────────────────────


async def test_list_documents_filters_and_pages(lib: Library) -> None:
    other_folder = (
        await lib.editor.http.post(
            f"{lib.base}/folders",
            json={"space_id": lib.space_id, "name": "Wartung", "default_access_level": "public"},
        )
    ).json()
    await _document(lib, title="C Laser")
    await _document(lib, title="A Laser", language="en")
    await _document(
        lib, title="B Wartungsplan", folder_id=other_folder["id"], doc_type="maintenance_manual", language="de"
    )

    url = f"{lib.base}/documents"
    all_titles = [d["title"] for d in (await lib.editor.http.get(url)).json()["items"]]
    in_folder = [
        d["title"] for d in (await lib.editor.http.get(url, params={"folder_id": lib.folder_id})).json()["items"]
    ]
    english = [d["title"] for d in (await lib.editor.http.get(url, params={"language": "en"})).json()["items"]]
    searched = [d["title"] for d in (await lib.editor.http.get(url, params={"q": "wartung"})).json()["items"]]
    in_space = (await lib.editor.http.get(url, params={"space_id": lib.space_id})).json()["items"]

    assert all_titles == ["A Laser", "B Wartungsplan", "C Laser"]
    assert in_folder == ["A Laser", "C Laser"]
    assert english == ["A Laser"]
    assert searched == ["B Wartungsplan"]
    assert len(in_space) == 3
    assert {d["folder_path"] for d in in_space} == {"Handbücher/Laser", "Handbücher/Wartung"}

    page_1 = (await lib.editor.http.get(url, params={"limit": 2})).json()
    page_2 = (await lib.editor.http.get(url, params={"limit": 2, "cursor": page_1["next_cursor"]})).json()
    assert [d["title"] for d in page_1["items"]] == ["A Laser", "B Wartungsplan"]
    assert [d["title"] for d in page_2["items"]] == ["C Laser"]
    assert page_2["next_cursor"] is None


async def test_list_documents_rejects_a_broken_cursor(lib: Library) -> None:
    response = await lib.editor.http.get(f"{lib.base}/documents", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422


async def test_list_documents_shows_only_own_tenant(lib: Library, client_as: ClientAs) -> None:
    other = await _make_library(client_as)
    await _document(other, title="Fremd")
    await _document(lib, title="Eigen")

    titles = [d["title"] for d in (await lib.editor.http.get(f"{lib.base}/documents")).json()["items"]]

    assert titles == ["Eigen"]


# ─────────────────────────── get + update ───────────────────────────


async def test_get_document_lists_language_variants(lib: Library, admin_db: AsyncSession) -> None:
    german = await _document(lib, title="Betriebsanleitung")
    english = await _document(lib, title="Operating manual", language="en")
    await admin_db.execute(
        update(Document).where(Document.id == UUID(english["id"])).values(group_id=UUID(german["group_id"]))
    )
    await admin_db.commit()

    response = await lib.editor.http.get(f"{lib.base}/documents/{german['id']}")

    assert response.status_code == 200
    assert response.json()["language_variants"] == [
        {"document_id": english["id"], "language": "en", "title": "Operating manual"}
    ]


async def test_update_document_changes_given_fields_and_audits_them(lib: Library, admin_db: AsyncSession) -> None:
    doc = await _document(lib)
    other_folder = (
        await lib.editor.http.post(
            f"{lib.base}/folders",
            json={"space_id": lib.space_id, "name": "Archiv", "default_access_level": "public"},
        )
    ).json()

    response = await lib.editor.http.patch(
        f"{lib.base}/documents/{doc['id']}",
        json={"title": "Betriebsanleitung 2026", "folder_id": other_folder["id"], "access_level": "customer"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert (updated["title"], updated["folder_path"]) == ("Betriebsanleitung 2026", "Handbücher/Archiv")
    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == UUID(doc["id"]), AuditEvent.action == "document.updated")
    )
    assert event is not None
    assert event.detail["fields"] == ["folder_id", "title"]  # access_level was already "customer"


async def test_update_language_to_one_taken_in_the_group_conflicts(lib: Library, admin_db: AsyncSession) -> None:
    german = await _document(lib)
    english = await _document(lib, language="en")
    await admin_db.execute(
        update(Document).where(Document.id == UUID(english["id"])).values(group_id=UUID(german["group_id"]))
    )
    await admin_db.commit()

    response = await lib.editor.http.patch(f"{lib.base}/documents/{english['id']}", json={"language": "de"})

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


@pytest.mark.parametrize(
    "change",
    [{"title": None}, {"title": " "}, {"language": "xx"}, {"doc_type": None}, {"machine_id": str(uuid4())}],
    ids=["null_title", "blank_title", "language", "null_doc_type", "machine"],
)
async def test_update_document_rejects_invalid_input(lib: Library, change: dict[str, Any]) -> None:
    doc = await _document(lib)

    response = await lib.editor.http.patch(f"{lib.base}/documents/{doc['id']}", json=change)

    assert response.status_code == 422


async def test_update_into_other_tenants_folder_is_not_found(lib: Library, client_as: ClientAs) -> None:
    other = await _make_library(client_as)
    doc = await _document(lib)

    response = await lib.editor.http.patch(f"{lib.base}/documents/{doc['id']}", json={"folder_id": other.folder_id})

    assert response.status_code == 404


# ─────────────────────────── trash + restore ───────────────────────────


async def test_trash_hides_and_restore_brings_back(lib: Library, admin_db: AsyncSession) -> None:
    doc = await _document(lib)
    url = f"{lib.base}/documents"

    trashed = await lib.editor.http.post(f"{url}/{doc['id']}/trash")
    trashed_again = await lib.editor.http.post(f"{url}/{doc['id']}/trash")
    listed = (await lib.editor.http.get(url)).json()["items"]
    with_trash = (await lib.editor.http.get(url, params={"include_trashed": True})).json()["items"]
    blocked = await lib.editor.http.patch(f"{url}/{doc['id']}", json={"title": "X"})
    restored = await lib.editor.http.post(f"{url}/{doc['id']}/restore")

    assert trashed.status_code == 200
    assert trashed.json()["trashed_at"] is not None
    assert trashed_again.json()["trashed_at"] == trashed.json()["trashed_at"]  # idempotent
    assert listed == []
    assert [d["id"] for d in with_trash] == [doc["id"]]
    assert blocked.status_code == 409
    assert restored.json()["trashed_at"] is None
    actions = (await admin_db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == UUID(doc["id"])))).all()
    assert sorted(actions) == ["document.created", "document.restored", "document.trashed"]


# ─────────────────────────── versions ───────────────────────────


async def test_new_version_becomes_current(lib: Library, admin_db: AsyncSession) -> None:
    doc = await _document(lib)
    upload_id = await _upload(lib, _pdf(), file_name="Anleitung_v2.pdf")

    response = await lib.editor.http.post(f"{lib.base}/documents/{doc['id']}/versions", json={"upload_id": upload_id})

    assert response.status_code == 201, response.text
    version = response.json()
    assert (version["version_no"], version["is_current"], version["file_name"]) == (2, True, "Anleitung_v2.pdf")
    assert version["processing_status"] == "pending"
    current = (await lib.editor.http.get(f"{lib.base}/documents/{doc['id']}")).json()
    assert (current["current_version_no"], current["versions_count"]) == (2, 2)
    listed = (await lib.editor.http.get(f"{lib.base}/documents/{doc['id']}/versions")).json()["items"]
    assert [(v["version_no"], v["is_current"]) for v in listed] == [(2, True), (1, False)]
    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == UUID(doc["id"]), AuditEvent.action == "document.version_added")
    )
    assert event is not None
    assert event.detail == {"version_no": 2}


async def test_new_version_of_trashed_document_conflicts(lib: Library) -> None:
    doc = await _document(lib)
    await lib.editor.http.post(f"{lib.base}/documents/{doc['id']}/trash")
    upload_id = await _upload(lib, _pdf())

    response = await lib.editor.http.post(f"{lib.base}/documents/{doc['id']}/versions", json={"upload_id": upload_id})

    assert response.status_code == 409


async def test_new_version_with_another_documents_file_has_duplicate_hint(lib: Library) -> None:
    data = _pdf()
    first = await _document(lib, data)
    second = await _document(lib)
    upload_id = await _upload(lib, data)

    response = await lib.editor.http.post(
        f"{lib.base}/documents/{second['id']}/versions", json={"upload_id": upload_id}
    )

    assert response.json()["duplicate_of_document_id"] == first["id"]


async def test_version_file_url_downloads_with_naming_file_name(lib: Library) -> None:
    data = _pdf()
    doc = await _document(lib, data, title="Betriebsanleitung TruLaser")
    version = (await lib.editor.http.get(f"{lib.base}/documents/{doc['id']}/versions")).json()["items"][0]

    response = await lib.editor.http.get(f"{lib.base}/documents/{doc['id']}/versions/{version['id']}/file")

    assert response.status_code == 200
    body = response.json()
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(seconds=110) < expires_at - datetime.now(UTC) <= timedelta(seconds=120)
    async with httpx.AsyncClient() as browser:
        download = await browser.get(body["url"])
    assert download.content == data
    assert 'filename="Betriebsanleitung_TruLaser_de_v1.pdf"' in download.headers["content-disposition"]


async def test_version_of_another_document_is_not_found(lib: Library) -> None:
    first = await _document(lib)
    second = await _document(lib)
    version = (await lib.editor.http.get(f"{lib.base}/documents/{first['id']}/versions")).json()["items"][0]

    response = await lib.editor.http.get(f"{lib.base}/documents/{second['id']}/versions/{version['id']}/file")

    assert response.status_code == 404


# ─────────────────────────── access ───────────────────────────


async def test_documents_require_session(lib: Library) -> None:
    lib.editor.http.cookies.clear()

    response = await lib.editor.http.get(f"{lib.base}/documents")

    assert response.status_code == 401


async def test_other_tenants_documents_are_not_found(lib: Library, client_as: ClientAs) -> None:
    doc = await _document(lib)
    version = (await lib.editor.http.get(f"{lib.base}/documents/{doc['id']}/versions")).json()["items"][0]
    intruder = await _make_library(client_as)
    own = f"{intruder.base}/documents/{doc['id']}"

    responses = [
        await intruder.editor.http.get(own),
        await intruder.editor.http.patch(own, json={"title": "X"}),
        await intruder.editor.http.post(f"{own}/trash"),
        await intruder.editor.http.post(f"{own}/restore"),
        await intruder.editor.http.get(f"{own}/versions"),
        await intruder.editor.http.post(f"{own}/versions", json={"upload_id": await _upload(intruder, _pdf())}),
        await intruder.editor.http.get(f"{own}/versions/{version['id']}/file"),
        await intruder.editor.http.get(f"{lib.base}/documents/{doc['id']}"),  # tenant A's URL as a non-member
    ]

    assert [response.status_code for response in responses] == [404] * 8
    assert (await lib.editor.http.get(f"{lib.base}/documents/{doc['id']}")).json()["title"] == "Betriebsanleitung"
