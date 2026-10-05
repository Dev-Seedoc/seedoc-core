from fastapi import APIRouter, Response

from seedoc.deps import DbSession
from seedoc.schemas.health import HealthRead
from seedoc.services import health as health_service

router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health(db: DbSession, response: Response) -> HealthRead:
    result = await health_service.get_health(db)
    if result.status != "ok":
        response.status_code = 503
    return result
