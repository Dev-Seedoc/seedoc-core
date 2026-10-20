"""API tests for products (M2-B2, API.md §3.4, BUSINESS_RULES §1/§6): CRUD, the document set, the language matrix
and reading product releases. `create_product_release` is not part of this task (its releases are seeded here)."""

import secrets
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import (
    AccessLevel,
    AuditEvent,
    Customer,
    Delivery,
    DeliveryKind,
    DocType,
    Document,
    DocumentVersion,
    Machine,
    MemberRole,
    ProductRelease,
    ProductReleaseItem,
)
from tests.api.library import Library, create_document, error_code, make_library
from tests.conftest import ClientAs

pytestmark = pytest.mark.usefixtures("postgres", "s3")


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    return await make_library(client_as)


async def _product(lib: Library, **fields: Any) -> dict[str, Any]:
    response = await lib.editor.http.post(f"{lib.base}/products", json={"name": "Laser 3030", **fields})
    assert response.status_code == 201, response.text
    return response.json()


async def _set_documents(lib: Library, product: dict[str, Any], *documents: dict[str, Any]) -> Any:
    return await lib.editor.http.put(
        f"{lib.base}/products/{product['id']}/documents", json={"document_ids": [d["id"] for d in documents]}
    )


async def _events(admin_db: AsyncSession, entity_id: str, action: str) -> list[AuditEvent]:
    return list(
        await admin_db.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == UUID(entity_id), AuditEvent.action == action)
        )
    )


# ─────────────────────────── create / read / update ───────────────────────────


async def test_create_product_with_defaults(lib: Library, admin_db: AsyncSession) -> None:
    response = await lib.editor.http.post(f"{lib.base}/products", json={"name": "  Laser 3030 "})

    assert response.status_code == 201, response.text
    product = response.json()
    assert (product["name"], product["space_id"], product["required_languages"]) == ("Laser 3030", None, ["de"])
    assert (product["document_count"], product["latest_release_no"], product["archived_at"]) == (0, None, None)
    [event] = await _events(admin_db, product["id"], "product.created")
    assert (event.tenant_id, event.actor_id, event.entity) == (lib.editor.tenant.id, lib.editor.user.id, "product")


async def test_create_product_keeps_space_and_language_order(lib: Library) -> None:
    product = await _product(lib, space_id=lib.space_id, required_languages=["en", "de", "fr"])

    assert product["space_id"] == lib.space_id
    assert product["required_languages"] == ["en", "de", "fr"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": " "},
        {"name": "x" * 201},
        {"name": "Laser", "required_languages": []},
        {"name": "Laser", "required_languages": ["de", "de"]},
        {"name": "Laser", "required_languages": ["xx"]},
        {"name": "Laser", "required_languages": None},
        {"name": "Laser", "space_id": "not-a-uuid"},
    ],
    ids=["blank", "too_long", "no_language", "duplicate", "unsupported", "null_languages", "bad_space"],
)
async def test_create_product_rejects_invalid_input(lib: Library, body: dict[str, Any]) -> None:
    response = await lib.editor.http.post(f"{lib.base}/products", json=body)

    assert response.status_code == 422


async def test_create_product_in_other_tenants_space_is_not_found(lib: Library, client_as: ClientAs) -> None:
    other = await make_library(client_as)

    response = await lib.editor.http.post(f"{lib.base}/products", json={"name": "Laser", "space_id": other.space_id})

    assert response.status_code == 404
    assert error_code(response) == "not_found"


async def test_list_products_sorted_german_and_only_own(lib: Library, client_as: ClientAs) -> None:
    for name in ("Zuführung", "Ölpumpe", "Abkantpresse", "Österreich-Linie"):
        await _product(lib, name=name)
    other = await make_library(client_as)
    await _product(other, name="Fremdprodukt")

    response = await lib.editor.http.get(f"{lib.base}/products")

    assert response.status_code == 200
    body = response.json()
    assert [p["name"] for p in body["items"]] == ["Abkantpresse", "Ölpumpe", "Österreich-Linie", "Zuführung"]
    assert body["next_cursor"] is None


async def test_get_product(lib: Library) -> None:
    product = await _product(lib)

    response = await lib.editor.http.get(f"{lib.base}/products/{product['id']}")

    assert response.status_code == 200
    assert response.json() == product


async def test_get_unknown_product_is_not_found(lib: Library) -> None:
    response = await lib.editor.http.get(f"{lib.base}/products/{uuid4()}")

    assert response.status_code == 404


