"""Operator aggregate."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from seedoc.db.base import Base, pg_enum


class OperatorRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class OperatorOrg(Base):
    __tablename__ = "operator_orgs"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str]
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OperatorMember(Base):
    __tablename__ = "operator_members"

    operator_org_id: Mapped[UUID] = mapped_column(ForeignKey("operator_orgs.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[OperatorRole] = mapped_column(
        pg_enum(OperatorRole, name="operator_role", create_type=False), server_default="member"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
