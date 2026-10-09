#!/usr/bin/env bash
# Staging/production only: replace the local passwords set by 01-roles.sql with the ones from .env.
# Runs once, as the superuser, on a fresh volume (docker-entrypoint-initdb.d), right after 01-roles.sql.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_pw="$SEEDOC_OWNER_PASSWORD" -v app_pw="$SEEDOC_APP_PASSWORD" -v admin_pw="$SEEDOC_ADMIN_PASSWORD" <<'SQL'
alter role seedoc_owner password :'owner_pw';
alter role seedoc_app password :'app_pw';
alter role seedoc_admin password :'admin_pw';
SQL
echo "seedoc role passwords set from .env"
