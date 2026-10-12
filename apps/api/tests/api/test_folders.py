"""API tests for folders (M1-A3, API.md §3.2). Written before the code (handover H-08): they fail until
`routers/app/folders.py` + `services/folders.py` exist. Never change them to make the code pass — ask Raven.

Contract the tests pin down:
- `FolderRead{id, space_id, parent_id, name, path, sort_order, default_access_level, default_doc_type,
  default_language, created_at, updated_at}`; `path` = folder names from the root, joined by "/" (no space name).
- `list_folders?space_id=` → every folder of the space as a flat `Page` (never paged, `next_cursor` null), sorted by
  `path`. The client builds the tree from `parent_id`.
- `FolderUpdate{name?, sort_order?, default_access_level?, default_doc_type?, default_language?}`: a field left out
  stays as it is; `default_doc_type: null` / `default_language: null` clears that default. Moving a folder (changing
  `parent_id`) is not part of M1-A3.
- `delete_folder` only for an empty folder: no subfolders and no documents (trashed ones count too) → else
  `409 conflict`.
- Every folder route: any member (`editor`); another tenant's ids → 404.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.models import AccessLevel, AuditEvent, DocType, Document, MemberRole
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres")

FOLDER_FIELDS = {
    "id",
    "space_id",
    "parent_id",
    "name",
    "path",
    "sort_order",
    "default_access_level",
    "default_doc_type",
    "default_language",
    "created_at",
    "updated_at",
}


def _base(client: MemberClient) -> str:
    return f"/api/v1/app/tenants/{client.tenant.id}"


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


async def _create_space(client: MemberClient, name: str = "Handbücher") -> str:
    """Spaces are admin-only; the tests create them as the tenant's owner."""
    response = await client.http.post(f"{_base(client)}/spaces", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_folder(
    client: MemberClient, space_id: str, name: str, parent_id: str | None = None, **defaults: Any
) -> dict[str, Any]:
    body = {"space_id": space_id, "parent_id": parent_id, "name": name, "default_access_level": "public", **defaults}
    response = await client.http.post(f"{_base(client)}/folders", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _list_folders(client: MemberClient, space_id: str) -> list[dict[str, Any]]:
    response = await client.http.get(f"{_base(client)}/folders", params={"space_id": space_id})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["next_cursor"] is None
    return body["items"]


@pytest.fixture
async def team(client_as: ClientAs) -> tuple[MemberClient, MemberClient, str]:
    """(owner, editor) of one tenant and the id of one space in it."""
    owner = await client_as(MemberRole.OWNER)
    editor = await client_as(MemberRole.EDITOR, tenant=owner.tenant)
    return owner, editor, await _create_space(owner)


# ─────────────────────────── create + list ───────────────────────────


async def test_create_folder_returns_folder_with_path(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team

    folder = await _create_folder(
        editor, space_id, "  Sicherheit  ", default_access_level="customer", default_doc_type="safety_instruction"
    )

    assert set(folder) == FOLDER_FIELDS
    assert folder["name"] == "Sicherheit"  # surrounding spaces removed
    assert folder["path"] == "Sicherheit"
    assert folder["space_id"] == space_id
    assert folder["parent_id"] is None
    assert folder["sort_order"] == 0
    assert folder["default_access_level"] == "customer"
    assert folder["default_doc_type"] == "safety_instruction"
    assert folder["default_language"] is None


async def test_create_subfolder_path_includes_parents(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    root = await _create_folder(editor, space_id, "Sicherheit")
    child = await _create_folder(editor, space_id, "Hinweise", parent_id=root["id"])

    grandchild = await _create_folder(editor, space_id, "Laser", parent_id=child["id"], default_language="de")

    assert child["path"] == "Sicherheit/Hinweise"
    assert grandchild["path"] == "Sicherheit/Hinweise/Laser"
    assert grandchild["parent_id"] == child["id"]
    assert grandchild["default_language"] == "de"


async def test_create_folder_writes_audit_event(
    team: tuple[MemberClient, MemberClient, str], admin_db: AsyncSession
) -> None:
    _, editor, space_id = team

    folder = await _create_folder(editor, space_id, "Wartung")

    event = await admin_db.scalar(select(AuditEvent).where(AuditEvent.entity_id == UUID(folder["id"])))
    assert event is not None
    assert (event.action, event.entity, event.tenant_id, event.actor_id) == (
        "folder.created",
        "folder",
        editor.tenant.id,
        editor.user.id,
    )


async def test_list_folders_is_flat_and_sorted_by_path(team: tuple[MemberClient, MemberClient, str]) -> None:
    owner, editor, space_id = team
    wartung = await _create_folder(editor, space_id, "Wartung")
    sicherheit = await _create_folder(editor, space_id, "Sicherheit")
    await _create_folder(editor, space_id, "Hinweise", parent_id=sicherheit["id"])
    await _create_folder(editor, space_id, "Intervalle", parent_id=wartung["id"])
    other_space = await _create_space(owner, "Zertifikate")
    await _create_folder(editor, other_space, "CE")

    folders = await _list_folders(editor, space_id)

    assert [folder["path"] for folder in folders] == [
        "Sicherheit",
        "Sicherheit/Hinweise",
        "Wartung",
        "Wartung/Intervalle",
    ]
    assert {folder["space_id"] for folder in folders} == {space_id}
    assert all(set(folder) == FOLDER_FIELDS for folder in folders)


async def test_same_name_is_allowed_under_different_parents(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    a = await _create_folder(editor, space_id, "Laser")
    b = await _create_folder(editor, space_id, "Biegen")

    first = await _create_folder(editor, space_id, "Wartung", parent_id=a["id"])
    second = await _create_folder(editor, space_id, "Wartung", parent_id=b["id"])

    assert (first["path"], second["path"]) == ("Laser/Wartung", "Biegen/Wartung")


@pytest.mark.parametrize("nested", [False, True], ids=["root", "subfolder"])
async def test_create_folder_with_taken_name_conflicts(
    team: tuple[MemberClient, MemberClient, str], nested: bool
) -> None:
    _, editor, space_id = team
    parent_id = (await _create_folder(editor, space_id, "Sicherheit"))["id"] if nested else None
    await _create_folder(editor, space_id, "Wartung", parent_id=parent_id)

    response = await editor.http.post(
        f"{_base(editor)}/folders",
        json={"space_id": space_id, "parent_id": parent_id, "name": "Wartung", "default_access_level": "public"},
    )

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


async def test_create_folder_rejects_parent_from_other_space(team: tuple[MemberClient, MemberClient, str]) -> None:
    owner, editor, space_id = team
    other_space = await _create_space(owner, "Zertifikate")
    parent = await _create_folder(editor, other_space, "CE")

    response = await editor.http.post(
        f"{_base(editor)}/folders",
        json={"space_id": space_id, "parent_id": parent["id"], "name": "X", "default_access_level": "public"},
    )

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 201},
        {"default_access_level": "secret"},
        {"default_doc_type": "novel"},
        {"default_language": "xx"},
        {"default_language": "DE"},
    ],
    ids=["empty", "blank", "too_long", "access_level", "doc_type", "language", "language_case"],
)
async def test_create_folder_rejects_invalid_input(
    team: tuple[MemberClient, MemberClient, str], change: dict[str, str]
) -> None:
    _, editor, space_id = team
    body = {"space_id": space_id, "name": "Wartung", "default_access_level": "public", **change}

    response = await editor.http.post(f"{_base(editor)}/folders", json=body)

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


async def test_create_folder_requires_default_access_level(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team

    response = await editor.http.post(f"{_base(editor)}/folders", json={"space_id": space_id, "name": "Wartung"})

    assert response.status_code == 422


async def test_list_folders_requires_space_id(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, _ = team

    response = await editor.http.get(f"{_base(editor)}/folders")

    assert response.status_code == 422


async def test_unknown_space_is_not_found(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, _ = team

    listed = await editor.http.get(f"{_base(editor)}/folders", params={"space_id": str(uuid4())})
    created = await editor.http.post(
        f"{_base(editor)}/folders",
        json={"space_id": str(uuid4()), "name": "X", "default_access_level": "public"},
    )

    assert (listed.status_code, created.status_code) == (404, 404)


# ─────────────────────────── update ───────────────────────────


async def test_rename_folder_updates_paths_of_subfolders(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    root = await _create_folder(editor, space_id, "Sicherheit")
    await _create_folder(editor, space_id, "Hinweise", parent_id=root["id"])

    response = await editor.http.patch(f"{_base(editor)}/folders/{root['id']}", json={"name": "Safety"})

    assert response.status_code == 200
    assert response.json()["path"] == "Safety"
    assert [folder["path"] for folder in await _list_folders(editor, space_id)] == ["Safety", "Safety/Hinweise"]


async def test_update_folder_changes_only_given_fields(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    folder = await _create_folder(
        editor, space_id, "Wartung", default_doc_type="maintenance_manual", default_language="de"
    )

    response = await editor.http.patch(
        f"{_base(editor)}/folders/{folder['id']}", json={"sort_order": 3, "default_access_level": "internal"}
    )

    assert response.status_code == 200
    updated = response.json()
    assert (updated["sort_order"], updated["default_access_level"]) == (3, "internal")
    assert (updated["name"], updated["default_doc_type"], updated["default_language"]) == (
        "Wartung",
        "maintenance_manual",
        "de",
    )


async def test_update_folder_null_clears_optional_defaults(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    folder = await _create_folder(
        editor, space_id, "Wartung", default_doc_type="maintenance_manual", default_language="de"
    )

    response = await editor.http.patch(
        f"{_base(editor)}/folders/{folder['id']}", json={"default_doc_type": None, "default_language": None}
    )

    assert response.status_code == 200
    assert (response.json()["default_doc_type"], response.json()["default_language"]) == (None, None)


async def test_rename_folder_to_sibling_name_conflicts(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    await _create_folder(editor, space_id, "Sicherheit")
    wartung = await _create_folder(editor, space_id, "Wartung")

    response = await editor.http.patch(f"{_base(editor)}/folders/{wartung['id']}", json={"name": "Sicherheit"})

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


@pytest.mark.parametrize(
    "change",
    [{"name": " "}, {"name": None}, {"sort_order": None}, {"default_access_level": None}, {"default_language": "xx"}],
    ids=["blank_name", "null_name", "null_sort_order", "null_access_level", "language"],
)
async def test_update_folder_rejects_invalid_input(
    team: tuple[MemberClient, MemberClient, str], change: dict[str, Any]
) -> None:
    _, editor, space_id = team
    folder = await _create_folder(editor, space_id, "Wartung")

    response = await editor.http.patch(f"{_base(editor)}/folders/{folder['id']}", json=change)

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


async def test_update_folder_writes_audit_event_with_changed_fields(
    team: tuple[MemberClient, MemberClient, str], admin_db: AsyncSession
) -> None:
    _, editor, space_id = team
    folder = await _create_folder(editor, space_id, "Wartung")

    await editor.http.patch(f"{_base(editor)}/folders/{folder['id']}", json={"name": "Service", "sort_order": 2})

    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == UUID(folder["id"]), AuditEvent.action == "folder.updated")
    )
    assert event is not None
    assert sorted(event.detail["fields"]) == ["name", "sort_order"]


# ─────────────────────────── delete ───────────────────────────


async def test_delete_empty_folder(team: tuple[MemberClient, MemberClient, str], admin_db: AsyncSession) -> None:
    _, editor, space_id = team
    folder = await _create_folder(editor, space_id, "Alt")

    response = await editor.http.delete(f"{_base(editor)}/folders/{folder['id']}")

    assert response.status_code == 204
    assert await _list_folders(editor, space_id) == []
    event = await admin_db.scalar(
        select(AuditEvent).where(AuditEvent.entity_id == UUID(folder["id"]), AuditEvent.action == "folder.deleted")
    )
    assert event is not None


async def test_delete_folder_with_subfolder_conflicts(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    parent = await _create_folder(editor, space_id, "Sicherheit")
    await _create_folder(editor, space_id, "Hinweise", parent_id=parent["id"])

    response = await editor.http.delete(f"{_base(editor)}/folders/{parent['id']}")

    assert response.status_code == 409
    assert _error_code(response) == "conflict"
    assert len(await _list_folders(editor, space_id)) == 2


@pytest.mark.parametrize("trashed", [False, True], ids=["document", "trashed_document"])
async def test_delete_folder_with_document_conflicts(
    team: tuple[MemberClient, MemberClient, str], admin_db: AsyncSession, trashed: bool
) -> None:
    _, editor, space_id = team
    folder = await _create_folder(editor, space_id, "Wartung")
    # Documents come with M1-A4; until then the row is inserted directly.
    admin_db.add(
        Document(
            tenant_id=editor.tenant.id,
            folder_id=UUID(folder["id"]),
            title="Wartungsplan",
            doc_type=DocType.MAINTENANCE_MANUAL,
            language="de",
            access_level=AccessLevel.INTERNAL,
            trashed_at=datetime.now(UTC) if trashed else None,
        )
    )
    await admin_db.commit()

    response = await editor.http.delete(f"{_base(editor)}/folders/{folder['id']}")

    assert response.status_code == 409
    assert _error_code(response) == "conflict"


# ─────────────────────────── access ───────────────────────────


async def test_folders_require_session(team: tuple[MemberClient, MemberClient, str]) -> None:
    _, editor, space_id = team
    editor.http.cookies.clear()

    response = await editor.http.get(f"{_base(editor)}/folders", params={"space_id": space_id})

    assert response.status_code == 401
    assert _error_code(response) == "unauthenticated"


async def test_other_tenants_folders_are_not_found(
    team: tuple[MemberClient, MemberClient, str], client_as: ClientAs
) -> None:
    """Tenant B uses its own URL with tenant A's ids: space, parent folder, folder — always 404, nothing changes."""
    _, editor, space_id = team
    folder = await _create_folder(editor, space_id, "Wartung")
    intruder = await client_as(MemberRole.OWNER)
    own = _base(intruder)
    own_space_id = await _create_space(intruder, "Eigener Bereich")

    responses = [
        await intruder.http.get(f"{own}/folders", params={"space_id": space_id}),
        await intruder.http.post(
            f"{own}/folders", json={"space_id": space_id, "name": "X", "default_access_level": "public"}
        ),
        await intruder.http.post(
            f"{own}/folders",
            json={"space_id": own_space_id, "parent_id": folder["id"], "name": "X", "default_access_level": "public"},
        ),
        await intruder.http.patch(f"{own}/folders/{folder['id']}", json={"name": "Taken over"}),
        await intruder.http.delete(f"{own}/folders/{folder['id']}"),
        # Tenant A's URL, as a non-member of tenant A.
        await intruder.http.get(f"{_base(editor)}/folders", params={"space_id": space_id}),
    ]

    assert [response.status_code for response in responses] == [404] * 6
    assert [f["name"] for f in await _list_folders(editor, space_id)] == ["Wartung"]
    assert await _list_folders(intruder, own_space_id) == []
