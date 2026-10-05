import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.schemas.health import HealthRead

log = structlog.get_logger()


async def get_health(db: AsyncSession) -> HealthRead:
    try:
        await db.execute(text("select 1"))
    except (SQLAlchemyError, OSError) as exc:
        log.warning("health_db_failed", error=type(exc).__name__)
        return HealthRead(status="error", db="error")
    return HealthRead(status="ok", db="ok")
