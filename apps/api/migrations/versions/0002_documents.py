# pyright: reportUnknownArgumentType=false
# ^ Alembic's op.create_table() calls pass postgresql.ENUM columns pyright cannot type.
"""documents

Spaces, folders, uploads, documents, document versions and text chunks (DATA_MODEL §3 "Documents"), with RLS,
`ts_config_for_language` and the UPDATE part of the version guard (DATA_MODEL §4). The DELETE part of the guard
needs the release tables and comes with 0004; `fk_documents_machine_id_machines` comes with 0003.

Revision ID: 0002
Revises: 0001
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from seedoc.db.types import RegConfig, Vector

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("spaces", "folders", "uploads", "documents", "document_versions", "text_chunks")

ACCESS_LEVEL = postgresql.ENUM("public", "customer", "internal", name="access_level", create_type=False)
DOC_TYPE = postgresql.ENUM(
    "operating_manual",
    "installation_manual",
    "maintenance_manual",
    "safety_instruction",
    "datasheet",
    "spare_parts_list",
    "wiring_diagram",
    "declaration_of_conformity",
    "certificate",
    "test_report",
    "training_material",
    "other",
    name="doc_type",
    create_type=False,
)
PROCESSING_STATUS = postgresql.ENUM(
    "pending", "processing", "ready", "failed", name="processing_status", create_type=False
)


def _uuid_pk() -> "sa.Column[uuid.UUID]":
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant_id(table: str) -> "sa.Column[uuid.UUID]":
    return sa.Column(
        "tenant_id",
        sa.Uuid(),
        sa.ForeignKey("tenants.id", name=f"fk_{table}_tenant_id_tenants", ondelete="CASCADE"),
        nullable=False,
    )


def _created_at() -> "sa.Column[datetime]":
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _index(table: str, *columns: str) -> None:
    op.create_index(f"ix_{table}_{'_'.join(columns)}", table, list(columns))


def upgrade() -> None:
    op.execute("create type access_level as enum ('public', 'customer', 'internal');")
    op.execute(
        "create type doc_type as enum ("
        "'operating_manual', 'installation_manual', 'maintenance_manual', 'safety_instruction', "
        "'datasheet', 'spare_parts_list', 'wiring_diagram', 'declaration_of_conformity', "
        "'certificate', 'test_report', 'training_material', 'other');"
    )
    op.execute("create type processing_status as enum ('pending', 'processing', 'ready', 'failed');")

    op.create_table(
        "spaces",
        _uuid_pk(),
        _tenant_id("spaces"),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_spaces"),
    )
    _index("spaces", "tenant_id")

    op.create_table(
        "folders",
        _uuid_pk(),
        _tenant_id("folders"),
        sa.Column(
            "space_id",
            sa.Uuid(),
            sa.ForeignKey("spaces.id", name="fk_folders_space_id_spaces", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.Uuid(),
            sa.ForeignKey("folders.id", name="fk_folders_parent_id_folders", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("default_access_level", ACCESS_LEVEL, server_default="public", nullable=False),
        sa.Column("default_doc_type", DOC_TYPE, nullable=True),
        sa.Column("default_language", sa.Text(), nullable=True),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_folders"),
        # A root folder has parent_id null; without NULLS NOT DISTINCT two roots could share a name.
        sa.UniqueConstraint(
            "space_id",
            "parent_id",
            "name",
            name="uq_folders_space_id_parent_id_name",
            postgresql_nulls_not_distinct=True,
        ),
    )
    _index("folders", "tenant_id")
    _index("folders", "space_id")
    _index("folders", "parent_id")

    op.create_table(
        "uploads",
        _uuid_pk(),
        _tenant_id("uploads"),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", name="fk_uploads_created_by_users"), nullable=True
        ),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_uploads"),
    )
    _index("uploads", "tenant_id")
    _index("uploads", "created_by")

    op.create_table(
        "documents",
        _uuid_pk(),
        _tenant_id("documents"),
        sa.Column(
            "folder_id", sa.Uuid(), sa.ForeignKey("folders.id", name="fk_documents_folder_id_folders"), nullable=False
        ),
        sa.Column("group_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("machine_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("doc_type", DOC_TYPE, nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("access_level", ACCESS_LEVEL, nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "trashed_by", sa.Uuid(), sa.ForeignKey("users.id", name="fk_documents_trashed_by_users"), nullable=True
        ),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", name="fk_documents_created_by_users"), nullable=True
        ),
        _created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    for column in (
        "tenant_id",
        "folder_id",
        "group_id",
        "machine_id",
        "current_version_id",
        "trashed_by",
        "created_by",
    ):
        _index("documents", column)

    op.create_table(
        "document_versions",
        _uuid_pk(),
        _tenant_id("document_versions"),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", name="fk_document_versions_document_id_documents", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.LargeBinary(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("processing_status", PROCESSING_STATUS, server_default="pending", nullable=False),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_document_versions_created_by_users"),
            nullable=True,
        ),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint("document_id", "version_no", name="uq_document_versions_document_id_version_no"),
    )
    for column in ("tenant_id", "document_id", "created_by"):
        _index("document_versions", column)
    # A document and its first version are inserted in one transaction, so the check waits for the commit.
    op.execute(
        "alter table documents add constraint fk_documents_current_version_id_document_versions "
        "foreign key (current_version_id) references document_versions deferrable initially deferred;"
    )

    op.execute("""
