"""Tenant aggregate."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from seedoc.db.base import Base, pg_enum


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"


class TenantStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class InvitationKind(StrEnum):
    TENANT_MEMBER = "tenant_member"
    OPERATOR = "operator"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    status: Mapped[TenantStatus] = mapped_column(
        pg_enum(TenantStatus, name="tenant_status", create_type=False), server_default="active"
    )
    brand_color: Mapped[str | None]
    brand_logo_key: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TenantMember(Base):
    __tablename__ = "tenant_members"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    role: Mapped[MemberRole] = mapped_column(pg_enum(MemberRole, name="member_role", create_type=False))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'tenant_member' AND role IS NOT NULL AND operator_org_id IS NULL) OR "
            "(kind = 'operator' AND role IS NULL AND operator_org_id IS NOT NULL AND customer_id IS NOT NULL)",
            name="kind_fields",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    kind: Mapped[InvitationKind] = mapped_column(pg_enum(InvitationKind, name="invitation_kind", create_type=False))
    email: Mapped[str] = mapped_column(CITEXT)
    role: Mapped[MemberRole | None] = mapped_column(pg_enum(MemberRole, name="member_role", create_type=False))
    customer_id: Mapped[UUID | None]  # FK added later in M2
    operator_org_id: Mapped[UUID | None] = mapped_column(ForeignKey("operator_orgs.id"))
    token_hash: Mapped[bytes] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    accepted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None]
    invited_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
