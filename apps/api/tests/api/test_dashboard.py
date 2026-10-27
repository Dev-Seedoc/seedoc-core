"""API tests for `get_dashboard` (API.md §3.1): counts of the tenant's documents, products, deliveries and processing
states, plus its 10 newest audit events."""

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import AuditEvent, Delivery, DeliveryStatus, Document, DocumentVersion, MemberRole, ProcessingStatus
from tests.api.library import Library, create_document, make_library
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres", "s3")


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    return await make_library(client_as)


async def _dashboard(member: MemberClient) -> dict[str, Any]:
    response = await member.http.get(f"/api/v1/app/tenants/{member.tenant.id}/dashboard")
    assert response.status_code == 200, response.text
    return response.json()


async def _set_status(admin_db: AsyncSession, document: dict[str, Any], status: ProcessingStatus) -> None:
    version_id = await admin_db.scalar(
        select(Document.current_version_id)
        .where(Document.id == UUID(document["id"]))
        .execution_options(populate_existing=True)
    )
    await admin_db.execute(
        update(DocumentVersion).where(DocumentVersion.id == version_id).values(processing_status=status)
    )
    await admin_db.commit()


async def _product(lib: Library, name: str) -> None:
    response = await lib.editor.http.post(f"{lib.base}/products", json={"name": name})
    assert response.status_code == 201, response.text


async def _delivery(lib: Library, customer_id: str, name: str) -> dict[str, Any]:
    response = await lib.editor.http.post(
        f"{lib.base}/deliveries", json={"customer_id": customer_id, "kind": "system", "name": name}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_events(admin_db: AsyncSession, tenant_id: UUID | None, *actions: str) -> None:
    """Audit events in this order (later = newer: same `created_at`, higher `id`)."""
    admin_db.add_all(AuditEvent(tenant_id=tenant_id, action=action, entity="document") for action in actions)
    await admin_db.commit()


async def test_fresh_tenant_shows_zeros_and_no_events(client_as: ClientAs) -> None:
    editor = await client_as(MemberRole.EDITOR)

    assert await _dashboard(editor) == {
        "document_count": 0,
        "product_count": 0,
        "delivery_count": 0,
        "processing_count": 0,
        "failed_count": 0,
        "recent_events": [],
    }


async def test_counts_documents_by_the_status_of_their_current_version(lib: Library, admin_db: AsyncSession) -> None:
    ready = await create_document(lib, title="Bereit")
    await create_document(lib, title="Wartet")  # pending, as after upload
    processing = await create_document(lib, title="In Arbeit")
    failed = await create_document(lib, title="Fehler")
    trashed = await create_document(lib, title="Papierkorb")
    await _set_status(admin_db, ready, ProcessingStatus.READY)
    await _set_status(admin_db, processing, ProcessingStatus.PROCESSING)
    await _set_status(admin_db, failed, ProcessingStatus.FAILED)
    await _set_status(admin_db, trashed, ProcessingStatus.FAILED)
    trash = await lib.editor.http.post(f"{lib.base}/documents/{trashed['id']}/trash")
    assert trash.status_code == 200, trash.text

    dashboard = await _dashboard(lib.editor)

    assert (dashboard["document_count"], dashboard["processing_count"], dashboard["failed_count"]) == (4, 2, 1)


async def test_counts_products_and_deliveries_that_are_not_archived(lib: Library, admin_db: AsyncSession) -> None:
    await _product(lib, "Laser 3030")
    await _product(lib, "Laser 4040")
    customer = await lib.editor.http.post(f"{lib.base}/customers", json={"name": "Muster AG"})
    assert customer.status_code == 201, customer.text
    await _delivery(lib, customer.json()["id"], "Anlage Nord")
    await _delivery(lib, customer.json()["id"], "Anlage Süd")
    archived = await _delivery(lib, customer.json()["id"], "Anlage Alt")
    await admin_db.execute(
        update(Delivery).where(Delivery.id == UUID(archived["id"])).values(status=DeliveryStatus.ARCHIVED)
    )
    await admin_db.commit()

    dashboard = await _dashboard(lib.editor)

    assert (dashboard["product_count"], dashboard["delivery_count"]) == (2, 2)


async def test_counts_only_own_tenant(lib: Library, client_as: ClientAs) -> None:
    other = await make_library(client_as)
    await create_document(other, title="Fremd")
    await _product(other, "Fremdprodukt")
    await create_document(lib, title="Eigen")

    dashboard = await _dashboard(lib.editor)

    assert (dashboard["document_count"], dashboard["product_count"]) == (1, 0)


async def test_recent_events_are_the_ten_newest_of_this_tenant(
    lib: Library, client_as: ClientAs, admin_db: AsyncSession
) -> None:
    other = await client_as(MemberRole.EDITOR)
    actions = [f"document.updated.{index}" for index in range(12)]
    await _add_events(admin_db, lib.editor.tenant.id, *actions)
    await _add_events(admin_db, other.tenant.id, "document.created")
    await _add_events(admin_db, None, "auth.login_failed")

    events = (await _dashboard(lib.editor))["recent_events"]

    assert [event["action"] for event in events] == list(reversed(actions))[:10]


async def test_recent_events_have_the_audit_event_shape(lib: Library, admin_db: AsyncSession) -> None:
    admin_db.add(
        AuditEvent(
            tenant_id=lib.editor.tenant.id,
            actor_id=lib.admin.user.id,
            action="document.updated",
            entity="document",
            detail={"fields": ["title"]},
            ip_hash="0123abcd",
        )
    )
    await admin_db.commit()

    event = (await _dashboard(lib.editor))["recent_events"][0]

    assert set(event) == {"id", "action", "entity", "entity_id", "actor_id", "actor_name", "detail", "created_at"}
    assert (event["actor_id"], event["actor_name"], event["detail"]) == (
        str(lib.admin.user.id),
        lib.admin.user.full_name,
        {"fields": ["title"]},
    )


async def test_every_member_role_sees_the_dashboard(lib: Library) -> None:
    for member in (lib.owner, lib.admin, lib.editor):
        await _dashboard(member)


async def test_other_tenant_gets_not_found(lib: Library, client_other_tenant: MemberClient) -> None:
    response = await client_other_tenant.http.get(f"{lib.base}/dashboard")

    assert response.status_code == 404


async def test_reading_the_dashboard_writes_no_audit_event(lib: Library, admin_db: AsyncSession) -> None:
    count = select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == lib.editor.tenant.id)
    before = await admin_db.scalar(count)

    await _dashboard(lib.editor)

    assert await admin_db.scalar(count) == before
