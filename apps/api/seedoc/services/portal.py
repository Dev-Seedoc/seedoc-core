"""Portal links (BUSINESS_RULES §11). The portal API itself comes with M3.

QR target: `https://<primary active domain or APP_HOST>/m/<machine token>` and `/s/<delivery token>` for systems.
Every `portal_url` in a response comes from here, so a tenant domain later changes all of them in one place.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.config import get_settings


async def get_portal_url(db: AsyncSession, tenant_id: UUID, kind: str, token: str) -> str:
    """`kind` = `"machine"` (`/m/`) or `"system"` (`/s/`).

    TODO(H-17): use the tenant's primary active domain from `tenant_domains` when there is one; until that table
    exists every link goes to `APP_HOST` (`db` and `tenant_id` are already taken so callers need not change).
    """
    del db, tenant_id
    prefix = "m" if kind == "machine" else "s"
    return f"https://{get_settings().app_host}/{prefix}/{token}"
