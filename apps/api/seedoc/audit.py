"""Audit logging (BUSINESS_RULES §9, action names NAMING §12)."""

from typing import Any
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from seedoc.deps import RequestContext
from seedoc.models.audit import AuditEvent


async def write_audit_event(
    db: AsyncSession,
    ctx: RequestContext,
    action: str,
    entity: str,
    entity_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
    *,
    tenant_id: UUID | None = None,
    actor_id: UUID | None = None,
) -> None:
    """Record an audit event in the caller's transaction.

    `tenant_id` / `actor_id` default to the request context; pass them when the service knows better (e.g. the
    invitation's tenant, or the user who just logged in). Events without a tenant are global (`p_audit_events_global`).
    `detail` holds ids and changed field names only — never secrets, tokens, PINs or document text.
    """
    # Plain INSERT without RETURNING: a global event (tenant_id null) is insert-only for seedoc_app, and Postgres
    # applies the select policy to RETURNING rows, so the ORM's `RETURNING id` would be rejected.
    await db.execute(
        insert(AuditEvent)
        .inline()  # no implicit RETURNING of the primary key
        .values(
            tenant_id=tenant_id or ctx.tenant_id,
            actor_id=actor_id or ctx.user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail or {},
            ip_hash=ctx.ip_hash,
        )
    )
