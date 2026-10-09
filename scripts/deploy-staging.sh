#!/usr/bin/env bash
# Deploy the current checkout to staging (ROADMAP M0-A9). Used by CI on every push to main, and by hand:
#   bash scripts/deploy-staging.sh                 # build both images locally, then deploy
#   bash scripts/deploy-staging.sh --no-build      # images seedoc-api:staging / seedoc-web:staging already built
# Env: STAGING_SSH (default deploy@staging.seedoc.cloud). Needs Docker locally and SSH access as `deploy`.
# Steps: build → copy images (docker save | ssh docker load) and the compose files → migrate → restart → health check.
set -euo pipefail

SSH_TARGET=${STAGING_SSH:-deploy@staging.seedoc.cloud}
APP_DIR=/opt/seedoc
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [ "${1:-}" != "--no-build" ]; then
  echo "== build images"
  docker build --platform linux/amd64 -t seedoc-api:staging apps/api
  docker build --platform linux/amd64 -t seedoc-web:staging -f apps/web/Dockerfile .
fi

ssh_run() { ssh -o BatchMode=yes "$SSH_TARGET" "$@"; }

echo "== upload images to $SSH_TARGET"
docker save seedoc-api:staging seedoc-web:staging | gzip -1 | ssh_run 'gunzip | docker load'

echo "== upload compose files"
tar -c -C infra/staging compose.yml Caddyfile postgres-init -C "$ROOT/infra/postgres/init" 01-roles.sql \
  | ssh_run "set -e; cd $APP_DIR; mkdir -p postgres-init; tar -x --no-same-owner; mv -f 01-roles.sql postgres-init/; \
             sed -i 's/\r\$//' postgres-init/* Caddyfile compose.yml; chmod 755 postgres-init/*.sh"

echo "== migrate and restart"
ssh_run "set -e; cd $APP_DIR
  if grep -q FILL_IN .env; then echo 'WARNING: .env still has FILL_IN values (S3 / mail) — see README §15'; fi
  docker compose up -d --wait postgres
  docker compose run --rm migrate
  docker compose up -d --remove-orphans api web
  docker image prune -f >/dev/null"

echo "== health check"
for _ in $(seq 1 30); do
  if ssh_run "cd $APP_DIR && docker compose exec -T api python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')\"" 2>/dev/null; then
    echo "staging is up: https://staging.seedoc.cloud"
    exit 0
  fi
  sleep 2
done
echo "ERROR: API health check failed — logs: ssh $SSH_TARGET 'cd $APP_DIR && docker compose logs --tail 100 api'" >&2
exit 1
