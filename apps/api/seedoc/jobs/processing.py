"""Processing jobs (ARCHITECTURE §11, queue `processing`). Thin: the work is in services/processing.py."""

from uuid import UUID

import procrastinate
import structlog
from procrastinate.exceptions import AlreadyEnqueued

from seedoc.config import get_settings
from seedoc.jobs.app import app, open_job_app
from seedoc.services import processing as processing_service

log = structlog.get_logger()

PROCESSING_QUEUE = "processing"
PROCESS_VERSION_RETRIES = 3  # after the first run; waits 5 s, 25 s, 125 s (storage or database hiccups)


@app.task(
    name="process_version",
    queue=PROCESSING_QUEUE,
    pass_context=True,
    retry=procrastinate.RetryStrategy(max_attempts=PROCESS_VERSION_RETRIES, exponential_wait=5),
)
async def process_version(context: procrastinate.JobContext, version_id: str) -> None:
    try:
        await processing_service.process_version(UUID(version_id))
    except Exception:
        if context.job.attempts >= PROCESS_VERSION_RETRIES:  # the last try: never leave the version "processing"
            await processing_service.mark_version_failed(UUID(version_id))
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
