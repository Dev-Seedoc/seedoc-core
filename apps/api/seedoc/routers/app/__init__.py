"""Manufacturer app routes, all under `/app/tenants/{tenant_id}` (API.md §3). Each resource has its own module with a
`router`; include it below. A user who is not a member of the tenant gets 404 (`require_role`)."""

from uuid import UUID

from fastapi import APIRouter, Depends

from seedoc.routers.app import folders, spaces, uploads


def _tenant_path(tenant_id: UUID) -> None:
    """Declares `{tenant_id}` (a UUID) once for every /app route; `get_ctx` reads it for the membership check."""


router = APIRouter(prefix="/app/tenants/{tenant_id}", dependencies=[Depends(_tenant_path)])
router.include_router(spaces.router)
router.include_router(folders.router)
router.include_router(uploads.router)
