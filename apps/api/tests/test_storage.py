"""`storage/s3.py` against a real S3 server (RustFS): keys, put, presigned download, delete, purge."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from seedoc.config import get_settings
from seedoc.storage.s3 import (
    delete_object,
    get_s3_client,
    get_upload_key,
    get_version_key,
    presign_get,
    purge_object,
    put_object,
)

pytestmark = pytest.mark.usefixtures("s3")


def test_keys_follow_naming() -> None:
    tenant_id, object_id = uuid4(), uuid4()

    assert get_upload_key(tenant_id, object_id) == f"tenants/{tenant_id}/uploads/{object_id}"
    assert get_version_key(tenant_id, object_id) == f"tenants/{tenant_id}/versions/{object_id}.pdf"


async def test_put_then_download_with_presigned_get() -> None:
    key = f"tenants/{uuid4()}/versions/{uuid4()}.pdf"
    await put_object(key, b"%PDF-1.7 test", "application/pdf")

    url, expires_at = presign_get(key, "Betriebsanleitung_de_v1.pdf")
    async with httpx.AsyncClient() as browser:
        response = await browser.get(url)

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7 test"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert timedelta(seconds=110) < expires_at - datetime.now(UTC) <= timedelta(seconds=120)


async def test_download_name_keeps_umlauts() -> None:
    key = f"tenants/{uuid4()}/versions/{uuid4()}.pdf"
    await put_object(key, b"%PDF-1.7", "application/pdf")

    url, _ = presign_get(key, 'Sicherheitshinweise "Laser" Größe_de_v2.pdf')
    async with httpx.AsyncClient() as browser:
        disposition = (await browser.get(url)).headers["content-disposition"]

    assert 'filename="Sicherheitshinweise _Laser_ Gr__e_de_v2.pdf"' in disposition
    assert "filename*=UTF-8''Sicherheitshinweise%20%22Laser%22%20Gr%C3%B6%C3%9Fe_de_v2.pdf" in disposition


async def test_delete_object_removes_it_and_tolerates_missing_keys() -> None:
    key = f"tenants/{uuid4()}/uploads/{uuid4()}"
    await put_object(key, b"%PDF-1.7", "application/pdf")

    await delete_object(key)
    await delete_object(key)  # already gone: no error

    url, _ = presign_get(key, "x.pdf")
    async with httpx.AsyncClient() as browser:
        assert (await browser.get(url)).status_code == 404


async def test_purge_object_removes_every_version_of_the_key_only() -> None:
    client, bucket = get_s3_client(), get_settings().s3_bucket
    client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})  # as on staging
    prefix = f"tenants/{uuid4()}/versions/"
    key, neighbour = f"{prefix}{uuid4()}.pdf", f"{prefix}{uuid4()}.pdf"
    await put_object(key, b"%PDF-1.7 first", "application/pdf")
    await put_object(key, b"%PDF-1.7 second", "application/pdf")
    await delete_object(key)  # only a delete marker: both versions are still stored
    await put_object(neighbour, b"%PDF-1.7 other", "application/pdf")

    await purge_object(key)

    listing = client.list_object_versions(Bucket=bucket, Prefix=prefix)
    remaining = [entry.get("Key") for entry in [*listing.get("Versions", []), *listing.get("DeleteMarkers", [])]]
    assert remaining == [neighbour]
    await purge_object(key)  # nothing left: not an error
