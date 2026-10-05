from httpx import AsyncClient


async def test_openapi_operation_ids_are_function_names(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    assert response.json()["paths"]["/api/v1/health"]["get"]["operationId"] == "get_health"


async def test_unknown_path_returns_not_found_error(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"
