"""API tests for `create_product_release` (API.md §3.4, BUSINESS_RULES §6 "Product release"): freezing the current
versions of a product's untrashed documents, with their metadata as it is at release time."""

import asyncio
import hashlib
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import (
    AuditEvent,
    Document,
    DocumentVersion,
    MemberRole,
    ProcessingStatus,
    ProductRelease,
    ProductReleaseItem,
)
from tests.api.library import Library, create_document, error_code, make_library
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres", "s3")


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    return await make_library(client_as)


async def _product(lib: Library, *documents: dict[str, Any]) -> dict[str, Any]:
    product = await lib.editor.http.post(f"{lib.base}/products", json={"name": "Laserschneider LX-5"})
    assert product.status_code == 201, product.text
    documents_set = await lib.editor.http.put(
        f"{lib.base}/products/{product.json()['id']}/documents",
        json={"document_ids": [document["id"] for document in documents]},
    )
    assert documents_set.status_code == 200, documents_set.text
    return product.json()


async def _current_version_id(admin_db: AsyncSession, document: dict[str, Any]) -> UUID:
    version_id = await admin_db.scalar(
        select(Document.current_version_id)
        .where(Document.id == UUID(document["id"]))
        .execution_options(populate_existing=True)
    )
    assert version_id is not None
    return version_id


async def _set_status(admin_db: AsyncSession, status: ProcessingStatus, *documents: dict[str, Any]) -> None:
    """The current version of each document gets `status` (the worker is not needed for these tests)."""
    for document in documents:
        version_id = await _current_version_id(admin_db, document)
        await admin_db.execute(
            update(DocumentVersion).where(DocumentVersion.id == version_id).values(processing_status=status)
        )
    await admin_db.commit()


async def _ready(admin_db: AsyncSession, *documents: dict[str, Any]) -> None:
    await _set_status(admin_db, ProcessingStatus.READY, *documents)


async def _release(
    lib: Library, product: dict[str, Any], body: dict[str, Any] | None = None, member: MemberClient | None = None
) -> Any:
    http = (member or lib.editor).http
    return await http.post(f"{lib.base}/products/{product['id']}/releases", json=body or {})


async def _items(admin_db: AsyncSession, release_id: str) -> list[ProductReleaseItem]:
    statement = select(ProductReleaseItem).where(ProductReleaseItem.release_id == UUID(release_id))
    items = await admin_db.scalars(statement.execution_options(populate_existing=True))
    return sorted(items, key=lambda item: item.title)


async def _release_count(admin_db: AsyncSession, product: dict[str, Any]) -> int:
    rows = await admin_db.scalars(select(ProductRelease.id).where(ProductRelease.product_id == UUID(product["id"])))
    return len(list(rows))


async def _events(admin_db: AsyncSession, product: dict[str, Any]) -> list[AuditEvent]:
    statement = select(AuditEvent).where(
        AuditEvent.action == "product_release.created", AuditEvent.detail["product_id"].astext == product["id"]
    )
    return list(await admin_db.scalars(statement))


# ─────────────────────────── creating a release ───────────────────────────


async def test_create_release_freezes_the_current_versions(lib: Library, admin_db: AsyncSession) -> None:
    sub = await lib.editor.http.post(
        f"{lib.base}/folders",
        json={
            "space_id": lib.space_id,
            "parent_id": lib.folder_id,
            "name": "Wartung",
            "default_access_level": "internal",
        },
    )
    assert sub.status_code == 201, sub.text
    manual = await create_document(lib, "Betriebsanleitung")
    plan = await create_document(lib, "Wartungsplan", language="en")
    moved = await lib.editor.http.patch(
        f"{lib.base}/documents/{plan['id']}", json={"folder_id": sub.json()["id"], "access_level": "internal"}
    )
    assert moved.status_code == 200, moved.text
    product = await _product(lib, manual, plan)
    await _ready(admin_db, manual, plan)

    response = await _release(lib, product, {"change_note": "  Erste Freigabe  "})

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["release_no"] == 1
    assert body["change_note"] == "Erste Freigabe"
    assert body["item_count"] == 2
    assert body["created_by_name"] == lib.editor.user.full_name
    assert body["created_at"] is not None
    items = await _items(admin_db, body["id"])
    assert [
        (item.title, item.language, item.doc_type.value, item.access_level.value, item.folder_path) for item in items
    ] == [
        ("Betriebsanleitung", "de", "operating_manual", "customer", "Handbücher/Laser"),
        ("Wartungsplan", "en", "operating_manual", "internal", "Handbücher/Laser/Wartung"),
    ]
    assert [item.version_id for item in items] == [
        await _current_version_id(admin_db, manual),
        await _current_version_id(admin_db, plan),
    ]
    assert [item.document_id for item in items] == [UUID(manual["id"]), UUID(plan["id"])]
    assert [item.group_id for item in items] == [UUID(manual["group_id"]), UUID(plan["group_id"])]
    assert {item.tenant_id for item in items} == {lib.editor.tenant.id}


