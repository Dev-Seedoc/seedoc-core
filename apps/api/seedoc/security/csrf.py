"""CSRF Origin protection middleware."""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from seedoc.config import get_settings
from seedoc.errors import AppError, ErrorCode

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


async def csrf_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """CSRF: every non-GET request with a cookie must carry an Origin header matching APP_URL."""
    if request.method in _SAFE_METHODS:
        return await call_next(request)

    if not request.cookies:
        return await call_next(request)

    origin = request.headers.get("origin")
    if not origin:
        error = AppError(ErrorCode.CSRF_FAILED, "Missing Origin header.")
        return JSONResponse(status_code=error.status_code, content=error.to_body())

    settings = get_settings()
    # In M3-A1 we will also allow active tenant domains for portal routes.
    if origin.lower() != settings.app_url.lower():
        error = AppError(ErrorCode.CSRF_FAILED, "Origin not allowed.")
        return JSONResponse(status_code=error.status_code, content=error.to_body())

    return await call_next(request)