async def test_update_product_changes_only_sent_fields(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib, space_id=lib.space_id)

    response = await lib.editor.http.patch(
        f"{lib.base}/products/{product['id']}",
        json={"name": "Laser 4040", "required_languages": ["de", "en"], "space_id": None},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["required_languages"], body["space_id"]) == ("Laser 4040", ["de", "en"], None)
    [event] = await _events(admin_db, product["id"], "product.updated")
    assert event.detail == {"fields": ["name", "required_languages", "space_id"]}


async def test_update_without_change_writes_no_audit(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib)

    response = await lib.editor.http.patch(f"{lib.base}/products/{product['id']}", json={"name": "Laser 3030"})

    assert response.status_code == 200
    assert await _events(admin_db, product["id"], "product.updated") == []


@pytest.mark.parametrize(
    "change",
    [{"name": None}, {"required_languages": None}, {"required_languages": []}, {"required_languages": ["xx"]}],
    ids=["null_name", "null_languages", "no_language", "unsupported"],
)
async def test_update_product_rejects_invalid_input(lib: Library, change: dict[str, Any]) -> None:
    product = await _product(lib)

    response = await lib.editor.http.patch(f"{lib.base}/products/{product['id']}", json=change)

    assert response.status_code == 422


async def test_update_into_other_tenants_space_is_not_found(lib: Library, client_as: ClientAs) -> None:
    product = await _product(lib)
    other = await make_library(client_as)

    response = await lib.editor.http.patch(f"{lib.base}/products/{product['id']}", json={"space_id": other.space_id})

    assert response.status_code == 404


# ─────────────────────────── document set ───────────────────────────


async def test_set_product_documents_replaces_the_set(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib)
    wartung, anleitung, schaltplan = (
        await create_document(lib, "Wartung"),
        await create_document(lib, "Anleitung"),
        await create_document(lib, "Schaltplan"),
    )
    first = await _set_documents(lib, product, wartung, anleitung, wartung)  # duplicates are ignored
    assert first.status_code == 200, first.text
    assert [d["title"] for d in first.json()["items"]] == ["Anleitung", "Wartung"]

    second = await _set_documents(lib, product, schaltplan, anleitung)

    assert second.status_code == 200, second.text
    assert [d["title"] for d in second.json()["items"]] == ["Anleitung", "Schaltplan"]
    listed = (await lib.editor.http.get(f"{lib.base}/products/{product['id']}/documents")).json()
    assert listed == second.json()
    assert listed["items"][0]["folder_path"] == "Handbücher/Laser"
    assert (await lib.editor.http.get(f"{lib.base}/products/{product['id']}")).json()["document_count"] == 2
    details = [event.detail for event in await _events(admin_db, product["id"], "product.documents_set")]
    assert sorted(details, key=lambda d: d["added"]) == [{"added": 1, "removed": 1}, {"added": 2, "removed": 0}]


async def test_setting_the_same_documents_again_writes_no_audit(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib)
    document = await create_document(lib)
    await _set_documents(lib, product, document)

    again = await _set_documents(lib, product, document)

    assert again.status_code == 200
    assert len(await _events(admin_db, product["id"], "product.documents_set")) == 1


async def test_an_empty_list_clears_the_set(lib: Library) -> None:
    product = await _product(lib)
    await _set_documents(lib, product, await create_document(lib))

    response = await _set_documents(lib, product)

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_trashed_documents_leave_the_list_but_cannot_be_added(lib: Library) -> None:
    product = await _product(lib)
    kept, trashed = await create_document(lib, "Anleitung"), await create_document(lib, "Wartung")
    await _set_documents(lib, product, kept, trashed)
    await lib.editor.http.post(f"{lib.base}/documents/{trashed['id']}/trash")

    listed = (await lib.editor.http.get(f"{lib.base}/products/{product['id']}/documents")).json()
    assert [d["title"] for d in listed["items"]] == ["Anleitung"]
    assert (await lib.editor.http.get(f"{lib.base}/products/{product['id']}")).json()["document_count"] == 1

    response = await _set_documents(lib, product, kept, trashed)

    assert response.status_code == 409
    assert error_code(response) == "conflict"


