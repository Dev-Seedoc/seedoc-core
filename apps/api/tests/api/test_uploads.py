"""API tests for create_upload (M1-A2, API.md §3.3, BUSINESS_RULES §3), against a real S3 server (RustFS).

The browser step is real too: the test `PUT`s a file to the presigned URL exactly as the web app will.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from httpx import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings
from seedoc.models import MemberRole, Upload
from seedoc.services.uploads import MAX_UPLOAD_BYTES
from seedoc.storage.s3 import get_s3_client
from tests.conftest import ClientAs, MemberClient

pytestmark = pytest.mark.usefixtures("postgres", "s3")

PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"


def _uploads(client: MemberClient) -> str:
    return f"/api/v1/app/tenants/{client.tenant.id}/uploads"


def _error_code(response: Response) -> str:
    return response.json()["error"]["code"]


def _body(data: bytes = PDF, /, **change: object) -> dict[str, object]:
    return {
        "file_name": "Betriebsanleitung TruLaser 2030.pdf",
        "size_bytes": len(data),
        "sha256_hex": hashlib.sha256(data).hexdigest(),
        "content_type": "application/pdf",
        **change,
    }


async def test_create_upload_stores_row_and_returns_presigned_put(client_as: ClientAs, admin_db: AsyncSession) -> None:
    editor = await client_as(MemberRole.EDITOR)

    response = await editor.http.post(_uploads(editor), json=_body())

    assert response.status_code == 201, response.text
    body = response.json()
    upload_id = UUID(body["upload_id"])
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=14) < expires_at - datetime.now(UTC) <= timedelta(minutes=15)

    upload = await admin_db.scalar(select(Upload).where(Upload.id == upload_id))
    assert upload is not None
    assert upload.tenant_id == editor.tenant.id
    assert upload.storage_key == f"tenants/{editor.tenant.id}/uploads/{upload_id}"
    assert (upload.file_name, upload.size_bytes, upload.content_type) == (
        "Betriebsanleitung TruLaser 2030.pdf",
        len(PDF),
        "application/pdf",
    )
    assert upload.sha256 == hashlib.sha256(PDF).digest()
    assert upload.created_by == editor.user.id
    assert upload.consumed_at is None
    assert timedelta(hours=23) < upload.expires_at - datetime.now(UTC) <= timedelta(hours=24)


async def test_browser_can_put_the_file_to_the_presigned_url(client_as: ClientAs) -> None:
    editor = await client_as(MemberRole.EDITOR)
    body = (await editor.http.post(_uploads(editor), json=_body())).json()

    async with httpx.AsyncClient() as browser:
        put = await browser.put(body["upload_url"], content=PDF, headers={"Content-Type": "application/pdf"})

    assert put.status_code == 200, put.text
    stored = get_s3_client().get_object(
        Bucket=get_settings().s3_bucket, Key=f"tenants/{editor.tenant.id}/uploads/{body['upload_id']}"
    )
    assert stored["Body"].read() == PDF


async def test_presigned_url_refuses_another_content_type(client_as: ClientAs) -> None:
    """The Content-Type is part of the signature, so the URL cannot be used to store e.g. an HTML page."""
    editor = await client_as(MemberRole.EDITOR)
    body = (await editor.http.post(_uploads(editor), json=_body())).json()

    async with httpx.AsyncClient() as browser:
        put = await browser.put(body["upload_url"], content=b"<html></html>", headers={"Content-Type": "text/html"})

    assert put.status_code == 403


@pytest.mark.parametrize("file_name", ["C:\\fakepath\\Anleitung.pdf", "../../etc/Anleitung.pdf"])
async def test_create_upload_keeps_only_the_file_name(
    client_as: ClientAs, admin_db: AsyncSession, file_name: str
) -> None:
    editor = await client_as(MemberRole.EDITOR)

    response = await editor.http.post(_uploads(editor), json=_body(file_name=file_name))

    assert response.status_code == 201
    stored = await admin_db.scalar(select(Upload.file_name).where(Upload.id == UUID(response.json()["upload_id"])))
    assert stored == "Anleitung.pdf"


async def test_create_upload_accepts_uppercase_hash_and_content_type_parameters(
    client_as: ClientAs, admin_db: AsyncSession
) -> None:
    editor = await client_as(MemberRole.EDITOR)

    response = await editor.http.post(
        _uploads(editor),
        json=_body(sha256_hex=hashlib.sha256(PDF).hexdigest().upper(), content_type="Application/PDF; qs=0.9"),
    )

    assert response.status_code == 201
    stored = await admin_db.scalar(select(Upload).where(Upload.id == UUID(response.json()["upload_id"])))
    assert stored is not None
    assert (stored.sha256, stored.content_type) == (hashlib.sha256(PDF).digest(), "application/pdf")


# ─────────────────────────── rules ───────────────────────────


@pytest.mark.parametrize("content_type", ["image/png", "application/octet-stream", "text/html"])
async def test_create_upload_refuses_non_pdf(client_as: ClientAs, content_type: str) -> None:
    editor = await client_as(MemberRole.EDITOR)

    response = await editor.http.post(_uploads(editor), json=_body(content_type=content_type))

    assert response.status_code == 415
    assert _error_code(response) == "unsupported_file_type"


async def test_create_upload_refuses_files_over_100_mb(client_as: ClientAs) -> None:
    editor = await client_as(MemberRole.EDITOR)

    at_limit = await editor.http.post(_uploads(editor), json=_body(size_bytes=MAX_UPLOAD_BYTES))
    over = await editor.http.post(_uploads(editor), json=_body(size_bytes=MAX_UPLOAD_BYTES + 1))

    assert at_limit.status_code == 201
    assert over.status_code == 413
    assert _error_code(over) == "file_too_large"


@pytest.mark.parametrize(
    "change",
    [{"size_bytes": 0}, {"sha256_hex": "abc"}, {"sha256_hex": "z" * 64}, {"file_name": "  "}, {"file_name": "x" * 256}],
    ids=["empty_file", "short_hash", "not_hex", "blank_name", "long_name"],
)
async def test_create_upload_rejects_invalid_input(client_as: ClientAs, change: dict[str, object]) -> None:
    editor = await client_as(MemberRole.EDITOR)

    response = await editor.http.post(_uploads(editor), json=_body(**change))

    assert response.status_code == 422
    assert _error_code(response) == "validation_failed"


# ─────────────────────────── access ───────────────────────────


async def test_create_upload_requires_session(client_as: ClientAs) -> None:
    editor = await client_as(MemberRole.EDITOR)
    editor.http.cookies.clear()

    response = await editor.http.post(_uploads(editor), json=_body())

    assert response.status_code == 401


async def test_create_upload_in_other_tenant_is_not_found(
    client_as: ClientAs, client_other_tenant: MemberClient, admin_db: AsyncSession
) -> None:
    owner = await client_as(MemberRole.OWNER)

    response = await client_other_tenant.http.post(_uploads(owner), json=_body())

    assert response.status_code == 404
    count = await admin_db.scalar(select(Upload.id).where(Upload.tenant_id == owner.tenant.id))
    assert count is None
