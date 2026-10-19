"""API tests for language variants (M1-A5, API.md §3.3, BUSINESS_RULES §3), against real Postgres and S3.

Documents are created the real way (upload → `create_document`); grouping only goes through the two endpoints
under test, so these tests describe `link_language_variant` / `unlink_language_variant` from the outside.
"""

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import AuditEvent, Document, MemberRole
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres", "s3")


@dataclass(frozen=True)
class Library:
    """An editor of one tenant with a space "Handbücher" and a folder "Laser" (no default language)."""

    editor: MemberClient
    folder_id: str

    @property
    def base(self) -> str:
        return f"/api/v1/app/tenants/{self.editor.tenant.id}"

    def variants_url(self, document: dict[str, Any], variant: dict[str, Any] | None = None) -> str:
        url = f"{self.base}/documents/{document['id']}/language-variants"
        return url if variant is None else f"{url}/{variant['id']}"


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
            },
        )
    ).json()
    return Library(editor=editor, folder_id=folder["id"])


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    return await _make_library(client_as)


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


async def _document(lib: Library, language: str, title: str | None = None) -> dict[str, Any]:
    """A new document in `language` (its own language group), created through upload → `create_document`."""
    data = f"%PDF-1.7\n% {uuid4()}\n%%EOF\n".encode()
    upload = await lib.editor.http.post(
        f"{lib.base}/uploads",
        json={
            "file_name": "Anleitung.pdf",
            "size_bytes": len(data),
            "sha256_hex": hashlib.sha256(data).hexdigest(),
            "content_type": "application/pdf",
        },
    )
    assert upload.status_code == 201, upload.text
    async with httpx.AsyncClient() as browser:
        stored = await browser.put(
            upload.json()["upload_url"], content=data, headers={"Content-Type": "application/pdf"}
        )
    assert stored.status_code == 200
    response = await lib.editor.http.post(
        f"{lib.base}/documents",
        json={
            "upload_id": upload.json()["upload_id"],
            "folder_id": lib.folder_id,
            "title": title or f"Betriebsanleitung {language}",
            "language": language,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _get(lib: Library, document: dict[str, Any]) -> dict[str, Any]:
    response = await lib.editor.http.get(f"{lib.base}/documents/{document['id']}")
    assert response.status_code == 200, response.text
    return response.json()


async def _link(lib: Library, document: dict[str, Any], variant: dict[str, Any]) -> Response:
    return await lib.editor.http.post(lib.variants_url(document), json={"document_id": variant["id"]})


async def _linked(lib: Library, document: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    response = await _link(lib, document, variant)
    assert response.status_code == 200, response.text
    return response.json()


async def _trash(lib: Library, document: dict[str, Any]) -> None:
    response = await lib.editor.http.post(f"{lib.base}/documents/{document['id']}/trash")
    assert response.status_code == 200, response.text


def _languages(document: dict[str, Any]) -> list[str]:
    return [variant["language"] for variant in document["language_variants"]]


async def _audit_events(admin_db: AsyncSession, document: dict[str, Any], action: str) -> list[AuditEvent]:
    return list(
        await admin_db.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == UUID(document["id"]), AuditEvent.action == action)
        )
    )


# ─────────────────────────── link ───────────────────────────


async def test_link_puts_both_documents_in_the_first_documents_group(lib: Library) -> None:
    german = await _document(lib, "de", "Betriebsanleitung")
    english = await _document(lib, "en", "Operating manual")
    assert german["group_id"] != english["group_id"]

    response = await _link(lib, german, english)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == german["id"]  # the response is the document in the path, as DocumentRead
    assert body["group_id"] == german["group_id"]  # the first document keeps its group
    assert body["language_variants"] == [{"document_id": english["id"], "language": "en", "title": "Operating manual"}]
    english_now = await _get(lib, english)
    assert english_now["group_id"] == german["group_id"]
    assert english_now["language_variants"] == [
        {"document_id": german["id"], "language": "de", "title": "Betriebsanleitung"}
    ]


async def test_link_merges_the_whole_second_group_into_the_first(lib: Library) -> None:
    german, french = await _document(lib, "de"), await _document(lib, "fr")
    english, spanish = await _document(lib, "en"), await _document(lib, "es")
    await _linked(lib, german, french)
    await _linked(lib, english, spanish)

    body = await _linked(lib, german, english)

    assert _languages(body) == ["en", "es", "fr"]  # sorted by language
    for document in (french, english, spanish):
        assert (await _get(lib, document))["group_id"] == german["group_id"]


async def test_link_from_the_variant_side_uses_the_variants_group(lib: Library) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")

    body = await _linked(lib, english, german)

    assert body["group_id"] == english["group_id"]
    assert (await _get(lib, german))["group_id"] == english["group_id"]


async def test_link_same_language_conflicts(lib: Library) -> None:
    first, second = await _document(lib, "de"), await _document(lib, "de")

    response = await _link(lib, first, second)

    assert response.status_code == 409
    assert _error_code(response) == "conflict"
    assert (await _get(lib, second))["group_id"] == second["group_id"]


async def test_link_conflict_in_any_member_changes_nothing(lib: Library) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    french, other_english = await _document(lib, "fr"), await _document(lib, "en")
    await _linked(lib, german, english)
    await _linked(lib, french, other_english)

    response = await _link(lib, german, french)  # french itself is free, but its group also has "en"

    assert response.status_code == 409
    assert _error_code(response) == "conflict"
    assert (await _get(lib, french))["group_id"] == french["group_id"]
    assert (await _get(lib, other_english))["group_id"] == french["group_id"]
    assert _languages(await _get(lib, german)) == ["en"]


async def test_trashed_member_still_holds_its_language(lib: Library) -> None:
    # A trashed document keeps its group; restoring it must not break "one document per language".
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _linked(lib, german, english)
    await _trash(lib, english)
    new_english = await _document(lib, "en")

    response = await _link(lib, german, new_english)

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


async def test_link_moves_trashed_members_of_the_second_group_too(lib: Library, admin_db: AsyncSession) -> None:
    german, english, french = await _document(lib, "de"), await _document(lib, "en"), await _document(lib, "fr")
    await _linked(lib, english, french)
    await _trash(lib, french)

    await _linked(lib, german, english)

    group_id = await admin_db.scalar(select(Document.group_id).where(Document.id == UUID(french["id"])))
    assert group_id == UUID(german["group_id"])


@pytest.mark.parametrize("trashed", ["document", "variant"])
async def test_link_with_a_trashed_document_conflicts(lib: Library, trashed: str) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _trash(lib, german if trashed == "document" else english)

    response = await _link(lib, german, english)

    assert response.status_code == 409
    assert _error_code(response) == "conflict"
    assert (await _get(lib, english))["group_id"] == english["group_id"]


async def test_link_document_to_itself_is_rejected(lib: Library) -> None:
    german = await _document(lib, "de")

    response = await _link(lib, german, german)

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


@pytest.mark.parametrize(
    "body", [{}, {"document_id": None}, {"document_id": "not-a-uuid"}], ids=["missing", "null", "bad"]
)
async def test_link_rejects_invalid_body(lib: Library, body: dict[str, Any]) -> None:
    german = await _document(lib, "de")

    response = await lib.editor.http.post(lib.variants_url(german), json=body)

    assert response.status_code == 422


async def test_link_unknown_variant_is_not_found(lib: Library) -> None:
    german = await _document(lib, "de")

    response = await lib.editor.http.post(lib.variants_url(german), json={"document_id": str(uuid4())})

    assert response.status_code == 404
    assert _error_code(response) == "not_found"


async def test_link_writes_one_audit_event(lib: Library, admin_db: AsyncSession) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")

    await _linked(lib, german, english)

    events = await _audit_events(admin_db, german, "document.language_linked")
    assert len(events) == 1
    assert (events[0].entity, events[0].detail) == ("document", {"variant_document_id": english["id"]})
    assert (events[0].tenant_id, events[0].actor_id) == (lib.editor.tenant.id, lib.editor.user.id)
    assert await _audit_events(admin_db, english, "document.language_linked") == []


async def test_linking_again_is_a_no_op(lib: Library, admin_db: AsyncSession) -> None:
    german, english, french = await _document(lib, "de"), await _document(lib, "en"), await _document(lib, "fr")
    await _linked(lib, german, english)
    await _linked(lib, german, french)

    again = await _link(lib, english, french)  # already in one group, from either side

    assert again.status_code == 200, again.text
    assert again.json()["group_id"] == german["group_id"]
    assert _languages(again.json()) == ["de", "fr"]
    assert await _audit_events(admin_db, english, "document.language_linked") == []


# ─────────────────────────── unlink ───────────────────────────


async def test_unlink_gives_the_variant_a_new_group(lib: Library) -> None:
    german, english, french = await _document(lib, "de"), await _document(lib, "en"), await _document(lib, "fr")
    await _linked(lib, german, english)
    await _linked(lib, german, french)

    response = await lib.editor.http.delete(lib.variants_url(german, english))

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id"], body["group_id"]) == (german["id"], german["group_id"])
    assert _languages(body) == ["fr"]
    english_now = await _get(lib, english)
    assert english_now["group_id"] not in {german["group_id"], english["group_id"]}  # a fresh group, not its old one
    assert english_now["language_variants"] == []
    assert (await _get(lib, french))["group_id"] == german["group_id"]


async def test_unlink_from_the_other_side_works_the_same(lib: Library) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _linked(lib, german, english)

    response = await lib.editor.http.delete(lib.variants_url(english, german))

    assert response.status_code == 200, response.text
    assert response.json()["group_id"] == german["group_id"]  # the path document stays, the variant leaves
    assert response.json()["language_variants"] == []
    assert (await _get(lib, german))["group_id"] != german["group_id"]


async def test_unlink_writes_an_audit_event(lib: Library, admin_db: AsyncSession) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _linked(lib, german, english)

    await lib.editor.http.delete(lib.variants_url(german, english))

    events = await _audit_events(admin_db, german, "document.language_unlinked")
    assert len(events) == 1
    assert (events[0].entity, events[0].detail) == ("document", {"variant_document_id": english["id"]})
    assert (events[0].tenant_id, events[0].actor_id) == (lib.editor.tenant.id, lib.editor.user.id)


async def test_unlinked_variant_can_take_a_language_of_its_old_group(lib: Library) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _linked(lib, german, english)
    await lib.editor.http.delete(lib.variants_url(german, english))

    response = await lib.editor.http.patch(f"{lib.base}/documents/{english['id']}", json={"language": "de"})

    assert response.status_code == 200, response.text


async def test_unlink_a_document_outside_the_group_is_not_found(lib: Library) -> None:
    german, english, stranger = await _document(lib, "de"), await _document(lib, "en"), await _document(lib, "fr")
    await _linked(lib, german, english)

    responses = [
        await lib.editor.http.delete(lib.variants_url(german, stranger)),
        await lib.editor.http.delete(lib.variants_url(german, german)),  # a document is not its own variant
        await lib.editor.http.delete(f"{lib.variants_url(german)}/{uuid4()}"),
    ]

    assert [response.status_code for response in responses] == [404] * 3
    assert _languages(await _get(lib, german)) == ["en"]


async def test_unlink_from_a_trashed_document_conflicts(lib: Library) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _linked(lib, german, english)
    await _trash(lib, german)

    response = await lib.editor.http.delete(lib.variants_url(german, english))

    assert response.status_code == 409
    assert _error_code(response) == "conflict"
    assert (await _get(lib, english))["group_id"] == german["group_id"]


async def test_unlink_a_trashed_variant_works(lib: Library, admin_db: AsyncSession) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _linked(lib, german, english)
    await _trash(lib, english)

    response = await lib.editor.http.delete(lib.variants_url(german, english))

    assert response.status_code == 200, response.text
    group_id = await admin_db.scalar(select(Document.group_id).where(Document.id == UUID(english["id"])))
    assert group_id != UUID(german["group_id"])


# ─────────────────────────── access ───────────────────────────


async def test_language_variants_require_session(lib: Library) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    lib.editor.http.cookies.clear()

    responses = [
        await _link(lib, german, english),
        await lib.editor.http.delete(lib.variants_url(german, english)),
    ]

    assert [response.status_code for response in responses] == [401, 401]


async def test_other_tenants_documents_are_not_found(lib: Library, client_as: ClientAs) -> None:
    german, english = await _document(lib, "de"), await _document(lib, "en")
    await _linked(lib, german, english)
    intruder = await _make_library(client_as)
    own_french = await _document(intruder, "fr")

    responses = [
        # tenant A's documents through the intruder's tenant URL
        await intruder.editor.http.post(intruder.variants_url(german), json={"document_id": own_french["id"]}),
        await intruder.editor.http.delete(intruder.variants_url(german, english)),
        # the intruder's own document linked to (or unlinked from) one of tenant A
        await intruder.editor.http.post(intruder.variants_url(own_french), json={"document_id": german["id"]}),
        await intruder.editor.http.delete(intruder.variants_url(own_french, german)),
        # tenant A's URL as a non-member
        await intruder.editor.http.post(lib.variants_url(german), json={"document_id": english["id"]}),
        await intruder.editor.http.delete(lib.variants_url(german, english)),
    ]

    assert [response.status_code for response in responses] == [404] * 6
    assert _languages(await _get(lib, german)) == ["en"]
    assert (await _get(intruder, own_french))["group_id"] == own_french["group_id"]
