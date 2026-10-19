"""jobs

The Procrastinate job queue (ARCHITECTURE §11): its tables, types, functions and triggers, from the schema file of
the pinned Procrastinate version (`migrations/sql/procrastinate-<version>.sql`, copied unchanged from the package).
A later Procrastinate upgrade gets its own migration that runs the package's migration files for that step.

The worker connects as `seedoc_admin` (default privileges on every table). The API only defers jobs as `seedoc_app`.
The queue holds no tenant data besides ids in job arguments, so it has no RLS.

Revision ID: 0002a
Revises: 0002
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0002a"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "sql" / "procrastinate-3.10.0.sql"


def upgrade() -> None:
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    # The file is many statements with dollar-quoted function bodies; asyncpg's simple-query `execute` runs it as one
    # script (SQLAlchemy's text() would treat `%` and `:name` specially and prepare statement by statement).
    dbapi_connection = op.get_bind().connection.dbapi_connection
    if dbapi_connection is None:
        raise RuntimeError("no database connection")
    dbapi_connection.run_async(  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        lambda connection: connection.execute(schema)  # pyright: ignore[reportUnknownLambdaType, reportUnknownMemberType]
    )

    # Deferring = calling procrastinate_defer_jobs_v1 (security invoker): it inserts the job, a trigger the event.
    op.execute("grant select, insert on procrastinate_jobs to seedoc_app;")
    op.execute("grant insert on procrastinate_events to seedoc_app;")


def downgrade() -> None:
    op.execute("""
do $$
declare
  item record;
begin
  drop table if exists procrastinate_events, procrastinate_periodic_defers, procrastinate_jobs,
    procrastinate_workers cascade;
  for item in
    select p.oid::regprocedure as signature, p.prokind from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname like 'procrastinate\\_%'
  loop
    if item.prokind = 'p' then
      execute format('drop procedure %s', item.signature);
    else
      execute format('drop function %s', item.signature);
    end if;
  end loop;
  for item in
    select t.typname from pg_type t join pg_namespace n on n.oid = t.typnamespace
    where n.nspname = 'public' and t.typname like 'procrastinate\\_%' and t.typtype in ('e', 'c')
  loop
    execute format('drop type %I cascade', item.typname);
  end loop;
end $$;
""")