async def test_other_tenants_or_unknown_document_is_not_found_and_changes_nothing(
    lib: Library, client_as: ClientAs
) -> None:
    product = await _product(lib)
    own = await create_document(lib)
    await _set_documents(lib, product, own)
    other = await make_library(client_as)
    foreign = await create_document(other)

    responses = [
        await _set_documents(lib, product, own, foreign),
        await lib.editor.http.put(
            f"{lib.base}/products/{product['id']}/documents", json={"document_ids": [own["id"], str(uuid4())]}
        ),
    ]

    assert [response.status_code for response in responses] == [404, 404]
    listed = (await lib.editor.http.get(f"{lib.base}/products/{product['id']}/documents")).json()
    assert [d["id"] for d in listed["items"]] == [own["id"]]


async def test_a_machine_specific_document_cannot_join_a_product(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib)
    document = await create_document(lib, "Prüfprotokoll")
    customer = Customer(tenant_id=lib.editor.tenant.id, name="Muster AG")
    admin_db.add(customer)
    await admin_db.flush()
    delivery = Delivery(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        kind=DeliveryKind.MACHINE,
        name="Auftrag 1",
        public_token=secrets.token_urlsafe(32),
    )
    admin_db.add(delivery)
    await admin_db.flush()
    machine = Machine(
        tenant_id=customer.tenant_id,
        delivery_id=delivery.id,
        product_id=UUID(product["id"]),
        name="Laser",
        serial_no=f"SN-{secrets.token_hex(4)}",
        public_token=secrets.token_urlsafe(32),
    )
    admin_db.add(machine)
    await admin_db.flush()
    await admin_db.execute(update(Document).where(Document.id == UUID(document["id"])).values(machine_id=machine.id))
    await admin_db.commit()

    response = await _set_documents(lib, product, document)

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


async def test_set_product_documents_rejects_too_many_ids(lib: Library) -> None:
    product = await _product(lib)

    response = await lib.editor.http.put(
        f"{lib.base}/products/{product['id']}/documents", json={"document_ids": [str(uuid4()) for _ in range(501)]}
    )

    assert response.status_code == 422


# ─────────────────────────── language matrix ───────────────────────────


async def _group(admin_db: AsyncSession, first: dict[str, Any], *others: dict[str, Any]) -> None:
    """Put `others` into the language group of `first` (the language variant API is a separate task, M1-A5)."""
    ids = [UUID(other["id"]) for other in others]
    await admin_db.execute(update(Document).where(Document.id.in_(ids)).values(group_id=UUID(first["group_id"])))
    await admin_db.commit()


async def test_language_matrix_shows_present_and_missing_languages(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib, required_languages=["de", "en", "fr"])
    anleitung_de = await create_document(lib, "Betriebsanleitung", "de")
    anleitung_en = await create_document(lib, "Operating manual", "en")
    not_in_set_fr = await create_document(lib, "Mode d'emploi", "fr")  # a variant outside the set does not count
    await _group(admin_db, anleitung_de, anleitung_en, not_in_set_fr)
    wartung_de = await create_document(lib, "Wartung", "de")
    english_only = await create_document(lib, "Datasheet", "en")
    await _set_documents(lib, product, anleitung_de, anleitung_en, wartung_de, english_only)

    response = await lib.editor.http.get(f"{lib.base}/products/{product['id']}/languages")

    assert response.status_code == 200, response.text
    matrix = response.json()
    assert matrix["languages"] == ["de", "en", "fr"]
    rows = {row["title"]: row for row in matrix["rows"]}
    assert [row["title"] for row in matrix["rows"]] == ["Betriebsanleitung", "Datasheet", "Wartung"]
    assert rows["Betriebsanleitung"]["group_id"] == anleitung_de["group_id"]
    assert rows["Betriebsanleitung"]["doc_type"] == "operating_manual"
    assert rows["Betriebsanleitung"]["cells"] == {
        "de": {"status": "present", "document_id": anleitung_de["id"], "waiver_reason": None},
        "en": {"status": "present", "document_id": anleitung_en["id"], "waiver_reason": None},
        "fr": {"status": "missing", "document_id": None, "waiver_reason": None},
    }
    assert {lang: cell["status"] for lang, cell in rows["Datasheet"]["cells"].items()} == {
        "de": "missing",
        "en": "present",
        "fr": "missing",
    }
    assert {lang: cell["status"] for lang, cell in rows["Wartung"]["cells"].items()} == {
        "de": "present",
        "en": "missing",
        "fr": "missing",
    }


async def test_language_matrix_of_an_empty_product(lib: Library) -> None:
    product = await _product(lib, required_languages=["de", "en"])

    response = await lib.editor.http.get(f"{lib.base}/products/{product['id']}/languages")

    assert response.json() == {"languages": ["de", "en"], "rows": []}


