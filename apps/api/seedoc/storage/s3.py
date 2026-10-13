"""Object storage over the S3 API (ARCHITECTURE §3; RustFS locally, D14). Keys follow NAMING §9.

Presigned URLs are signed locally (no network call) for `S3_ENDPOINT`, the address the **browser** uses, so the API
must reach the store under the same address. Never log a presigned URL (NAMING, logging rules): it works for anyone
who has it.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING
from urllib.parse import quote
from uuid import UUID

import boto3
from botocore.config import Config

from seedoc.config import get_settings

if TYPE_CHECKING:  # type stubs are a dev dependency; the production image does not have them
    from mypy_boto3_s3.client import S3Client

UPLOAD_URL_TTL = timedelta(minutes=15)  # BUSINESS_RULES §4
DOWNLOAD_URL_TTL = timedelta(seconds=120)  # BUSINESS_RULES §4: portal, operator and manufacturer downloads


def get_upload_key(tenant_id: UUID, upload_id: UUID) -> str:
    return f"tenants/{tenant_id}/uploads/{upload_id}"


def get_version_key(tenant_id: UUID, version_id: UUID) -> str:
    return f"tenants/{tenant_id}/versions/{version_id}.pdf"


@lru_cache
def get_s3_client() -> "S3Client":
    settings = get_settings()
    client: S3Client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        # Path-style URLs (`<endpoint>/<bucket>/<key>`) work with RustFS and Hetzner without wildcard DNS.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    return client


def presign_put(key: str, content_type: str, ttl: timedelta = UPLOAD_URL_TTL) -> tuple[str, datetime]:
    """URL the browser `PUT`s the file to, with this exact `Content-Type` header; returns `(url, expires_at)`.
    Size and SHA-256 are not enforced by the URL — the API checks the stored object before using it (M1-A4)."""
    url = get_s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=int(ttl.total_seconds()),
    )
    return url, datetime.now(UTC) + ttl


def presign_get(key: str, download_name: str, ttl: timedelta = DOWNLOAD_URL_TTL) -> tuple[str, datetime]:
    """Short-lived download URL that saves the file as `download_name` (NAMING §9); returns `(url, expires_at)`."""
    url = get_s3_client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": get_settings().s3_bucket,
            "Key": key,
            "ResponseContentDisposition": _get_content_disposition(download_name),
        },
        ExpiresIn=int(ttl.total_seconds()),
    )
    return url, datetime.now(UTC) + ttl


async def put_object(key: str, body: bytes, content_type: str) -> None:
    """Store `body` under `key` (used by jobs, e.g. exports; browsers upload through `presign_put`)."""
    client, bucket = get_s3_client(), get_settings().s3_bucket
    await asyncio.to_thread(lambda: client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type))


async def delete_object(key: str) -> None:
    """Delete `key`; deleting a key that does not exist is not an error (S3 semantics)."""
    client, bucket = get_s3_client(), get_settings().s3_bucket
    await asyncio.to_thread(lambda: client.delete_object(Bucket=bucket, Key=key))


def _get_content_disposition(file_name: str) -> str:
    """`attachment` with an ASCII fallback and the UTF-8 name (RFC 6266), so umlauts survive in every browser."""
    ascii_name = file_name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name, safe='')}"
