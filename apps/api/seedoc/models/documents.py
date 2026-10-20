"""Document library aggregate (DATA_MODEL §3 "Documents")."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, Computed, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from seedoc.db.base import Base, pg_enum
from seedoc.db.types import RegConfig, Vector

EMBEDDING_DIMENSIONS = 1536


class AccessLevel(StrEnum):
    PUBLIC = "public"
    CUSTOMER = "customer"
    INTERNAL = "internal"


class DocType(StrEnum):
    OPERATING_MANUAL = "operating_manual"
    INSTALLATION_MANUAL = "installation_manual"
    MAINTENANCE_MANUAL = "maintenance_manual"
    SAFETY_INSTRUCTION = "safety_instruction"
    DATASHEET = "datasheet"
    SPARE_PARTS_LIST = "spare_parts_list"
    WIRING_DIAGRAM = "wiring_diagram"
    DECLARATION_OF_CONFORMITY = "declaration_of_conformity"
    CERTIFICATE = "certificate"
    TEST_REPORT = "test_report"
    TRAINING_MATERIAL = "training_material"
    OTHER = "other"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Space(Base):
    __tablename__ = "spaces"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (UniqueConstraint("space_id", "parent_id", "name", postgresql_nulls_not_distinct=True),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    space_id: Mapped[UUID] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("folders.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str]
    sort_order: Mapped[int] = mapped_column(server_default="0")
    default_access_level: Mapped[AccessLevel] = mapped_column(
        pg_enum(AccessLevel, name="access_level", create_type=False), server_default="public"
    )
    default_doc_type: Mapped[DocType | None] = mapped_column(pg_enum(DocType, name="doc_type", create_type=False))
    default_language: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str]  # tenants/{tenant_id}/uploads/{id}
    file_name: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[bytes]
    content_type: Mapped[str]
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]  # 15 min to upload, 24 h to consume
    consumed_at: Mapped[datetime | None]


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[UUID] = mapped_column(ForeignKey("folders.id"), index=True)
    group_id: Mapped[UUID] = mapped_column(server_default=func.gen_random_uuid(), index=True)  # language variants
    machine_id: Mapped[UUID | None] = mapped_column(ForeignKey("machines.id"), index=True)  # machine-specific
    title: Mapped[str]
    doc_type: Mapped[DocType] = mapped_column(pg_enum(DocType, name="doc_type", create_type=False))
    language: Mapped[str]
    access_level: Mapped[AccessLevel] = mapped_column(pg_enum(AccessLevel, name="access_level", create_type=False))
    # Deferrable: a document and its first version are inserted in one transaction.
    current_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("document_versions.id", deferrable=True, initially="DEFERRED", use_alter=True), index=True
    )
    trashed_at: Mapped[datetime | None]
    trashed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class DocumentVersion(Base):
    """Immutable except the processing columns (trigger `trg_document_versions_immutable`, DATA_MODEL §4)."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_no"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), index=True)
    version_no: Mapped[int]
    storage_key: Mapped[str]  # tenants/{tenant_id}/versions/{id}.pdf
    file_name: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[bytes]
    page_count: Mapped[int | None]
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        pg_enum(ProcessingStatus, name="processing_status", create_type=False), server_default="pending"
    )
    processing_error: Mapped[str | None]
    processed_at: Mapped[datetime | None]
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TextChunk(Base):
    __tablename__ = "text_chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "chunk_index"),
        Index(
            "ix_text_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_text_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    page_no: Mapped[int]
    chunk_index: Mapped[int]
    heading: Mapped[str | None]
    content: Mapped[str]
    ts_config: Mapped[str] = mapped_column(RegConfig())  # ts_config_for_language(document.language)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, Computed("to_tsvector(ts_config, content)", persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
