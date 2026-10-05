COMPOSE := docker compose -f infra/docker-compose.yml
API := cd apps/api &&

.PHONY: help install up down dev dev-api dev-web migrate seed test test-api test-web lint typecheck gen-api

help:
	@echo "install    install backend (uv) and frontend (pnpm) dependencies"
	@echo "up / down  start / stop postgres, minio, mailpit"
	@echo "dev        api on :8000 and web on :5173 (mailpit UI on :8025)"
	@echo "migrate    alembic upgrade head (as seedoc_owner)"
	@echo "seed       demo tenant, owner and staff user"
	@echo "test       backend + frontend tests"
	@echo "lint       ruff + eslint;  typecheck: pyright + tsc"

install:
	$(API) uv sync
	pnpm install

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

dev:
	$(MAKE) -j2 dev-api dev-web

dev-api:
	$(API) uv run uvicorn seedoc.main:create_app --factory --reload --port 8000

dev-web:
	pnpm --dir apps/web dev

migrate:
	$(API) uv run alembic upgrade head

seed:
	@echo "seed: not implemented yet (ROADMAP M0-A10)"

test: test-api test-web

test-api:
	$(API) uv run pytest

test-web:
	pnpm --dir apps/web test

lint:
	$(API) uv run ruff check . && uv run ruff format --check .
	pnpm --dir apps/web lint

typecheck:
	$(API) uv run pyright
	pnpm --dir apps/web typecheck

gen-api:
	pnpm --dir apps/web gen:api
