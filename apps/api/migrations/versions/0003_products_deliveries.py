# pyright: reportUnknownArgumentType=false
# ^ Alembic's op.create_table() calls pass postgresql.ENUM / ARRAY columns pyright cannot type.
"""products_deliveries

Products with their document sets and releases, customers, deliveries and machines (DATA_MODEL §3 "Products",
"Customers, deliveries, machines"), with RLS, the immutability trigger of the two product release tables
(DATA_MODEL §4) and the foreign keys 0001/0002 left open: `fk_documents_machine_id_machines`,
`fk_invitations_customer_id_customers`.

Revision ID: 0003
Revises: 0002a
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Product releases are written once (insert + read); the trigger refuses UPDATE / DELETE for every role anyway.
WRITABLE_TABLES = ("products", "product_documents", "customers", "deliveries", "machines")
RELEASE_TABLES = ("product_releases", "product_release_items")

ACCESS_LEVEL = postgresql.ENUM("public", "customer", "internal", name="access_level", create_type=False)
DOC_TYPE = postgresql.ENUM(name="doc_type", create_type=False)
DELIVERY_KIND = postgresql.ENUM("machine", "system", name="delivery_kind", create_type=False)
DELIVERY_STATUS = postgresql.ENUM("draft", "published", "archived", name="delivery_status", create_type=False)


def _uuid_pk() -> "sa.Column[uuid.UUID]":
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant_id(table: str) -> "sa.Column[uuid.UUID]":
    return sa.Column(
        "tenant_id",
        sa.Uuid(),
        sa.ForeignKey("tenants.id", name=f"fk_{table}_tenant_id_tenants", ondelete="CASCADE"),
        nullable=False,
    )


def _fk(
    table: str, column: str, target: str, *, nullable: bool = False, ondelete: str | None = None
) -> sa.Column[uuid.UUID]:
    return sa.Column(
        column,
        sa.Uuid(),
        sa.ForeignKey(f"{target}.id", name=f"fk_{table}_{column}_{target}", ondelete=ondelete),
        nullable=nullable,
    )


def _timestamp(name: str, *, default_now: bool = True) -> "sa.Column[datetime]":
    if default_now:
        return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _languages() -> "sa.Column[list[str]]":
    return sa.Column("required_languages", postgresql.ARRAY(sa.Text()), server_default="{de}", nullable=False)


def _index(table: str, *columns: str) -> None:
    op.create_index(f"ix_{table}_{'_'.join(columns)}", table, list(columns))


def upgrade() -> None:
    op.execute("create type delivery_kind as enum ('machine', 'system');")
    op.execute("create type delivery_status as enum ('draft', 'published', 'archived');")

    # ───────────── Products ─────────────
    op.create_table(
        "products",
        _uuid_pk(),
        _tenant_id("products"),
        _fk("products", "space_id", "spaces", nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        _languages(),
        _timestamp("archived_at", default_now=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
    )
    for column in ("tenant_id", "space_id"):
        _index("products", column)

    op.create_table(
        "product_documents",
        _tenant_id("product_documents"),
        _fk("product_documents", "product_id", "products", ondelete="CASCADE"),
        _fk("product_documents", "document_id", "documents", ondelete="CASCADE"),
        _fk("product_documents", "added_by", "users", nullable=True),
        _timestamp("added_at"),
        sa.PrimaryKeyConstraint("product_id", "document_id", name="pk_product_documents"),
    )
    for column in ("tenant_id", "document_id", "added_by"):
        _index("product_documents", column)

    op.create_table(
        "product_releases",
        _uuid_pk(),
        _tenant_id("product_releases"),
        _fk("product_releases", "product_id", "products"),
        sa.Column("release_no", sa.Integer(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        _fk("product_releases", "created_by", "users", nullable=True),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name="pk_product_releases"),
        sa.UniqueConstraint("product_id", "release_no", name="uq_product_releases_product_id_release_no"),
    )
    for column in ("tenant_id", "created_by"):
        _index("product_releases", column)

    op.create_table(
        "product_release_items",
        _uuid_pk(),
        _tenant_id("product_release_items"),
        _fk("product_release_items", "release_id", "product_releases"),
        _fk("product_release_items", "document_id", "documents"),
        _fk("product_release_items", "version_id", "document_versions"),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("doc_type", DOC_TYPE, nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("access_level", ACCESS_LEVEL, nullable=False),
        sa.Column("folder_path", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_product_release_items"),
        sa.UniqueConstraint("release_id", "version_id", name="uq_product_release_items_release_id_version_id"),
    )
    for column in ("tenant_id", "document_id", "version_id"):
        _index("product_release_items", column)

    # ───────────── Customers, deliveries, machines ─────────────
    op.create_table(
        "customers",
        _uuid_pk(),
        _tenant_id("customers"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=True),
        sa.Column("contact_email", postgresql.CITEXT(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
    )
    _index("customers", "tenant_id")
    op.execute(
        "alter table invitations add constraint fk_invitations_customer_id_customers "
        "foreign key (customer_id) references customers;"
    )
    _index("invitations", "customer_id")

    op.create_table(
        "deliveries",
        _uuid_pk(),
        _tenant_id("deliveries"),
        _fk("deliveries", "customer_id", "customers"),
        sa.Column("kind", DELIVERY_KIND, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("order_no", sa.Text(), nullable=True),
        _languages(),
        sa.Column("status", DELIVERY_STATUS, server_default="draft", nullable=False),
        sa.Column("public_token", sa.Text(), nullable=False),  # system QR, 32 random bytes base64url
        _fk("deliveries", "created_by", "users", nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_deliveries"),
        sa.UniqueConstraint("public_token", name="uq_deliveries_public_token"),
    )
    for column in ("tenant_id", "customer_id", "created_by"):
        _index("deliveries", column)

    op.create_table(
        "machines",
        _uuid_pk(),
        _tenant_id("machines"),
        _fk("machines", "delivery_id", "deliveries"),
        _fk("machines", "product_id", "products"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("serial_no", sa.Text(), nullable=False),
        sa.Column("public_token", sa.Text(), nullable=False),  # machine QR
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        _timestamp("first_published_at", default_now=False),  # billing fact, set once
        _timestamp("archived_at", default_now=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.PrimaryKeyConstraint("id", name="pk_machines"),
        sa.UniqueConstraint("public_token", name="uq_machines_public_token"),
        sa.UniqueConstraint("tenant_id", "serial_no", name="uq_machines_tenant_id_serial_no"),
    )
    for column in ("delivery_id", "product_id"):
        _index("machines", column)
    op.execute(
        "alter table documents add constraint fk_documents_machine_id_machines "
        "foreign key (machine_id) references machines;"
    )

    # Immutability (DATA_MODEL §4): a product release and its items never change once written.
    op.execute("""
