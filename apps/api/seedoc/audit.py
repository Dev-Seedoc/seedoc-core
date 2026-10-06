"""Audit logging."""

from typing import Any
from uuid import UUID

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
) -> None:
    """Record an audit event."""
    event = AuditEvent(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail or {},
        ip_hash=ctx.ip_hash,
    )
    db.add(event)