async def test_the_release_is_readable_and_counted_on_the_product(lib: Library, admin_db: AsyncSession) -> None:
    manual = await create_document(lib)
    product = await _product(lib, manual)
    await _ready(admin_db, manual)

    created = (await _release(lib, product, {"change_note": "Ausgabe 1"})).json()

    listed = (await lib.editor.http.get(f"{lib.base}/products/{product['id']}/releases")).json()
    assert listed["items"] == [created]
    detail = (await lib.editor.http.get(f"{lib.base}/products/{product['id']}/releases/1")).json()
    assert [(item["document_id"], item["version_no"]) for item in detail["items"]] == [(manual["id"], 1)]
    read = (await lib.editor.http.get(f"{lib.base}/products/{product['id']}")).json()
    assert read["latest_release_no"] == 1


async def test_release_numbers_count_up_per_product(lib: Library, admin_db: AsyncSession) -> None:
    manual = await create_document(lib)
    first_product = await _product(lib, manual)
    second_product = await _product(lib, manual)
    await _ready(admin_db, manual)

    numbers = [(await _release(lib, first_product)).json()["release_no"] for _ in range(3)]
    other = (await _release(lib, second_product)).json()["release_no"]

    assert numbers == [1, 2, 3]
    assert other == 1


async def test_two_releases_at_the_same_time_get_different_numbers(lib: Library, admin_db: AsyncSession) -> None:
    manual = await create_document(lib)
    product = await _product(lib, manual)
    await _ready(admin_db, manual)
    other = lib.admin  # a second client, so both requests really run at the same time

    responses = await asyncio.gather(_release(lib, product), _release(lib, product, member=other))

    assert [response.status_code for response in responses] == [201, 201]
    assert sorted(response.json()["release_no"] for response in responses) == [1, 2]


async def test_a_release_keeps_its_version_and_metadata_after_later_changes(
    lib: Library, admin_db: AsyncSession
) -> None:
    manual = await create_document(lib, "Betriebsanleitung")
    product = await _product(lib, manual)
    await _ready(admin_db, manual)
    first = (await _release(lib, product)).json()
    first_version = await _current_version_id(admin_db, manual)

    renamed = await lib.editor.http.patch(f"{lib.base}/documents/{manual['id']}", json={"title": "Bedienungsanleitung"})
    assert renamed.status_code == 200, renamed.text
    second_version_body = await _new_version(lib, manual)
    await _ready(admin_db, manual)
    second = (await _release(lib, product)).json()

    [frozen] = await _items(admin_db, first["id"])
    assert (frozen.title, frozen.version_id) == ("Betriebsanleitung", first_version)
    [current] = await _items(admin_db, second["id"])
    assert (current.title, current.version_id) == ("Bedienungsanleitung", UUID(second_version_body["id"]))
    detail = (await lib.editor.http.get(f"{lib.base}/products/{product['id']}/releases/1")).json()
    assert [item["version_no"] for item in detail["items"]] == [1]


