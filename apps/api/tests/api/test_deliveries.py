"""API tests for customers, deliveries and machines (M2-B3, API.md §3.5, BUSINESS_RULES §1/§11)."""

import re
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import AuditEvent, Delivery, DeliveryStatus, Document, MemberRole
from tests.api.library import Library, create_document, error_code, make_library
from tests.conftest import ClientAs

pytestmark = pytest.mark.usefixtures("postgres", "s3")

TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")  # 32 random bytes, base64url without padding


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    return await make_library(client_as)


async def _customer(lib: Library, **fields: Any) -> dict[str, Any]:
    response = await lib.editor.http.post(f"{lib.base}/customers", json={"name": "Muster AG", **fields})
    assert response.status_code == 201, response.text
    return response.json()


async def _product(lib: Library, name: str = "Laser 3030", languages: list[str] | None = None) -> dict[str, Any]:
    response = await lib.editor.http.post(
        f"{lib.base}/products", json={"name": name, "required_languages": languages or ["de"]}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _delivery(lib: Library, customer: dict[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
    customer = customer or await _customer(lib)
    body = {"customer_id": customer["id"], "kind": "system", "name": "Anlage Nord", **fields}
    response = await lib.editor.http.post(f"{lib.base}/deliveries", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _add_machine(lib: Library, delivery: dict[str, Any], product: dict[str, Any], serial_no: str = "") -> Any:
    return await lib.editor.http.post(
        f"{lib.base}/deliveries/{delivery['id']}/machines",
        json={"product_id": product["id"], "name": "Laser 3030", "serial_no": serial_no or f"SN-{uuid4().hex[:8]}"},
    )


async def _machine(lib: Library, delivery: dict[str, Any] | None = None, **product: Any) -> dict[str, Any]:
    delivery = delivery or await _delivery(lib)
    response = await _add_machine(lib, delivery, await _product(lib, **product))
    assert response.status_code == 201, response.text
    return response.json()


async def _get(lib: Library, path: str) -> dict[str, Any]:
    response = await lib.editor.http.get(f"{lib.base}/{path}")
    assert response.status_code == 200, response.text
    return response.json()


async def _events(admin_db: AsyncSession, entity_id: str, action: str) -> list[AuditEvent]:
    return list(
        await admin_db.scalars(
            select(AuditEvent).where(AuditEvent.entity_id == UUID(entity_id), AuditEvent.action == action)
        )
    )


async def _publish(admin_db: AsyncSession, delivery: dict[str, Any]) -> None:
    """As if published (publishing itself is M2-B5)."""
    await admin_db.execute(
        update(Delivery).where(Delivery.id == UUID(delivery["id"])).values(status=DeliveryStatus.PUBLISHED)
    )
    await admin_db.commit()


# ─────────────────────────── customers ───────────────────────────


async def test_create_customer(lib: Library, admin_db: AsyncSession) -> None:
    response = await lib.editor.http.post(
        f"{lib.base}/customers",
        json={"name": " Muster AG ", "contact_name": "Erika Muster", "contact_email": "Erika.Muster@Example.com"},
    )

    assert response.status_code == 201, response.text
    customer = response.json()
    assert (customer["name"], customer["contact_name"], customer["contact_email"]) == (
        "Muster AG",
        "Erika Muster",
        "erika.muster@example.com",
    )
    assert customer["delivery_count"] == 0
    assert len(await _events(admin_db, customer["id"], "customer.created")) == 1


@pytest.mark.parametrize(
    "body",
    [{"name": " "}, {"name": "Muster AG", "contact_email": "not-an-email"}, {"name": None}],
    ids=["blank_name", "bad_email", "null_name"],
)
async def test_create_customer_rejects_invalid_input(lib: Library, body: dict[str, Any]) -> None:
    response = await lib.editor.http.post(f"{lib.base}/customers", json=body)

    assert response.status_code == 422


async def test_list_customers_sorted_with_delivery_count(lib: Library) -> None:
    zeta, alpha = await _customer(lib, name="Zeta GmbH"), await _customer(lib, name="Älpler KG")
    await _delivery(lib, zeta)
    await _delivery(lib, zeta, name="Anlage Süd")

    body = await _get(lib, "customers")

    assert [(c["name"], c["delivery_count"]) for c in body["items"]] == [("Älpler KG", 0), ("Zeta GmbH", 2)]
    assert body["items"][0]["id"] == alpha["id"]
    assert body["next_cursor"] is None


async def test_update_customer(lib: Library, admin_db: AsyncSession) -> None:
    customer = await _customer(lib, contact_name="Erika", contact_email="erika@example.com")

    response = await lib.editor.http.patch(
        f"{lib.base}/customers/{customer['id']}", json={"name": "Muster GmbH", "contact_email": None}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["contact_name"], body["contact_email"]) == ("Muster GmbH", "Erika", None)
    [event] = await _events(admin_db, customer["id"], "customer.updated")
    assert event.detail == {"fields": ["contact_email", "name"]}
    assert (await _get(lib, f"customers/{customer['id']}"))["name"] == "Muster GmbH"


async def test_update_customer_null_name_is_rejected(lib: Library) -> None:
    customer = await _customer(lib)

    response = await lib.editor.http.patch(f"{lib.base}/customers/{customer['id']}", json={"name": None})

    assert response.status_code == 422


# ─────────────────────────── deliveries ───────────────────────────


async def test_create_system_delivery(lib: Library, admin_db: AsyncSession) -> None:
    customer = await _customer(lib)

    response = await lib.editor.http.post(
        f"{lib.base}/deliveries",
        json={"customer_id": customer["id"], "kind": "system", "name": "Anlage Nord", "order_no": "A-4711"},
    )

    assert response.status_code == 201, response.text
    delivery = response.json()
    assert (delivery["customer_id"], delivery["customer_name"], delivery["kind"]) == (
        customer["id"],
        "Muster AG",
        "system",
    )
    assert (delivery["name"], delivery["order_no"], delivery["status"]) == ("Anlage Nord", "A-4711", "draft")
    assert delivery["required_languages"] == []  # filled from the products of its machines
    assert TOKEN.match(delivery["public_token"])
    assert delivery["portal_url"] == f"https://localhost/s/{delivery['public_token']}"
    assert (delivery["current_release_no"], delivery["has_open_draft"], delivery["machines"]) == (None, False, [])
    assert len(await _events(admin_db, delivery["id"], "delivery.created")) == 1


async def test_create_delivery_with_given_languages(lib: Library) -> None:
    delivery = await _delivery(lib, required_languages=["de", "pl"])

    assert delivery["required_languages"] == ["de", "pl"]


@pytest.mark.parametrize(
    "change",
    [{"kind": "fleet"}, {"name": " "}, {"required_languages": ["xx"]}, {"required_languages": ["de", "de"]}],
    ids=["kind", "blank_name", "unsupported_language", "duplicate_language"],
)
async def test_create_delivery_rejects_invalid_input(lib: Library, change: dict[str, Any]) -> None:
    customer = await _customer(lib)
    body = {"customer_id": customer["id"], "kind": "system", "name": "Anlage", **change}

    response = await lib.editor.http.post(f"{lib.base}/deliveries", json=body)

    assert response.status_code == 422


async def test_create_delivery_for_other_tenants_customer_is_not_found(lib: Library, client_as: ClientAs) -> None:
    other = await make_library(client_as)
    foreign = await _customer(other)

    response = await lib.editor.http.post(
        f"{lib.base}/deliveries", json={"customer_id": foreign["id"], "kind": "system", "name": "Anlage"}
    )

    assert response.status_code == 404


async def test_machines_add_their_products_languages_while_draft(lib: Library) -> None:
    delivery = await _delivery(lib)
    await _add_machine(lib, delivery, await _product(lib, "Laser", ["de", "en"]))
    await _add_machine(lib, delivery, await _product(lib, "Presse", ["en", "fr"]))

    assert (await _get(lib, f"deliveries/{delivery['id']}"))["required_languages"] == ["de", "en", "fr"]


async def test_machines_extend_given_languages_too(lib: Library) -> None:
    delivery = await _delivery(lib, required_languages=["pl"])
    await _add_machine(lib, delivery, await _product(lib, "Laser", ["de", "pl"]))

    assert (await _get(lib, f"deliveries/{delivery['id']}"))["required_languages"] == ["pl", "de"]


async def test_after_the_first_publish_languages_are_fixed(lib: Library, admin_db: AsyncSession) -> None:
    delivery = await _delivery(lib, required_languages=["de"])
    await _publish(admin_db, delivery)

    added = await _add_machine(lib, delivery, await _product(lib, "Laser", ["de", "en"]))
    assert added.status_code == 201, added.text
    assert (await _get(lib, f"deliveries/{delivery['id']}"))["required_languages"] == ["de"]

    response = await lib.editor.http.patch(
        f"{lib.base}/deliveries/{delivery['id']}", json={"required_languages": ["de", "en"]}
    )
    assert response.status_code == 409
    assert error_code(response) == "conflict"
    renamed = await lib.editor.http.patch(f"{lib.base}/deliveries/{delivery['id']}", json={"name": "Anlage Ost"})
    assert renamed.status_code == 200


async def test_update_delivery(lib: Library, admin_db: AsyncSession) -> None:
    delivery = await _delivery(lib, order_no="A-1")

    response = await lib.editor.http.patch(
        f"{lib.base}/deliveries/{delivery['id']}",
        json={"name": "Anlage Ost", "order_no": None, "required_languages": ["de", "en"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["order_no"], body["required_languages"]) == ("Anlage Ost", None, ["de", "en"])
    assert body["public_token"] == delivery["public_token"]  # never changes
    [event] = await _events(admin_db, delivery["id"], "delivery.updated")
    assert event.detail == {"fields": ["name", "order_no", "required_languages"]}


@pytest.mark.parametrize("change", [{"name": None}, {"required_languages": None}], ids=["null_name", "null_languages"])
async def test_update_delivery_rejects_invalid_input(lib: Library, change: dict[str, Any]) -> None:
    delivery = await _delivery(lib)

    response = await lib.editor.http.patch(f"{lib.base}/deliveries/{delivery['id']}", json=change)

    assert response.status_code == 422


async def test_customer_and_kind_of_a_delivery_never_change(lib: Library) -> None:
    delivery = await _delivery(lib)
    other = await _customer(lib, name="Andere AG")

    response = await lib.editor.http.patch(
        f"{lib.base}/deliveries/{delivery['id']}", json={"customer_id": other["id"], "kind": "machine"}
    )

    assert response.status_code == 200  # not part of DeliveryUpdate: ignored
    assert (response.json()["customer_id"], response.json()["kind"]) == (delivery["customer_id"], "system")


async def test_list_deliveries_filters_and_counts(lib: Library, admin_db: AsyncSession) -> None:
    muster, other = await _customer(lib), await _customer(lib, name="Andere AG")
    nord = await _delivery(lib, muster, name="Nord")
    sued = await _delivery(lib, muster, name="Süd")
    await _delivery(lib, other, name="Ost")
    await _add_machine(lib, nord, await _product(lib))
    await _publish(admin_db, sued)

    everything = await _get(lib, "deliveries")
    for_muster = await _get(lib, f"deliveries?customer_id={muster['id']}")
    published = await _get(lib, "deliveries?status=published")

    assert [d["name"] for d in everything["items"]] == ["Nord", "Ost", "Süd"]
    assert [(d["name"], d["machine_count"], d["customer_name"]) for d in for_muster["items"]] == [
        ("Nord", 1, "Muster AG"),
        ("Süd", 0, "Muster AG"),
    ]
    assert [d["id"] for d in published["items"]] == [sued["id"]]


async def test_list_deliveries_rejects_unknown_status(lib: Library) -> None:
    response = await lib.editor.http.get(f"{lib.base}/deliveries?status=lost")

    assert response.status_code == 422


# ─────────────────────────── machines ───────────────────────────


async def test_create_machine(lib: Library, admin_db: AsyncSession) -> None:
    delivery = await _delivery(lib)
    product = await _product(lib)

    response = await _add_machine(lib, delivery, product, serial_no="SN-0001")

    assert response.status_code == 201, response.text
    machine = response.json()
    assert (machine["delivery_id"], machine["product_id"], machine["product_name"]) == (
        delivery["id"],
        product["id"],
        "Laser 3030",
    )
    assert (machine["name"], machine["serial_no"], machine["first_published_at"], machine["archived_at"]) == (
        "Laser 3030",
        "SN-0001",
        None,
        None,
    )
    assert TOKEN.match(machine["public_token"])
    assert machine["public_token"] != delivery["public_token"]
    assert machine["portal_url"] == f"https://localhost/m/{machine['public_token']}"
    assert len(await _events(admin_db, machine["id"], "machine.created")) == 1
    listed = (await _get(lib, f"deliveries/{delivery['id']}"))["machines"]
    assert [m["id"] for m in listed] == [machine["id"]]
    assert "delivery_id" not in listed[0]


async def test_a_machine_delivery_takes_exactly_one_machine(lib: Library) -> None:
    delivery = await _delivery(lib, kind="machine")
    product = await _product(lib)
    first = await _add_machine(lib, delivery, product)
    assert first.status_code == 201
    await lib.admin.http.post(f"{lib.base}/machines/{first.json()['id']}/archive")  # archived ones still count

    second = await _add_machine(lib, delivery, product)

    assert second.status_code == 409
    assert error_code(second) == "conflict"


async def test_a_system_delivery_takes_several_machines_in_order(lib: Library) -> None:
    delivery = await _delivery(lib)
    product = await _product(lib)
    first = (await _add_machine(lib, delivery, product)).json()
    second = (await _add_machine(lib, delivery, product)).json()
    await lib.editor.http.patch(f"{lib.base}/machines/{first['id']}", json={"sort_order": 5})

    machines = (await _get(lib, f"deliveries/{delivery['id']}"))["machines"]

    assert [m["id"] for m in machines] == [second["id"], first["id"]]


async def test_serial_numbers_are_unique_per_tenant(lib: Library, client_as: ClientAs) -> None:
    delivery = await _delivery(lib)
    product = await _product(lib)
    assert (await _add_machine(lib, delivery, product, "SN-42")).status_code == 201

    duplicate = await _add_machine(lib, delivery, product, "SN-42")
    other = await make_library(client_as)
    elsewhere = await _add_machine(other, await _delivery(other), await _product(other), "SN-42")

    assert duplicate.status_code == 409
    assert error_code(duplicate) == "conflict"
    assert elsewhere.status_code == 201


@pytest.mark.parametrize(
    "body",
    [{"name": "Laser", "serial_no": " "}, {"name": " ", "serial_no": "SN-1"}, {"name": "Laser"}],
    ids=["blank_serial", "blank_name", "no_serial"],
)
async def test_create_machine_rejects_invalid_input(lib: Library, body: dict[str, Any]) -> None:
    delivery, product = await _delivery(lib), await _product(lib)

    response = await lib.editor.http.post(
        f"{lib.base}/deliveries/{delivery['id']}/machines", json={"product_id": product["id"], **body}
    )

    assert response.status_code == 422


async def test_create_machine_with_other_tenants_product_is_not_found(lib: Library, client_as: ClientAs) -> None:
    other = await make_library(client_as)

    response = await _add_machine(lib, await _delivery(lib), await _product(other))

    assert response.status_code == 404


async def test_update_machine(lib: Library, admin_db: AsyncSession) -> None:
    machine = await _machine(lib)

    response = await lib.editor.http.patch(
        f"{lib.base}/machines/{machine['id']}", json={"name": "Laser links", "serial_no": "SN-9", "sort_order": 2}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["serial_no"], body["public_token"]) == ("Laser links", "SN-9", machine["public_token"])
    [event] = await _events(admin_db, machine["id"], "machine.updated")
    assert event.detail == {"fields": ["name", "serial_no", "sort_order"]}
    assert (await _get(lib, f"machines/{machine['id']}"))["name"] == "Laser links"


@pytest.mark.parametrize(
    "change",
    [{"name": None}, {"serial_no": None}, {"sort_order": None}, {"serial_no": " "}],
    ids=["null_name", "null_serial", "null_sort_order", "blank_serial"],
)
async def test_update_machine_rejects_invalid_input(lib: Library, change: dict[str, Any]) -> None:
    machine = await _machine(lib)

    response = await lib.editor.http.patch(f"{lib.base}/machines/{machine['id']}", json=change)

    assert response.status_code == 422


async def test_the_product_of_a_machine_never_changes(lib: Library) -> None:
    machine = await _machine(lib)
    other = await _product(lib, "Presse")

    response = await lib.editor.http.patch(f"{lib.base}/machines/{machine['id']}", json={"product_id": other["id"]})

    assert response.status_code == 200  # not part of MachineUpdate: ignored
    assert response.json()["product_id"] == machine["product_id"]


async def test_update_machine_to_a_used_serial_conflicts(lib: Library) -> None:
    delivery = await _delivery(lib)
    product = await _product(lib)
    await _add_machine(lib, delivery, product, "SN-1")
    second = (await _add_machine(lib, delivery, product, "SN-2")).json()

    response = await lib.editor.http.patch(f"{lib.base}/machines/{second['id']}", json={"serial_no": "SN-1"})

    assert response.status_code == 409


async def test_archive_machine_is_for_admins_and_happens_once(lib: Library, admin_db: AsyncSession) -> None:
    machine = await _machine(lib)

    as_editor = await lib.editor.http.post(f"{lib.base}/machines/{machine['id']}/archive")
    first = await lib.admin.http.post(f"{lib.base}/machines/{machine['id']}/archive")
    again = await lib.owner.http.post(f"{lib.base}/machines/{machine['id']}/archive")

    assert as_editor.status_code == 403
    assert first.status_code == 200, first.text
    assert first.json()["archived_at"] is not None
    assert again.status_code == 200
    assert again.json()["archived_at"] == first.json()["archived_at"]
    assert len(await _events(admin_db, machine["id"], "machine.archived")) == 1
    changed = await lib.editor.http.patch(f"{lib.base}/machines/{machine['id']}", json={"name": "Neu"})
    assert changed.status_code == 409  # an archived machine is read-only


# ─────────────────────────── machine documents ───────────────────────────


async def test_attach_list_and_detach_machine_documents(lib: Library, admin_db: AsyncSession) -> None:
    machine = await _machine(lib)
    report = await create_document(lib, "Prüfprotokoll")
    url = f"{lib.base}/machines/{machine['id']}/documents"

    attached = await lib.editor.http.post(url, json={"document_id": report["id"]})
    again = await lib.editor.http.post(url, json={"document_id": report["id"]})

    assert attached.status_code == 200, attached.text
    assert (attached.json()["id"], attached.json()["machine_id"]) == (report["id"], machine["id"])
    assert again.status_code == 200
    assert [d["id"] for d in (await _get(lib, f"machines/{machine['id']}/documents"))["items"]] == [report["id"]]
    events = await _events(admin_db, machine["id"], "machine.document_attached")
    assert [event.detail for event in events] == [{"document_id": report["id"]}]

    detached = await lib.editor.http.delete(f"{url}/{report['id']}")

    assert detached.status_code == 204
    assert (await _get(lib, f"machines/{machine['id']}/documents"))["items"] == []
    machine_id = await admin_db.scalar(select(Document.machine_id).where(Document.id == UUID(report["id"])))
    assert machine_id is None
    events = await _events(admin_db, machine["id"], "machine.document_detached")
    assert [event.detail for event in events] == [{"document_id": report["id"]}]


async def test_list_machine_documents_hides_trashed_ones(lib: Library) -> None:
    machine = await _machine(lib)
    report = await create_document(lib, "Prüfprotokoll")
    await lib.editor.http.post(f"{lib.base}/machines/{machine['id']}/documents", json={"document_id": report["id"]})
    await lib.editor.http.post(f"{lib.base}/documents/{report['id']}/trash")

    assert (await _get(lib, f"machines/{machine['id']}/documents"))["items"] == []


async def test_attach_refuses_documents_that_belong_elsewhere(lib: Library) -> None:
    delivery = await _delivery(lib)
    product = await _product(lib)
    first = (await _add_machine(lib, delivery, product)).json()
    second = (await _add_machine(lib, delivery, product)).json()
    report, manual, trashed = (
        await create_document(lib, "Prüfprotokoll"),
        await create_document(lib, "Betriebsanleitung"),
        await create_document(lib, "Alt"),
    )
    await lib.editor.http.post(f"{lib.base}/machines/{first['id']}/documents", json={"document_id": report["id"]})
    await lib.editor.http.put(f"{lib.base}/products/{product['id']}/documents", json={"document_ids": [manual["id"]]})
    await lib.editor.http.post(f"{lib.base}/documents/{trashed['id']}/trash")
    url = f"{lib.base}/machines/{second['id']}/documents"

    responses = [
        await lib.editor.http.post(url, json={"document_id": report["id"]}),  # another machine's
        await lib.editor.http.post(url, json={"document_id": manual["id"]}),  # in a product's set
        await lib.editor.http.post(url, json={"document_id": trashed["id"]}),
    ]

    assert [response.status_code for response in responses] == [409, 409, 409]
    assert {error_code(response) for response in responses} == {"conflict"}


async def test_detach_a_document_not_attached_here_is_not_found(lib: Library) -> None:
    machine = await _machine(lib)
    loose = await create_document(lib)

    responses = [
        await lib.editor.http.delete(f"{lib.base}/machines/{machine['id']}/documents/{loose['id']}"),
        await lib.editor.http.delete(f"{lib.base}/machines/{machine['id']}/documents/{uuid4()}"),
    ]

    assert [response.status_code for response in responses] == [404, 404]


# ─────────────────────────── access ───────────────────────────


async def test_deliveries_require_session(lib: Library) -> None:
    lib.editor.http.cookies.clear()

    responses = [
        await lib.editor.http.get(f"{lib.base}/customers"),
        await lib.editor.http.get(f"{lib.base}/deliveries"),
    ]

    assert [response.status_code for response in responses] == [401, 401]


async def test_other_tenants_rows_are_not_found(lib: Library, client_as: ClientAs) -> None:
    customer = await _customer(lib)
    delivery = await _delivery(lib, customer)
    machine = await _machine(lib, delivery)
    document = await create_document(lib)
    intruder = await make_library(client_as)
    base = intruder.base
    own_document = await create_document(intruder)
    own_machine = await _machine(intruder)

    responses = [
        await intruder.editor.http.get(f"{base}/customers/{customer['id']}"),
        await intruder.editor.http.patch(f"{base}/customers/{customer['id']}", json={"name": "X"}),
        await intruder.editor.http.get(f"{base}/deliveries/{delivery['id']}"),
        await intruder.editor.http.patch(f"{base}/deliveries/{delivery['id']}", json={"name": "X"}),
        await _add_machine(intruder, delivery, await _product(intruder)),
        await intruder.editor.http.get(f"{base}/machines/{machine['id']}"),
        await intruder.editor.http.patch(f"{base}/machines/{machine['id']}", json={"name": "X"}),
        await intruder.admin.http.post(f"{base}/machines/{machine['id']}/archive"),
        await intruder.editor.http.get(f"{base}/machines/{machine['id']}/documents"),
        await intruder.editor.http.post(
            f"{base}/machines/{machine['id']}/documents", json={"document_id": own_document["id"]}
        ),
        await intruder.editor.http.post(
            f"{base}/machines/{own_machine['id']}/documents", json={"document_id": document["id"]}
        ),
        await intruder.editor.http.delete(f"{base}/machines/{machine['id']}/documents/{document['id']}"),
        await intruder.editor.http.get(f"{lib.base}/deliveries/{delivery['id']}"),  # tenant A's URL as a non-member
    ]

    assert [response.status_code for response in responses] == [404] * 13
    assert [d["id"] for d in (await _get(intruder, "deliveries"))["items"]] == [
        (await _get(intruder, f"machines/{own_machine['id']}"))["delivery_id"]
    ]
    assert (await _get(lib, f"deliveries/{delivery['id']}"))["name"] == "Anlage Nord"


@pytest.mark.parametrize("role", [MemberRole.EDITOR, MemberRole.ADMIN, MemberRole.OWNER])
async def test_every_member_role_manages_deliveries(lib: Library, role: MemberRole) -> None:
    member = {MemberRole.EDITOR: lib.editor, MemberRole.ADMIN: lib.admin, MemberRole.OWNER: lib.owner}[role]

    response = await member.http.post(f"{lib.base}/customers", json={"name": "Kunde"})

    assert response.status_code == 201
