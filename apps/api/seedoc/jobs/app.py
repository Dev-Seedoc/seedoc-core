"""The Procrastinate app (ARCHITECTURE §11): tasks register on `app`; who connects decides the role.

- The API only defers jobs, as `seedoc_app`, through a small pool opened on first use (`open_job_app`).
- The worker (`python -m seedoc.jobs.worker`) opens the app as `seedoc_admin` and runs the tasks.

Connections use psycopg (Procrastinate's driver); the URLs are the SQLAlchemy ones without `+asyncpg`. On Windows
psycopg needs a selector event loop (the worker entry point and the tests set one).
"""

import asyncio

import procrastinate

app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(), import_paths=["seedoc.jobs.mail", "seedoc.jobs.processing"]
)

# The event loop the app was opened on: a pool belongs to one loop (each test has its own).
_opened_on: asyncio.AbstractEventLoop | None = None


def get_conninfo(database_url: str) -> str:
    """`postgresql+asyncpg://…` → `postgresql://…` for psycopg."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def open_job_app(database_url: str, *, max_size: int = 4) -> procrastinate.App:
    """Open `app` with a pool for `database_url` on the running loop; a no-op when it is already open there."""
    global _opened_on
    loop = asyncio.get_running_loop()
    if _opened_on is loop:
        return app
    connector = procrastinate.PsycopgConnector(conninfo=get_conninfo(database_url), min_size=1, max_size=max_size)
    # What App.replace_connector does, without restoring the old one afterwards.
    app.connector = connector
    app.job_manager.connector = connector
    await app.open_async()
    _opened_on = loop
    return app


async def close_job_app() -> None:
    """Close the pool if it was opened on this loop (a pool of a finished loop is simply dropped)."""
    global _opened_on
    if _opened_on is asyncio.get_running_loop():
        await app.close_async()
    _opened_on = None
