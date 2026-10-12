"""API tests for spaces (M1-A3 reference implementation, API.md §3.2).

Pattern for every /app resource: happy path, 401 without session, 403 for a role that is too low, 404 for another
tenant's ids (and for a tenant the user is not a member of), 422 for invalid input, plus each business rule.
"""

from uuid import UUID, uuid4

import pytest
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import AuditEvent, MemberRole
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres")


def _spaces(client: MemberClient) -> str:
    return f"/api/v1/app/tenants/{client.tenant.id}/spaces"


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


async def _create_space(client: MemberClient, name: str = "Handbücher") -> dict[str, str]:
    response = await client.http.post(_spaces(client), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


# ─────────────────────────── happy path ───────────────────────────


async def test_create_space_returns_space_and_writes_audit_event(client_as: ClientAs, admin_db: AsyncSession) -> None:
    admin = await client_as(MemberRole.ADMIN)

    space = await _create_space(admin, "  Handbücher  ")

    assert space["name"] == "Handbücher"  # surrounding spaces removed
    assert UUID(space["id"])
    assert space["created_at"]
    event = await admin_db.scalar(select(AuditEvent).where(AuditEvent.entity_id == UUID(space["id"])))
    assert event is not None
    assert (event.action, event.entity, event.tenant_id, event.actor_id) == (
        "space.created",
        "space",
        admin.tenant.id,
        admin.user.id,
    )


async def test_list_spaces_returns_own_spaces_by_name(client_as: ClientAs) -> None:
    owner = await client_as(MemberRole.OWNER)
    await _create_space(owner, "Zertifikate")
    await _create_space(owner, "Anleitungen")

    response = await owner.http.get(_spaces(owner))

    assert response.status_code == 200
    body = response.json()
    assert [space["name"] for space in body["items"]] == ["Anleitungen", "Zertifikate"]
    assert body["next_cursor"] is None


async def test_editor_can_list_spaces(client_as: ClientAs) -> None:
    editor = await client_as(MemberRole.EDITOR)

    response = await editor.http.get(_spaces(editor))

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


async def test_update_space_renames_it(client_as: ClientAs) -> None:
    admin = await client_as(MemberRole.ADMIN)
    space = await _create_space(admin)

    response = await admin.http.patch(f"{_spaces(admin)}/{space['id']}", json={"name": "Dokumentation"})

    assert response.status_code == 200
    assert response.json()["name"] == "Dokumentation"
    listed = (await admin.http.get(_spaces(admin))).json()["items"]
    assert [item["name"] for item in listed] == ["Dokumentation"]


async def test_update_space_without_fields_changes_nothing(client_as: ClientAs) -> None:
    admin = await client_as(MemberRole.ADMIN)
    space = await _create_space(admin)

    response = await admin.http.patch(f"{_spaces(admin)}/{space['id']}", json={})

    assert response.status_code == 200
    assert response.json() == space


# ─────────────────────────── access ───────────────────────────


async def test_spaces_require_session(client_as: ClientAs) -> None:
    owner = await client_as(MemberRole.OWNER)
    owner.http.cookies.clear()

    response = await owner.http.get(_spaces(owner))

    assert response.status_code == 401
    assert _error_code(response) == "unauthenticated"


async def test_editor_cannot_create_space(client_as: ClientAs) -> None:
    editor = await client_as(MemberRole.EDITOR)

    response = await editor.http.post(_spaces(editor), json={"name": "Handbücher"})

    assert response.status_code == 403
    assert _error_code(response) == "forbidden"


async def test_editor_cannot_update_space(client_as: ClientAs) -> None:
    owner = await client_as(MemberRole.OWNER)
    space = await _create_space(owner)
    editor = await client_as(MemberRole.EDITOR, tenant=owner.tenant)

    response = await editor.http.patch(f"{_spaces(editor)}/{space['id']}", json={"name": "X"})

    assert response.status_code == 403
    assert _error_code(response) == "forbidden"


async def test_non_member_gets_404_for_the_tenant(client_as: ClientAs, client_other_tenant: MemberClient) -> None:
    owner = await client_as(MemberRole.OWNER)

    response = await client_other_tenant.http.get(_spaces(owner))

    assert response.status_code == 404
    assert _error_code(response) == "not_found"


async def test_other_tenants_space_is_not_found(client_as: ClientAs) -> None:
    owner_a = await client_as(MemberRole.OWNER)
    owner_b = await client_as(MemberRole.OWNER)
    space_b = await _create_space(owner_b)

    response = await owner_a.http.patch(f"{_spaces(owner_a)}/{space_b['id']}", json={"name": "Taken over"})

    assert response.status_code == 404
    assert _error_code(response) == "not_found"
    names_b = [item["name"] for item in (await owner_b.http.get(_spaces(owner_b))).json()["items"]]
    assert names_b == ["Handbücher"]
    assert (await owner_a.http.get(_spaces(owner_a))).json()["items"] == []


async def test_unknown_space_is_not_found(client_as: ClientAs) -> None:
    admin = await client_as(MemberRole.ADMIN)

    response = await admin.http.patch(f"{_spaces(admin)}/{uuid4()}", json={"name": "X"})

    assert response.status_code == 404


# ─────────────────────────── validation ───────────────────────────


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
async def test_create_space_rejects_invalid_name(client_as: ClientAs, name: str) -> None:
    admin = await client_as(MemberRole.ADMIN)

    response = await admin.http.post(_spaces(admin), json={"name": name})

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


async def test_update_space_rejects_empty_name(client_as: ClientAs) -> None:
    admin = await client_as(MemberRole.ADMIN)
    space = await _create_space(admin)

    response = await admin.http.patch(f"{_spaces(admin)}/{space['id']}", json={"name": " "})

    assert response.status_code == 422
