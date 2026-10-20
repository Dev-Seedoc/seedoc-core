"""Maintenance jobs (ARCHITECTURE §11, queue `maintenance`), started by the worker's periodic scheduler (UTC)."""

from seedoc.jobs.app import app
from seedoc.services import trash as trash_service

MAINTENANCE_QUEUE = "maintenance"


@app.periodic(cron="30 3 * * *", periodic_id="purge_trash")  # daily 03:30 UTC
@app.task(name="purge_trash", queue=MAINTENANCE_QUEUE, queueing_lock="purge_trash")
async def purge_trash(timestamp: int) -> None:
    """`timestamp` = the scheduled time (Procrastinate passes it to periodic tasks); the cut-off uses the clock."""
    await trash_service.purge_trash()