create or replace function ts_config_for_language(lang text) returns regconfig
language sql immutable as $$
  select case lang
    when 'de' then 'german' when 'en' then 'english' when 'fr' then 'french'
    when 'es' then 'spanish' when 'it' then 'italian' when 'nl' then 'dutch'
    when 'pt' then 'portuguese' when 'sv' then 'swedish' when 'da' then 'danish'
    when 'fi' then 'finnish' when 'nb' then 'norwegian' when 'hu' then 'hungarian'
    when 'ro' then 'romanian' when 'ru' then 'russian' when 'tr' then 'turkish'
    else 'simple' end::regconfig $$;
""")

    op.create_table(
        "text_chunks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        _tenant_id("text_chunks"),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey(
                "document_versions.id", name="fk_text_chunks_version_id_document_versions", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("ts_config", RegConfig(), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed("to_tsvector(ts_config, content)", persisted=True)),
        sa.Column("embedding", Vector(1536), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_text_chunks"),
        sa.UniqueConstraint("version_id", "chunk_index", name="uq_text_chunks_version_id_chunk_index"),
    )
    _index("text_chunks", "tenant_id")
    _index("text_chunks", "version_id")
    op.execute("create index ix_text_chunks_embedding on text_chunks using hnsw (embedding vector_cosine_ops);")
    op.execute("create index ix_text_chunks_tsv on text_chunks using gin (tsv);")

    # Immutability (DATA_MODEL §4): only the processing columns of a version may change. 0004 replaces this function
    # with the full version that also refuses to DELETE a version used in a release.
    op.execute("""
create or replace function guard_document_version_update() returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and (to_jsonb(new) - '{processing_status,processing_error,processed_at,page_count}'::text[])
       is distinct from (to_jsonb(old) - '{processing_status,processing_error,processed_at,page_count}'::text[]) then
    raise exception 'release_immutable: document version fields are immutable' using errcode = 'P0001';
  end if;
  return coalesce(new, old);
end $$;
""")
    op.execute(
        "create trigger trg_document_versions_immutable before update or delete on document_versions "
        "for each row execute function guard_document_version_update();"
    )

    # Row-level security (DATA_MODEL §5)
    for table in TENANT_TABLES:
        op.execute(f"alter table {table} enable row level security;")
        op.execute(f"alter table {table} force row level security;")
        op.execute(
            f"create policy p_{table}_tenant on {table} "
            "using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
            "with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);"
        )
        op.execute(f"grant select, insert, update, delete on {table} to seedoc_app;")


def downgrade() -> None:
    op.execute("drop trigger if exists trg_document_versions_immutable on document_versions;")
    op.execute("drop function if exists guard_document_version_update;")
    op.execute("alter table documents drop constraint fk_documents_current_version_id_document_versions;")
    op.drop_table("text_chunks")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("uploads")
    op.drop_table("folders")
    op.drop_table("spaces")
    op.execute("drop function if exists ts_config_for_language;")
    op.execute("drop type if exists processing_status;")
    op.execute("drop type if exists doc_type;")
    op.execute("drop type if exists access_level;")
