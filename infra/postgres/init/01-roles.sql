-- Local/CI database bootstrap (DATA_MODEL §5). Runs once as the superuser on a fresh volume.
-- Staging/production create the same roles with real passwords from the password manager.
--   seedoc_owner : owns all objects, runs migrations. BYPASSRLS so the SECURITY DEFINER functions it owns
--                  (member_tenants, resolve_public_token, ...) can read across tenants; the API never connects as it.
--   seedoc_app   : API for /auth, /app, /portal, /operator — RLS enforced (no BYPASSRLS, owns nothing)
--   seedoc_admin : BYPASSRLS — staff routes and worker jobs only

create role seedoc_owner login password 'seedoc_owner' bypassrls;
create role seedoc_app login password 'seedoc_app';
create role seedoc_admin login password 'seedoc_admin' bypassrls;

do $$ begin
  execute format('alter database %I owner to seedoc_owner', current_database());
  execute format('grant connect on database %I to seedoc_app, seedoc_admin', current_database());
end $$;

alter schema public owner to seedoc_owner;
grant usage on schema public to seedoc_app, seedoc_admin;

-- Extensions need the superuser; tables are created later by seedoc_owner through Alembic.
create extension if not exists vector;
create extension if not exists pgcrypto;
create extension if not exists citext;

-- seedoc_admin may touch every table seedoc_owner creates. seedoc_app grants are per table in each migration.
alter default privileges for role seedoc_owner in schema public
  grant select, insert, update, delete on tables to seedoc_admin;
alter default privileges for role seedoc_owner in schema public
  grant usage, select on sequences to seedoc_app, seedoc_admin;