create or replace function forbid_mutation() returns trigger language plpgsql as $$
begin
  raise exception 'release_immutable: % on % is not allowed', tg_op, tg_table_name
    using errcode = 'P0001';
end $$;
""")
    for table in RELEASE_TABLES:
        op.execute(
            f"create trigger trg_{table}_immutable before update or delete on {table} "
            "for each row execute function forbid_mutation();"
        )

    # Row-level security (DATA_MODEL §5)
    for table in (*WRITABLE_TABLES, *RELEASE_TABLES):
        op.execute(f"alter table {table} enable row level security;")
        op.execute(f"alter table {table} force row level security;")
        op.execute(
            f"create policy p_{table}_tenant on {table} "
            "using (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid) "
            "with check (tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid);"
        )
    for table in WRITABLE_TABLES:
        op.execute(f"grant select, insert, update, delete on {table} to seedoc_app;")
    for table in RELEASE_TABLES:
        op.execute(f"grant select, insert on {table} to seedoc_app;")


def downgrade() -> None:
    op.execute("alter table documents drop constraint fk_documents_machine_id_machines;")
    op.drop_table("machines")
    op.drop_table("deliveries")
    op.drop_index("ix_invitations_customer_id", table_name="invitations")
    op.execute("alter table invitations drop constraint fk_invitations_customer_id_customers;")
    op.drop_table("customers")
    for table in RELEASE_TABLES:
        op.execute(f"drop trigger if exists trg_{table}_immutable on {table};")
    op.drop_table("product_release_items")
    op.drop_table("product_releases")
    op.drop_table("product_documents")
    op.drop_table("products")
    op.execute("drop function if exists forbid_mutation;")
    op.execute("drop type if exists delivery_status;")
    op.execute("drop type if exists delivery_kind;")
