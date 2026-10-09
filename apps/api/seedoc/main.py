import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from seedoc.config import get_settings
from seedoc.db.engine import dispose_engines
from seedoc.errors import AppError, ErrorCode
from seedoc.mail.send import send_pending_mail
from seedoc.routers import auth, health, staff
from seedoc.security.csrf import csrf_middleware

API_PREFIX = "/api/v1"
REQUEST_ID_HEADER = "X-Request-ID"

log = structlog.get_logger()


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


def _generate_operation_id(route: APIRoute) -> str:
    # operation_id = router function name (NAMING §5)
    return route.name


def _error_response(error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content=error.to_body())


# Starlette types every handler as (Request, Exception); each one is registered for exactly one class below.
async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    return _error_response(cast(AppError, exc))


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    errors = cast(RequestValidationError, exc).errors()
    fields = [{"loc": list(err["loc"]), "type": err["type"], "msg": err["msg"]} for err in errors]
    return _error_response(AppError(ErrorCode.VALIDATION_FAILED, details={"fields": fields}))


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    # Unknown paths and wrong methods look like "not found"; nothing else should reach here.
    status_code = cast(StarletteHTTPException, exc).status_code
    code = ErrorCode.NOT_FOUND if status_code in (404, 405) else ErrorCode.INTERNAL_ERROR
    return _error_response(AppError(code))


async def _handle_db_error(request: Request, exc: Exception) -> JSONResponse:
    # Immutability triggers raise these messages (DATA_MODEL §4).
    message = str(getattr(exc, "orig", exc))
    for code in (ErrorCode.RELEASE_IMMUTABLE, ErrorCode.DOCUMENT_IN_RELEASE):
        if code.value in message:
            return _error_response(AppError(code))
    return await _handle_unexpected_error(request, exc)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", path=request.url.path, error=type(exc).__name__)
    message = "internal error" if get_settings().is_production else f"{type(exc).__name__}: {exc}"
    return _error_response(AppError(ErrorCode.INTERNAL_ERROR, message=message))


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncGenerator[None]:
    yield
    await send_pending_mail()
    await dispose_engines()


def create_app() -> FastAPI:
    settings = get_settings()
    _configure_logging()

    app = FastAPI(
        title="SeeDoc API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None if settings.is_production else f"{API_PREFIX}/docs",
        redoc_url=None,
        generate_unique_id_function=_generate_operation_id,
        lifespan=_lifespan,
    )

    # Registered first so it runs inside bind_request_id: CSRF rejections still carry X-Request-ID.
    app.middleware("http")(csrf_middleware)

    @app.middleware("http")
    async def bind_request_id(  # pyright: ignore[reportUnusedFunction]
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(DBAPIError, _handle_db_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(staff.router, prefix=API_PREFIX)
    return app
