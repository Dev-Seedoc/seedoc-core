"""Worker entry point: `python -m seedoc.jobs.worker` (the `worker` service, same image as the API)."""

import asyncio
import logging
import sys

import structlog

from seedoc.config import get_settings
from seedoc.jobs.app import close_job_app, open_job_app
from seedoc.jobs.mail import MAIL_QUEUE
from seedoc.jobs.maintenance import MAINTENANCE_QUEUE
from seedoc.jobs.processing import PROCESSING_QUEUE
from seedoc.main import configure_logging

log = structlog.get_logger()

QUEUES = [PROCESSING_QUEUE, MAIL_QUEUE, MAINTENANCE_QUEUE]
CONCURRENCY = 2  # PDFs are parsed in threads; two at a time keep a small server responsive


async def run_worker() -> None:
    app = await open_job_app(get_settings().database_admin_url, max_size=CONCURRENCY + 2)
    log.info("worker_started", queues=QUEUES)
    try:
        await app.run_worker_async(queues=QUEUES, concurrency=CONCURRENCY, delete_jobs="successful")
    finally:
        await close_job_app()


def main() -> None:
    configure_logging()
    logging.basicConfig(level=logging.INFO)  # Procrastinate logs through the standard library (job names and ids)
    if sys.platform == "win32":  # psycopg cannot use the default Proactor loop
        asyncio.run(run_worker(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
