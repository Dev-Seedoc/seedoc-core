"""Uploads (API.md §3.3, BUSINESS_RULES §3). `create_upload` records what the browser is about to send and returns a
presigned PUT URL; the file itself never passes through the API. `create_document` / `create_document_version`
(M1-A4) later check the stored object against this row (size, SHA-256, `%PDF-`) before using it."""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.db.engine import tenant_transaction
from seedoc.deps import RequestContext
from seedoc.errors import AppError, ErrorCode
from seedoc.models.documents import Upload
from seedoc.schemas.uploads import UploadCreate, UploadRead
from seedoc.storage.s3 import get_upload_key, presign_put

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # BUSINESS_RULES §3: ≤ 100 MB
PDF_CONTENT_TYPE = "application/pdf"
UPLOAD_CONSUME_TTL = timedelta(hours=24)  # DATA_MODEL uploads.expires_at: 24 h to turn it into a document/version


async def create_upload(db: AsyncSession, ctx: RequestContext, body: UploadCreate) -> UploadRead:
    if body.content_type.split(";")[0].strip().lower() != PDF_CONTENT_TYPE:
        raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE, "only PDF files can be uploaded")
    if body.size_bytes > MAX_UPLOAD_BYTES:
        raise AppError(ErrorCode.FILE_TOO_LARGE, details={"max_bytes": MAX_UPLOAD_BYTES})

    upload_id = uuid.uuid4()
    async with tenant_transaction(db, ctx.tenant_id) as tenant_id:
        key = get_upload_key(tenant_id, upload_id)
        db.add(
            Upload(
                id=upload_id,
                tenant_id=tenant_id,
                storage_key=key,
                file_name=_get_base_name(body.file_name),
                size_bytes=body.size_bytes,
                sha256=bytes.fromhex(body.sha256_hex),
                content_type=PDF_CONTENT_TYPE,
                created_by=ctx.user_id,
                expires_at=datetime.now(UTC) + UPLOAD_CONSUME_TTL,
            )
        )
    # Signed locally after the commit: the URL is only handed out once the row exists.
    url, expires_at = presign_put(key, PDF_CONTENT_TYPE)
    return UploadRead(upload_id=upload_id, upload_url=url, expires_at=expires_at)


def _get_base_name(file_name: str) -> str:
    """`C:\\fakepath\\Anleitung.pdf` → `Anleitung.pdf`: only the name is kept, never a client path."""
    return re.split(r"[\\/]", file_name)[-1].strip() or "document.pdf"
