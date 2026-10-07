"""CSRF protection by Origin check (ARCHITECTURE §8)."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from seedoc.config import get_settings
from seedoc.errors import AppError, ErrorCode

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def csrf_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Every non-GET request that carries a cookie must send an `Origin` equal to `APP_URL`, else `403 csrf_failed`.

    TODO(M3-A1): also accept the active tenant domain on portal routes.
    """
    if request.method in _SAFE_METHODS or not request.cookies:
        return await call_next(request)

    origin = request.headers.get("origin")
    if origin is None or origin.rstrip("/").lower() != get_settings().app_url.rstrip("/").lower():
        error = AppError(ErrorCode.CSRF_FAILED)
        return JSONResponse(status_code=error.status_code, content=error.to_body())
    return await call_next(request)
