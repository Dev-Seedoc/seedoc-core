"""API tests for `list_audit_events` (API.md §3.1): the tenant's audit log for admins and owners, newest first, with
exact-match filters and cursor paging."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import AuditEvent, MemberRole
from tests.api.library import Library, error_code, make_library
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres", "s3")


@pytest.fixture
async def lib(client_as: ClientAs) -> Library:
    return await make_library(client_as)


async def _list(lib: Library, *, member: MemberClient | None = None, **params: Any) -> dict[str, Any]:
    response = await (member or lib.admin).http.get(f"{lib.base}/audit", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def _list_all(lib: Library, **params: Any) -> list[dict[str, Any]]:
    """Every page, following `next_cursor`."""
    items: list[dict[str, Any]] = []
    query: dict[str, Any] = dict(params)
    while True:
        page = await _list(lib, **query)
        items += page["items"]
        if page["next_cursor"] is None:
            return items
        query["cursor"] = page["next_cursor"]


async def _add(admin_db: AsyncSession, tenant_id: UUID | None, action: str, **fields: Any) -> AuditEvent:
    event = AuditEvent(tenant_id=tenant_id, action=action, entity=fields.pop("entity", "document"), **fields)
    admin_db.add(event)
    await admin_db.commit()
    await admin_db.refresh(event)
    return event


async def test_admin_and_owner_may_list_editor_may_not(lib: Library) -> None:
    for member in (lib.owner, lib.admin):
        await _list(lib, member=member)

    response = await lib.editor.http.get(f"{lib.base}/audit")

    assert response.status_code == 403


async def test_other_tenant_gets_not_found(lib: Library, client_as: ClientAs) -> None:
    other_admin = await client_as(MemberRole.ADMIN)

    response = await other_admin.http.get(f"{lib.base}/audit")

    assert response.status_code == 404


async def test_an_event_has_the_documented_fields_and_no_ip_hash(lib: Library, admin_db: AsyncSession) -> None:
    entity_id = uuid4()
    event = await _add(
        admin_db,
        lib.admin.tenant.id,
        "document.updated",
        actor_id=lib.editor.user.id,
        entity_id=entity_id,
        detail={"fields": ["title"]},
        ip_hash="0123abcd",
    )

    item = (await _list(lib, limit=1))["items"][0]

    assert item == {
        "id": event.id,
        "action": "document.updated",
        "entity": "document",
        "entity_id": str(entity_id),
        "actor_id": str(lib.editor.user.id),
        "actor_name": lib.editor.user.full_name,
        "detail": {"fields": ["title"]},
        "created_at": item["created_at"],
    }
    assert item["created_at"]


async def test_a_system_event_has_no_actor(lib: Library, admin_db: AsyncSession) -> None:
    await _add(admin_db, lib.admin.tenant.id, "document.purged")

    item = (await _list(lib, limit=1))["items"][0]

    assert (item["action"], item["actor_id"], item["actor_name"]) == ("document.purged", None, None)


async def test_a_real_action_shows_up_with_its_actor(lib: Library) -> None:
    product = await lib.editor.http.post(f"{lib.base}/products", json={"name": "Laser 3030"})
    assert product.status_code == 201, product.text

    items = (await _list(lib, entity_id=product.json()["id"]))["items"]

    assert [(item["action"], item["entity"], item["actor_name"]) for item in items] == [
        ("product.created", "product", lib.editor.user.full_name)
    ]


async def test_lists_newest_first_and_only_own_tenant(
    lib: Library, client_as: ClientAs, admin_db: AsyncSession
) -> None:
    other = await client_as(MemberRole.ADMIN)
    await _add(admin_db, other.tenant.id, "document.created")
    await _add(admin_db, None, "auth.login_failed", entity="user")
    expected = list(
        await admin_db.scalars(
            select(AuditEvent.id)
            .where(AuditEvent.tenant_id == lib.admin.tenant.id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        )
    )

    items = await _list_all(lib)

    assert expected  # the library setup wrote some
    assert [item["id"] for item in items] == expected


async def test_pages_follow_the_cursor_without_gaps_or_repeats(lib: Library, admin_db: AsyncSession) -> None:
    for index in range(5):
        await _add(admin_db, lib.admin.tenant.id, f"test.event_{index}")
    everything = (await _list(lib, limit=200))["items"]

    first = await _list(lib, limit=2)
    second = await _list(lib, limit=2, cursor=first["next_cursor"])
    paged = await _list_all(lib, limit=2)

    assert [item["action"] for item in first["items"]] == ["test.event_4", "test.event_3"]
    assert [item["action"] for item in second["items"]] == ["test.event_2", "test.event_1"]
    assert [item["id"] for item in paged] == [item["id"] for item in everything]


async def test_last_page_has_no_cursor(lib: Library) -> None:
    page = await _list(lib, limit=200)

    assert page["next_cursor"] is None


async def test_default_limit_is_fifty(lib: Library, admin_db: AsyncSession) -> None:
    admin_db.add_all(
        AuditEvent(tenant_id=lib.admin.tenant.id, action="test.bulk", entity="document") for _ in range(60)
    )
    await admin_db.commit()

    page = await _list(lib)

    assert len(page["items"]) == 50
    assert page["next_cursor"] is not None


async def test_filters_are_exact_and_combine(lib: Library, admin_db: AsyncSession) -> None:
    target = uuid4()
    await _add(admin_db, lib.admin.tenant.id, "document.updated", entity_id=target)
    await _add(admin_db, lib.admin.tenant.id, "document.trashed", entity_id=target)
    await _add(admin_db, lib.admin.tenant.id, "document.updated", entity_id=uuid4())
    await _add(admin_db, lib.admin.tenant.id, "product.updated", entity="product", entity_id=target)

    by_action = await _list_all(lib, action="document.updated")
    by_entity = await _list_all(lib, entity="product")
    by_entity_id = await _list_all(lib, entity_id=str(target))
    combined = await _list_all(lib, action="document.updated", entity="document", entity_id=str(target))
    prefix = await _list_all(lib, action="document")

    assert len(by_action) == 2
    assert [item["action"] for item in by_entity] == ["product.updated"]
    assert [item["action"] for item in by_entity_id] == ["product.updated", "document.trashed", "document.updated"]
    assert [(item["action"], item["entity_id"]) for item in combined] == [("document.updated", str(target))]
    assert prefix == []


@pytest.mark.parametrize("params", [{"cursor": "not-a-cursor"}, {"limit": 0}, {"limit": 201}, {"entity_id": "x"}])
async def test_bad_query_is_rejected(lib: Library, params: dict[str, Any]) -> None:
    response = await lib.admin.http.get(f"{lib.base}/audit", params=params)

    assert response.status_code == 422
    assert error_code(response) == "validation_failed"


async def test_listing_writes_no_audit_event(lib: Library, admin_db: AsyncSession) -> None:
    count = select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == lib.admin.tenant.id)
    before = await admin_db.scalar(count)

    await _list(lib)

    assert await admin_db.scalar(count) == before
