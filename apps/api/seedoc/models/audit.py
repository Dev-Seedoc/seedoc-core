"""Audit aggregate."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from seedoc.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_tenant_id_created_at", "tenant_id", text("created_at DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID | None] = mapped_column(ForeignKey("tenants.id"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    entity: Mapped[str]
    entity_id: Mapped[UUID | None]
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    ip_hash: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
