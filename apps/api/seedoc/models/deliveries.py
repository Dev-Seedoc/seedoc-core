"""Customers, deliveries and machines (DATA_MODEL §3 "Customers, deliveries, machines"). `public_token` is the QR
token of a machine (`/m/{token}`) or of a system delivery (`/s/{token}`): a permanent contract, never changed."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from seedoc.db.base import Base, pg_enum


class DeliveryKind(StrEnum):
    MACHINE = "machine"  # exactly one machine
    SYSTEM = "system"  # several machines, plus the system QR


class DeliveryStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    contact_name: Mapped[str | None]
    contact_email: Mapped[str | None] = mapped_column(CITEXT)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    kind: Mapped[DeliveryKind] = mapped_column(pg_enum(DeliveryKind, name="delivery_kind", create_type=False))
    name: Mapped[str]
    order_no: Mapped[str | None]
    required_languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{de}")
    status: Mapped[DeliveryStatus] = mapped_column(
        pg_enum(DeliveryStatus, name="delivery_status", create_type=False), server_default="draft"
    )
    public_token: Mapped[str] = mapped_column(unique=True)  # system QR
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Machine(Base):
    __tablename__ = "machines"
    __table_args__ = (UniqueConstraint("tenant_id", "serial_no"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey("deliveries.id"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), index=True)
    name: Mapped[str]
    serial_no: Mapped[str]
    public_token: Mapped[str] = mapped_column(unique=True)  # machine QR
    sort_order: Mapped[int] = mapped_column(server_default="0")
    first_published_at: Mapped[datetime | None]  # billing fact, set once
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