# ─────────────────────────── releases (read) ───────────────────────────


async def _seed_release(
    admin_db: AsyncSession, lib: Library, product: dict[str, Any], release_no: int, documents: list[dict[str, Any]]
) -> ProductRelease:
    release = ProductRelease(
        tenant_id=lib.editor.tenant.id,
        product_id=UUID(product["id"]),
        release_no=release_no,
        change_note=f"Ausgabe {release_no}",
        created_by=lib.editor.user.id,
    )
    admin_db.add(release)
    await admin_db.flush()
    for document in documents:
        version = await admin_db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == UUID(document["id"]))
        )
        assert version is not None
        admin_db.add(
            ProductReleaseItem(
                tenant_id=release.tenant_id,
                release_id=release.id,
                document_id=version.document_id,
                version_id=version.id,
                group_id=UUID(document["group_id"]),
                title=document["title"],
                doc_type=DocType(document["doc_type"]),
                language=document["language"],
                access_level=AccessLevel(document["access_level"]),
                folder_path=document["folder_path"],
            )
        )
    await admin_db.commit()
    return release


async def test_list_and_get_product_releases(lib: Library, admin_db: AsyncSession) -> None:
    product = await _product(lib)
    wartung, anleitung = await create_document(lib, "Wartung"), await create_document(lib, "Anleitung")
    await _seed_release(admin_db, lib, product, 1, [wartung])
    await _seed_release(admin_db, lib, product, 2, [wartung, anleitung])

    listed = await lib.editor.http.get(f"{lib.base}/products/{product['id']}/releases")

    assert listed.status_code == 200, listed.text
    releases = listed.json()["items"]
    assert [(r["release_no"], r["item_count"], r["change_note"]) for r in releases] == [
        (2, 2, "Ausgabe 2"),
        (1, 1, "Ausgabe 1"),
    ]
    assert releases[0]["created_by_name"] == lib.editor.user.full_name
    assert (await lib.editor.http.get(f"{lib.base}/products/{product['id']}")).json()["latest_release_no"] == 2

    detail = await lib.editor.http.get(f"{lib.base}/products/{product['id']}/releases/2")

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert (body["release_no"], body["item_count"]) == (2, 2)
    assert [(i["title"], i["language"], i["version_no"], i["folder_path"]) for i in body["items"]] == [
        ("Anleitung", "de", 1, "Handbücher/Laser"),
        ("Wartung", "de", 1, "Handbücher/Laser"),
    ]
    assert body["items"][0]["document_id"] == anleitung["id"]


async def test_unknown_release_no_is_not_found(lib: Library) -> None:
    product = await _product(lib)

    response = await lib.editor.http.get(f"{lib.base}/products/{product['id']}/releases/1")

    assert response.status_code == 404


# ─────────────────────────── access ───────────────────────────


async def test_products_require_session(lib: Library) -> None:
    lib.editor.http.cookies.clear()

    response = await lib.editor.http.get(f"{lib.base}/products")

    assert response.status_code == 401


@pytest.mark.parametrize("role", [MemberRole.EDITOR, MemberRole.ADMIN, MemberRole.OWNER])
async def test_every_member_role_manages_products(lib: Library, role: MemberRole) -> None:
    member = {MemberRole.EDITOR: lib.editor, MemberRole.ADMIN: lib.admin, MemberRole.OWNER: lib.owner}[role]

    response = await member.http.post(f"{lib.base}/products", json={"name": "Laser"})

    assert response.status_code == 201


async def test_other_tenants_products_are_not_found(lib: Library, client_as: ClientAs) -> None:
    product = await _product(lib)
    intruder = await make_library(client_as)
    own = f"{intruder.base}/products/{product['id']}"

    responses = [
        await intruder.editor.http.get(own),
        await intruder.editor.http.patch(own, json={"name": "X"}),
        await intruder.editor.http.get(f"{own}/documents"),
        await intruder.editor.http.put(f"{own}/documents", json={"document_ids": []}),
        await intruder.editor.http.get(f"{own}/languages"),
        await intruder.editor.http.get(f"{own}/releases"),
        await intruder.editor.http.get(f"{own}/releases/1"),
        await intruder.editor.http.get(f"{lib.base}/products/{product['id']}"),  # tenant A's URL as a non-member
    ]

    assert [response.status_code for response in responses] == [404] * 8
    assert (await lib.editor.http.get(f"{lib.base}/products/{product['id']}")).json()["name"] == "Laser 3030"
