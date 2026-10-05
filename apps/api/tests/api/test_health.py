import pytest
from httpx import AsyncClient


@pytest.mark.usefixtures("postgres")
async def test_get_health_ok_with_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
    assert response.headers["X-Request-ID"]


@pytest.mark.usefixtures("unreachable_database")
async def test_get_health_reports_unreachable_database(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "error"}
