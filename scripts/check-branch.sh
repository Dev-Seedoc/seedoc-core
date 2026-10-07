#!/usr/bin/env bash
# Test a developer branch exactly as it is on GitHub, before it is merged into main.
#
#   scripts/check-branch.sh DevArea-Jamshid      (or: make check-branch BRANCH=DevArea-Jamshid)
#
# Checks out origin/<branch> in a throw-away worktree (your own checkout is not touched), reports whether main can
# be fast-forwarded to it, and runs every CI check for api and web. Docker must be running, otherwise the database
# tests would only be skipped. Exit code 0 = safe to merge.
set -euo pipefail

branch="${1:?usage: scripts/check-branch.sh <branch>}"
root="$(git rev-parse --show-toplevel)"
ref="origin/${branch}"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running — start Docker Desktop first (database tests would be skipped)." >&2
  exit 1
fi

git -C "$root" fetch origin --prune --quiet
git -C "$root" rev-parse --verify --quiet "$ref" >/dev/null || { echo "No such branch: $ref" >&2; exit 1; }

dir="$(mktemp -d)/seedoc-check"
cleanup() {
  rm -rf "$dir"
  git -C "$root" worktree prune
}
trap cleanup EXIT
git -C "$root" worktree add --quiet --detach "$dir" "$ref"

echo "== Checking ${ref}: $(git -C "$dir" log --oneline -1)"
echo "   Commits not on main yet:"
git -C "$root" log --oneline "origin/main..${ref}" | sed 's/^/     /'
if git -C "$root" merge-base --is-ancestor origin/main "$ref"; then
  echo "   main can be fast-forwarded to this branch."
else
  echo "   main has commits this branch lacks: the branch owner must merge main into the branch first." >&2
  exit 1
fi

cd "$dir"
echo "== Install"
pnpm install --frozen-lockfile --silent
(cd apps/api && uv sync --frozen --quiet)

echo "== API: ruff, format, pyright, pytest"
(cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q -p no:cacheprovider)

echo "== Web: lint, format, typecheck, test, build"
(cd apps/web && pnpm -s lint && pnpm -s format:check && pnpm -s typecheck && pnpm -s test && pnpm -s build)

echo ""
echo "ALL CHECKS PASSED for ${ref} — safe to merge into main."