async def _new_version(lib: Library, document: dict[str, Any]) -> dict[str, Any]:
    """A second version of `document`, uploaded the real way."""
    data = f"%PDF-1.7\n% {uuid4()}\n%%EOF\n".encode()
    upload = await lib.editor.http.post(
        f"{lib.base}/uploads",
        json={
            "file_name": "Anleitung-v2.pdf",
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
        f"{lib.base}/documents/{document['id']}/versions", json={"upload_id": upload.json()["upload_id"]}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_trashed_documents_are_left_out(lib: Library, admin_db: AsyncSession) -> None:
    manual = await create_document(lib, "Betriebsanleitung")
    old = await create_document(lib, "Alte Anleitung")  # pending, but trashed: it neither counts nor blocks
    product = await _product(lib, manual, old)
    await _ready(admin_db, manual)
    trashed = await lib.editor.http.post(f"{lib.base}/documents/{old['id']}/trash")
    assert trashed.status_code == 200, trashed.text

    response = await _release(lib, product)

    assert response.status_code == 201, response.text
    assert response.json()["item_count"] == 1
    assert [item.title for item in await _items(admin_db, response.json()["id"])] == ["Betriebsanleitung"]


@pytest.mark.parametrize("body", [{}, {"change_note": None}, {"change_note": "   "}])
async def test_a_missing_or_blank_change_note_is_null(
    lib: Library, admin_db: AsyncSession, body: dict[str, Any]
) -> None:
    manual = await create_document(lib)
    product = await _product(lib, manual)
    await _ready(admin_db, manual)

    response = await _release(lib, product, body)

    assert response.status_code == 201, response.text
    assert response.json()["change_note"] is None


async def test_a_too_long_change_note_is_rejected(lib: Library, admin_db: AsyncSession) -> None:
    manual = await create_document(lib)
    product = await _product(lib, manual)
    await _ready(admin_db, manual)

    response = await _release(lib, product, {"change_note": "x" * 2001})

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"
    assert await _release_count(admin_db, product) == 0


async def test_create_release_is_audited(lib: Library, admin_db: AsyncSession) -> None:
    manual = await create_document(lib)
    plan = await create_document(lib, "Wartungsplan")
    product = await _product(lib, manual, plan)
    await _ready(admin_db, manual, plan)

    response = await _release(lib, product)

    assert response.status_code == 201, response.text
    [event] = await _events(admin_db, product)
    assert event.actor_id == lib.editor.user.id
    assert event.tenant_id == lib.editor.tenant.id
    assert (event.entity, event.entity_id) == ("product_release", UUID(response.json()["id"]))
    assert event.detail == {"product_id": product["id"], "release_no": 1, "item_count": 2}


@pytest.mark.parametrize("role", [MemberRole.OWNER, MemberRole.ADMIN, MemberRole.EDITOR])
async def test_every_member_can_release(lib: Library, admin_db: AsyncSession, role: MemberRole) -> None:
    manual = await create_document(lib)
    product = await _product(lib, manual)
    await _ready(admin_db, manual)
    member = {MemberRole.OWNER: lib.owner, MemberRole.ADMIN: lib.admin, MemberRole.EDITOR: lib.editor}[role]

    response = await _release(lib, product, member=member)

    assert response.status_code == 201, response.text
    assert response.json()["created_by_name"] == member.user.full_name


# ─────────────────────────── blocked ───────────────────────────


@pytest.mark.parametrize("status", [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING, ProcessingStatus.FAILED])
async def test_a_version_that_is_not_ready_blocks_the_release(
    lib: Library, admin_db: AsyncSession, status: ProcessingStatus
) -> None:
    ready = await create_document(lib, "Betriebsanleitung")
    first = await create_document(lib, "Wartungsplan")
    second = await create_document(lib, "Ersatzteilliste")
    product = await _product(lib, ready, first, second)
    await _ready(admin_db, ready)
    await _set_status(admin_db, status, first, second)

    response = await _release(lib, product, {"change_note": "Erste Freigabe"})

    assert response.status_code == 409
    assert error_code(response) == "publish_blocked"
    expected = sorted([first["id"], second["id"]])
    assert response.json()["error"]["details"] == {
        "problems": [{"code": "version_not_ready", "document_id": document_id} for document_id in expected]
    }
    assert await _release_count(admin_db, product) == 0
    assert await _events(admin_db, product) == []


async def test_a_product_without_documents_cannot_be_released(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib)

    response = await _release(lib, product)

    assert response.status_code == 409
    assert error_code(response) == "publish_blocked"
    assert response.json()["error"]["details"] == {"problems": [{"code": "no_items"}]}
    assert await _release_count(admin_db, product) == 0


async def test_a_product_with_only_trashed_documents_cannot_be_released(lib: Library, admin_db: AsyncSession) -> None:
    manual = await create_document(lib)
    product = await _product(lib, manual)
    await _ready(admin_db, manual)
    trashed = await lib.editor.http.post(f"{lib.base}/documents/{manual['id']}/trash")
    assert trashed.status_code == 200, trashed.text

    response = await _release(lib, product)

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"problems": [{"code": "no_items"}]}


# ─────────────────────────── not found ───────────────────────────


async def test_another_tenants_product_is_not_found(
    lib: Library, admin_db: AsyncSession, client_other_tenant: MemberClient
) -> None:
    manual = await create_document(lib)
    product = await _product(lib, manual)
    await _ready(admin_db, manual)

    response = await client_other_tenant.http.post(
        f"/api/v1/app/tenants/{client_other_tenant.tenant.id}/products/{product['id']}/releases", json={}
    )

    assert response.status_code == 404
    assert error_code(response) == "not_found"
    assert await _release_count(admin_db, product) == 0


async def test_an_unknown_product_is_not_found(lib: Library) -> None:
    response = await lib.editor.http.post(f"{lib.base}/products/00000000-0000-4000-8000-000000000000/releases", json={})

    assert response.status_code == 404
    assert error_code(response) == "not_found"
