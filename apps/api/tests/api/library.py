"""Shared setup for API tests that need documents: a tenant with an owner, an admin and an editor, a space
"Handbücher" with a folder "Laser" (defaults: operating manual, customer), and documents created the real way
(upload → PUT → `create_document`)."""

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from httpx import Response

from seedoc.models import MemberRole
from tests.conftest import ClientAs, MemberClient


@dataclass(frozen=True)
class Library:
    owner: MemberClient
    admin: MemberClient
    editor: MemberClient
    space_id: str
    folder_id: str

    @property
    def base(self) -> str:
        return f"/api/v1/app/tenants/{self.editor.tenant.id}"


async def make_library(client_as: ClientAs) -> Library:
    owner = await client_as(MemberRole.OWNER)
    admin = await client_as(MemberRole.ADMIN, tenant=owner.tenant)
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
    return Library(owner=owner, admin=admin, editor=editor, space_id=space["id"], folder_id=folder["id"])


def error_code(response: Response) -> str:
    return response.json()["error"]["code"]


async def create_document(lib: Library, title: str = "Betriebsanleitung", language: str = "de") -> dict[str, Any]:
    """A new document (its own language group) with one pending version; returns its `DocumentRead`."""
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
            "title": title,
            "language": language,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
