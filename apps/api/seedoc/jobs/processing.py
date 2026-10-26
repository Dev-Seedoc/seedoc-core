"""Processing jobs (ARCHITECTURE §11, queue `processing`). Thin: the work is in services/processing.py."""

import contextlib
from uuid import UUID

import procrastinate
import structlog
from procrastinate.exceptions import AlreadyEnqueued

from seedoc.ai.provider import AiConfigurationError
from seedoc.config import get_settings
from seedoc.jobs.app import app, open_job_app
from seedoc.services import processing as processing_service

log = structlog.get_logger()

PROCESSING_QUEUE = "processing"
PROCESS_VERSION_RETRIES = 3  # after the first run; waits 5 s, 25 s, 125 s (storage or database hiccups)
EMBED_CHUNKS_RETRIES = 5  # waits 5 s … ~52 min: rides out a provider outage or rate limit


@app.task(
    name="process_version",
    queue=PROCESSING_QUEUE,
    pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=PROCESS_VERSION_RETRIES, exponential_wait=5),
)
async def process_version(context: procrastinate.JobContext, version_id: str) -> None:
    try:
        needs_embeddings = await processing_service.process_version(UUID(version_id))
        if needs_embeddings:
            # In the worker, so the app is open as seedoc_admin; a failure here retries the whole job.
            with contextlib.suppress(AlreadyEnqueued):
                await embed_chunks.configure(queueing_lock=f"embed:{version_id}").defer_async(version_id=version_id)
    except Exception:
        if context.job.attempts >= PROCESS_VERSION_RETRIES:  # the last try: never leave the version "processing"
            await processing_service.mark_version_failed(UUID(version_id))
        raise


@app.task(
    name="embed_chunks",
    queue=PROCESSING_QUEUE,
    pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=EMBED_CHUNKS_RETRIES, exponential_wait=5),
)
async def embed_chunks(context: procrastinate.JobContext, version_id: str) -> None:
    try:
        await processing_service.embed_chunks(UUID(version_id))
    except AiConfigurationError as exc:
        # A wrong key or model: retrying cannot help, so the version fails now and the job ends.
        log.error("ai_configuration_error", version_id=version_id, error=str(exc))
        await processing_service.mark_version_failed(UUID(version_id), processing_service.ERROR_INDEXING)
    except Exception:
        if context.job.attempts >= EMBED_CHUNKS_RETRIES:
            await processing_service.mark_version_failed(UUID(version_id), processing_service.ERROR_INDEXING)
        raise


async def defer_process_version(version_id: UUID) -> None:
    """Queue `process_version` after the version's transaction committed. Never raises: the version exists either
    way, so a queue problem is logged (the version then stays `pending`) instead of failing the upload."""
    try:
        await open_job_app(get_settings().database_url)
        await process_version.configure(queueing_lock=str(version_id)).defer_async(version_id=str(version_id))
    except AlreadyEnqueued:
        pass
    except Exception as exc:
        log.error("job_defer_failed", job="process_version", version_id=str(version_id), error=type(exc).__name__)
