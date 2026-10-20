"""Products, their document sets and product releases (DATA_MODEL §3 "Products"). Product releases and their items
are immutable (trigger `forbid_mutation`, DATA_MODEL §4)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from seedoc.db.base import Base, pg_enum
from seedoc.models.documents import AccessLevel, DocType


class Product(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    space_id: Mapped[UUID | None] = mapped_column(ForeignKey("spaces.id"), index=True)
    name: Mapped[str]
    required_languages: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{de}")
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ProductDocument(Base):
    """One document of a product's document set (what the next product release freezes)."""

    __tablename__ = "product_documents"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    added_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProductRelease(Base):
    __tablename__ = "product_releases"
    __table_args__ = (UniqueConstraint("product_id", "release_no"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    release_no: Mapped[int]
    change_note: Mapped[str | None]
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProductReleaseItem(Base):
    """One frozen document version of a product release, with the document's metadata at release time."""

    __tablename__ = "product_release_items"
    __table_args__ = (UniqueConstraint("release_id", "version_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    release_id: Mapped[UUID] = mapped_column(ForeignKey("product_releases.id"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id"), index=True)
    group_id: Mapped[UUID]
    title: Mapped[str]
    doc_type: Mapped[DocType] = mapped_column(pg_enum(DocType, name="doc_type", create_type=False))
    language: Mapped[str]
    access_level: Mapped[AccessLevel] = mapped_column(pg_enum(AccessLevel, name="access_level", create_type=False))
    folder_path: Mapped[str]
