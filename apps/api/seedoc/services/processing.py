"""Processing of a document version (ARCHITECTURE §9, BUSINESS_RULES §3): the worker's `process_version` job.

`pending → processing → ready | failed`. The stored file is checked against the version's size and SHA-256, its
pages are read with pdfium, and the text is stored as chunks (`text_chunks`, full-text index per language). Then
`embed_chunks` adds an embedding to every chunk (batches of 96) and marks the version `ready`. Without `AI_API_KEY`
(local, CI, staging until a key exists) the chunks stay without embedding and the version is `ready` at once.

Runs in the worker as `seedoc_admin` (no request, no tenant context), so every query names the version id. Safe to
repeat: a `ready` version is left alone, and the chunks of an earlier attempt are replaced, never added to.
Network and PDF work happen outside the database transactions.
"""

import asyncio
import hashlib
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import structlog
from sqlalchemy import CursorResult, Text, delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.ai.chunking import build_chunks
from seedoc.ai.embeddings import batches
from seedoc.ai.pdf_text import PdfReadError, extract_page_texts
from seedoc.ai.provider import create_embeddings, is_ai_configured
from seedoc.db.engine import get_admin_sessionmaker
from seedoc.db.types import to_vector_literal
from seedoc.models.documents import Document, DocumentVersion, ProcessingStatus, TextChunk
from seedoc.storage.s3 import read_object

log = structlog.get_logger()

# `processing_error` texts: shown to editors, so short and without file content.
ERROR_FILE_MISSING = "the file is missing in storage"
ERROR_FILE_CHANGED = "the stored file does not match its checksum"
ERROR_NOT_READABLE = "the file is not a readable PDF (damaged or password-protected)"
ERROR_INTERNAL = "processing failed; upload the file again or contact support"
ERROR_INDEXING = "the text could not be indexed for search; upload the file again or contact support"


_STORE_EMBEDDINGS = text(
    "update text_chunks set embedding = batch.embedding::vector"
    " from unnest(cast(:ids as bigint[]), cast(:vectors as text[])) as batch(id, embedding)"
    " where text_chunks.id = batch.id"
)


class _ProcessingError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def process_version(version_id: UUID) -> bool:
    """Process one version; a version that does not exist (deleted meanwhile) or is already `ready` is skipped.
    A problem with the file marks the version `failed`; any other error is raised so the job is retried.
    True when the chunks still need embeddings (the version stays `processing` and the caller queues `embed_chunks`).
    """
    async with get_admin_sessionmaker()() as db:
        started = await _start(db, version_id)
        if started is None:
            return False
        version, language = started
        try:
            page_texts = await _read_pages(version)
        except _ProcessingError as failure:
            await mark_version_failed(version_id, failure.message)
            log.warning("version_processing_failed", version_id=str(version_id), error=failure.message)
            return False

        chunks = build_chunks(page_texts)
        async with db.begin():
            ts_config = await db.scalar(select(func.ts_config_for_language(language).cast(Text)))
            await db.execute(delete(TextChunk).where(TextChunk.version_id == version_id))
            if chunks:
                await db.execute(
                    insert(TextChunk),
                    [
                        {
                            "tenant_id": version.tenant_id,
                            "version_id": version_id,
                            "page_no": chunk.page_no,
                            "chunk_index": chunk.chunk_index,
                            "content": chunk.content,
                            "ts_config": ts_config,
                        }
                        for chunk in chunks
                    ],
                )
            needs_embeddings = bool(chunks) and is_ai_configured()
            status = ProcessingStatus.PROCESSING if needs_embeddings else ProcessingStatus.READY
            await _set_status(db, version_id, status, page_count=len(page_texts))
        log.info(
            "version_processed",
            version_id=str(version_id),
            page_count=len(page_texts),
            chunk_count=len(chunks),
            embeddings="queued" if needs_embeddings else "skipped",
        )
        return needs_embeddings


async def embed_chunks(version_id: UUID) -> None:
    """Embed the version's chunks that have no embedding yet, then mark it `ready`. Each batch is stored when it
    comes back, so a retry continues where the last attempt stopped and never pays twice. Only a version that is
    still `processing` is touched (deleted, `failed` or `ready` meanwhile → skipped). Provider errors are raised:
    the job retries `AiUnavailableError` and fails the version on `AiConfigurationError`."""
    async with get_admin_sessionmaker()() as db:
        async with db.begin():
            status = await db.scalar(select(DocumentVersion.processing_status).where(DocumentVersion.id == version_id))
            if status is not ProcessingStatus.PROCESSING:
                log.info("embedding_skipped", version_id=str(version_id), status=status)
                return
            rows = (
                await db.execute(
                    select(TextChunk.id, TextChunk.content)
                    .where(TextChunk.version_id == version_id, TextChunk.embedding.is_(None))
                    .order_by(TextChunk.chunk_index)
                )
            ).all()
        total_tokens = 0
        for batch in batches(rows):
            result = await create_embeddings([row.content for row in batch])
            total_tokens += result.total_tokens
            async with db.begin():
                # One statement per batch (all rows or none); an ORM bulk update by primary key lost single rows here.
                stored = cast(
                    CursorResult[Any],
                    await db.execute(
                        _STORE_EMBEDDINGS,
                        {"ids": [row.id for row in batch], "vectors": [to_vector_literal(v) for v in result.vectors]},
                    ),
                )
                if stored.rowcount != len(batch):  # chunks replaced meanwhile (processed again): start over
                    raise RuntimeError("the chunks changed while they were embedded")
        async with db.begin():
            await _set_status(db, version_id, ProcessingStatus.READY)
        log.info("version_embedded", version_id=str(version_id), chunk_count=len(rows), total_tokens=total_tokens)


async def mark_version_failed(version_id: UUID, message: str = ERROR_INTERNAL) -> None:
    """`failed` with `processing_error` — also used by the job after its last retry."""
    async with get_admin_sessionmaker()() as db, db.begin():
        await _set_status(db, version_id, ProcessingStatus.FAILED, error=message)


async def _start(db: AsyncSession, version_id: UUID) -> tuple[DocumentVersion, str] | None:
    async with db.begin():
        row = (
            await db.execute(
                select(DocumentVersion, Document.language)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(DocumentVersion.id == version_id)
                .with_for_update(of=DocumentVersion)
            )
        ).one_or_none()
        if row is None:
            log.warning("version_not_found", version_id=str(version_id))
            return None
        version, language = row
        if version.processing_status == ProcessingStatus.READY:
            return None
        version.processing_status = ProcessingStatus.PROCESSING
        version.processing_error = None
    return version, language


async def _read_pages(version: DocumentVersion) -> list[str]:
    data = await read_object(version.storage_key)
    if data is None:
        raise _ProcessingError(ERROR_FILE_MISSING)
    if len(data) != version.size_bytes or hashlib.sha256(data).digest() != version.sha256:
        raise _ProcessingError(ERROR_FILE_CHANGED)
    try:
        return await asyncio.to_thread(extract_page_texts, data)
    except PdfReadError as exc:
        raise _ProcessingError(ERROR_NOT_READABLE) from exc


async def _set_status(
    db: AsyncSession,
    version_id: UUID,
    status: ProcessingStatus,
    *,
    page_count: int | None = None,
    error: str | None = None,
) -> None:
    version = await db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id).with_for_update())
    if version is None:
        return
    version.processing_status = status
    version.processing_error = error
    version.processed_at = datetime.now(UTC)
    if page_count is not None:
        version.page_count = page_count
