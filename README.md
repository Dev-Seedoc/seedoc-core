# SeeDoc

Permanent QR-code documentation portals for industrial machines, with an AI assistant that answers **only** from
the delivered documents and cites the page.

**Status:** rebuild from scratch. Plan started Monday 5 October 2026; pilot deadline **Friday 29 January 2027**.

> This README summarises the full technical contract: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/NAMING.md`,
> `docs/API.md`, `docs/DATA_MODEL.md`, `docs/BUSINESS_RULES.md`, `docs/WORK_PLAN.md`, `docs/ROADMAP.md`,
> `docs/HANDOVER.md` and `.env.example`. Where it differs from those files, they take precedence.

**New developer?** Go to [14. Local development](#14-local-development): what to install, how to set up, and how
to check that everything runs.

---

## Contents

1. [What SeeDoc does](#1-what-seedoc-does)
2. [Non-negotiable invariants](#2-non-negotiable-invariants)
3. [Rules for developers and AI assistants](#3-rules-for-developers-and-ai-assistants)
4. [Stack](#4-stack)
5. [System overview](#5-system-overview)
6. [Repository layout](#6-repository-layout)
7. [Tenancy, security and authentication](#7-tenancy-security-and-authentication)
8. [Documents and the AI pipeline](#8-documents-and-the-ai-pipeline)
9. [Business rules](#9-business-rules)
10. [Data model](#10-data-model)
11. [API overview](#11-api-overview)
12. [Naming conventions](#12-naming-conventions)
13. [Configuration](#13-configuration)
14. [Local development](#14-local-development)
15. [Testing](#15-testing)
16. [Deployment](#16-deployment)
17. [Team, work split and workflow](#17-team-work-split-and-workflow)
18. [Roadmap](#18-roadmap)
19. [Decision log](#19-decision-log)
20. [The old system](#20-the-old-system)

---

## 1. What SeeDoc does

Each machine a manufacturer ships gets a **permanent QR code**. Scanning it opens exactly the documentation that was
delivered with that machine: frozen, versioned and in the operator's language. An **AI assistant** answers questions
using only those documents.

Lifecycle:

1. The manufacturer uploads documents (PDF) into spaces and folders.
2. It freezes a **product release** (the document set of a machine model).
3. It creates a **delivery** for a customer, either one machine or a system of machines, with a **draft**.
4. It checks completeness and languages, then **publishes** a delivery release.
5. It prints QR labels.
6. The operator scans a label and reads: public documents openly, protected ones with a PIN or an operator account.
7. Later the manufacturer publishes an **update**, which is a new release. The old release is kept.

Business promise every line of code protects: **what a customer sees is always a frozen, traceable version, and one
manufacturer can never see another's data.**

## 2. Non-negotiable invariants

Each one has its own automated test suite.

1. **Tenant isolation.** No query can return another tenant's rows (forced Postgres RLS plus a service-layer filter).
2. **Immutability.** `document_versions`, `product_releases`, `product_release_items`, `delivery_releases` and
   `delivery_release_items` cannot be changed or deleted by any role.
3. **Portal access.** `internal` items never reach the portal. `customer` items need a PIN session or an operator
   grant. Only the **current** delivery release is shown.
4. **Permanent QR URLs.** `/m/{token}` (machine) and `/s/{token}` (system). Tokens never change.
5. **Traceability.** Every customer-visible file points to an immutable version with a SHA-256. Every publish,
   delete, PIN and role change is recorded in `audit_events`.

## 3. Rules for developers and AI assistants

Two developers work in parallel, each with their own AI assistant. Everything must fit together with code you have
never seen, so the written contract is followed **exactly**.

**Read first:** `docs/ARCHITECTURE.md` → `docs/NAMING.md` → `docs/API.md` → `docs/DATA_MODEL.md` →
`docs/BUSINESS_RULES.md`.

**Hard rules**

1. **Never invent a name** for an endpoint, `operation_id`, table, column, enum value, error code, audit action, job,
   env var, route or hook. Look it up in the docs.
2. **Never rename** anything that exists in the docs or code.
3. **Something new is needed?** Add it to the relevant doc first, in the same PR, listed under "Contract changes".
   The other developer must approve it.
4. **Do not build `Later` items** unless the task says so.
5. **Layering is strict:** routers do HTTP only, services hold business logic and transactions. No SQL in routers
   and no HTTP objects in services.
6. **Tenant isolation:** every tenant table has `tenant_id`, RLS policies and an isolation test.
7. **Immutability:** release tables and `document_versions` are never updated or deleted.
8. **`/m/{token}` and `/s/{token}` are a permanent contract.**
9. **UI text is German** (formal "Sie") and always comes from i18n files.
10. **Code, identifiers, comments, commit messages and docs are English.**
11. No new dependency unless it is added to the stack table (contract change).
12. Never commit secrets or `.env`; commit only `.env.example`.

**Definition of done**

- [ ] Names match `NAMING.md` and `API.md` exactly
- [ ] Backend: `ruff check`, `ruff format --check`, `pyright`, `pytest` pass
- [ ] Frontend: `pnpm lint`, `pnpm typecheck`, `pnpm test` pass
- [ ] New tenant table → RLS policy + isolation test (`tests/isolation/`)
- [ ] New endpoint → API tests for happy path, wrong role (403) and other tenant (404)
- [ ] OpenAPI changed → regenerated `apps/web/src/lib/api/schema.d.ts` committed
- [ ] New UI strings in `i18n/de.json` (same key in `en.json`)
- [ ] Audit event written for every auditable action
- [ ] PR title in Conventional Commits format; description says "Contract changes: none" or lists them

**Using an AI assistant on this repo**

- Claude Code reads `CLAUDE.md`, which points to `AGENTS.md`, automatically.
- Codex, Cursor, Copilot, Windsurf and most other agents read `AGENTS.md`; Copilot also reads
  `.github/copilot-instructions.md`.
- For a chat-only AI, paste `AGENTS.md` first, then the docs relevant to the task.

Suggested prompt:

> Read AGENTS.md and the docs it lists. Implement ROADMAP task **M2-B5**. Use only names defined in docs/API.md,
> docs/DATA_MODEL.md and docs/NAMING.md. Follow BUSINESS_RULES §6 exactly. Write the tests required by the
> Definition of Done. If you need a name that is not defined, stop and propose the doc change.

## 4. Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 19, Vite, TypeScript strict, React Router 7 (library mode), TanStack Query 5, TanStack Table 8 |
| UI | Tailwind CSS 4, shadcn/ui (Radix), lucide-react, sonner |
| Forms | React Hook Form + Zod |
| API client | `openapi-typescript` (types) + `openapi-fetch` (calls), generated from FastAPI OpenAPI |
| i18n | react-i18next; `de` shipped, `en` kept in sync |
| PDF viewer | `react-pdf` (pdf.js) with the worker bundled locally (no CDN) |
| QR | `segno` for QR codes, `reportlab` for the A4 label sheet |
| Backend | Python 3.12, FastAPI, Pydantic v2, pydantic-settings |
| DB access | SQLAlchemy 2.0 async (asyncpg), Alembic |
| Database | PostgreSQL 16 + pgvector + full-text search |
| Jobs | Procrastinate (Postgres-backed queue) |
| Storage | S3-compatible (RustFS locally; Hetzner Object Storage or AWS S3 Frankfurt) |
| Auth | Own session auth: Argon2id, opaque session token in an HttpOnly cookie, TOTP for staff |
| PDF text | `pypdfium2` (not PyMuPDF, which is AGPL) |
| AI | Embeddings `text-embedding-3-small` (1536 dims); chat `gpt-4.1-mini` via an EU-processing provider |
| Mail | Resend (EU region, sender domain `mail.seedoc.cloud`) over SMTP; Mailpit locally |
| Hosting | Hetzner Cloud (DE), Docker Compose, Caddy (TLS incl. on-demand TLS for manufacturer domains) |
| Observability | Sentry, structured JSON logs (`structlog`) |
| Tooling | pnpm, uv, Ruff, pyright strict, ESLint + Prettier, Vitest, Playwright, pytest + httpx + testcontainers |

## 5. System overview

```
             ┌──────────────────────────── Browser ────────────────────────────┐
             │  Manufacturer app (/…)   Portal (/m, /s)   Operator (/operator)  │
             │  Staff console (/staff)          one React build                 │
             └───────────────────────────────┬─────────────────────────────────┘
                                             │ HTTPS
                                   ┌─────────▼─────────┐
                                   │       Caddy       │  TLS, serves web build,
                                   │                   │  proxies /api → api:8000
                                   └─────────┬─────────┘
                        ┌────────────────────▼────────────────────┐
                        │            FastAPI  (apps/api)          │
                        │  routers → services → models (SQLA)     │
                        └──┬──────────────┬──────────────┬────────┘
                 ┌─────────▼───┐   ┌──────▼──────┐  ┌────▼─────────────┐
                 │ PostgreSQL  │   │ Object store│  │ AI provider      │
                 │ RLS, vector,│   │ (private)   │  │ embeddings, chat │
                 │ FTS, jobs   │   └──────▲──────┘  └────▲─────────────┘
                 └─────────▲───┘   ┌──────┴──────────────┴──┐   ┌──────────────┐
                           └───────┤ Worker (same image)    ├──►│ Mail provider│
                                   └────────────────────────┘   └──────────────┘
```

The browser never talks to the database or object store with credentials. It only gets short-lived presigned URLs
(upload PUT 15 min, download GET 120 s, export download 10 min).

## 6. Repository layout

```
apps/api/seedoc/
  main.py        create_app(): routers, middleware, exception handlers
  config.py      Settings; app refuses to start if a required var is missing
  deps.py        get_db, get_ctx, require_role, require_fresh_auth, RequestContext
  db/            engine, session factory, set_tenant(), RLS helpers
  models/        SQLAlchemy ORM models
  schemas/       Pydantic request/response models
  routers/       HTTP only: auth, app/*, portal, operator, staff, internal, health
  services/      business logic + transactions (no FastAPI imports)
  jobs/          Procrastinate tasks (thin; call services)
  ai/            pdf_text, chunking, embeddings, search, assistant, prompts, provider
  storage/       s3.py: presign_put, presign_get, put_object, delete_object
  mail/          send.py + templates/
  security/      passwords, sessions, totp, pin, tokens, crypto, rate_limit, host
  errors.py      AppError + all error codes
  audit.py       write_audit_event()
  usage.py       record_usage_event()

apps/web/src/
  main.tsx, router.tsx
  app/<feature>/        manufacturer screens
  portal/               public QR pages (mobile-first, tenant branding)
  operator/             operator area
  staff/                staff console
  auth/                 login, invite, password reset
  components/ui/        shadcn components
  lib/api/schema.d.ts   GENERATED — never edit
  lib/api/client.ts     openapi-fetch client
  lib/api/endpoints.ts  one function per operation_id
  lib/api/hooks/        TanStack Query hooks
  i18n/de.json, en.json

infra/   docker-compose.yml, Caddy, deploy
docs/    the contract
```

**Layering:** a router function parses input, calls **one** service function and returns a schema. Its name **is**
the `operation_id`. Services take `(db, ctx, …)`, own the transaction and raise `AppError(code=…)`, never
`HTTPException`. Models never import services, and schemas never import models. Jobs are idempotent.

## 7. Tenancy, security and authentication

**Row-Level Security**

- Every tenant table has `tenant_id uuid not null` and RLS **enabled and forced**.
- Three DB roles: the API connects as `seedoc_app` (non-owner, no `BYPASSRLS`). Migrations run as `seedoc_owner`.
  Staff routes and jobs use `seedoc_admin` (`BYPASSRLS`) through a separate engine.
- Per request: `set_config('app.tenant_id', …, true)`. Policy: `tenant_id = current_setting('app.tenant_id')::uuid`.
  If no tenant is set, queries return zero rows.
- The service layer also filters by `ctx.tenant_id`.
- Portal tokens resolve through the `SECURITY DEFINER` function `resolve_public_token(token)`; operator access goes
  through `operator_machine_access(machine_id, user_id)`.
- Anything outside your tenant returns **404**, never 403.

**Authentication**

| Audience | Mechanism |
| --- | --- |
| Manufacturer users, operators | E-mail + password (Argon2id). Cookie `seedoc_session` (HttpOnly, Secure, SameSite=Lax); the DB stores only `sha256(token)` |
| Staff | Same login + **TOTP required** |
| Portal PIN | Cookie `seedoc_portal`, 4 h, bound to delivery + PIN version |
| Fresh auth | `POST /auth/reauth`, valid 30 min; required for PIN set/reveal, role changes, removing members, grants |

- Invite-only: no public sign-up.
- CSRF: every non-GET request with a cookie must send an `Origin` matching `APP_URL` (or an active tenant domain on
  portal routes).
- Sessions: 12 h idle timeout, 30 days absolute; the token rotates on login.
- Passwords are 12–128 characters. Ten failed logins in 15 min per e-mail or IP hash → `429` for 15 min.

**Host routing and domains**

- `APP_HOST` (or `localhost` outside production) serves the full app.
- An **active** host in `tenant_domains` serves only `/m/*`, `/s/*`, `/api/v1/portal/*` and `/api/v1/health` for
  that tenant. Any other host returns a neutral 404.
- Caddy on-demand TLS asks `/api/v1/internal/tls-allowed`, so only `pending`/`active` domains get certificates.
- QR labels use the tenant's primary active domain (fallback `APP_HOST`). Printing is blocked (`domain_not_ready`)
  while the primary domain is `pending`.

**Security headers** (Caddy): HSTS, CSP without inline scripts, `X-Frame-Options DENY`,
`Referrer-Policy strict-origin-when-cross-origin`. Production never returns stack traces.

## 8. Documents and the AI pipeline

```
create_upload ─► browser PUT to presigned URL ─► create_document / create_document_version
                                                  (verifies size, SHA-256, magic bytes %PDF)
                                                     ▼
                                     job process_version (page text → text_chunks)
                                                     ▼
                                     job embed_chunks (batches of 96 → embeddings → ready)
```

- `processing_status`: `pending → processing → ready | failed`. Publishing requires `ready`.
- Chunking: per page, ~800 tokens with 100-token overlap, never across pages.
- Hybrid search: vector top 40 + full-text top 40 (per-language `ts_config`), merged by reciprocal-rank fusion
  (k = 60). Results are filtered **in SQL** to the version IDs the caller may see, never afterwards.
- Assistant: top 6 chunks of 1,400 chars each, last 8 turns, temperature 0.2, max 1,200 output tokens, streamed via
  SSE. Below the relevance threshold the model is not called and a refusal is returned. Every answer is stored with
  its sources.
- Quotas: 20 questions/hour per PIN session, 20/hour per IP hash per machine for anonymous visitors, 30/hour per
  operator.
- The system prompt requires a cited source for every fact, never invents values, puts safety first, treats source
  text as data rather than instructions, and answers in the question's language (formal German "Sie").

**Background jobs**

| Job | Trigger | Does |
| --- | --- | --- |
| `process_version` | version created | verify file, page count, page text, chunks |
| `embed_chunks` | after processing | embeddings, mark `ready` |
| `send_email` | invite, reset | send template, retry 5× |
| `build_export` | export requested | ZIP + `manifest.json`, kept 7 days |
| `expire_exports` | daily 03:00 | delete expired exports |
| `purge_trash` | daily 03:30 | hard-delete documents trashed > 30 days and never released |
| `meter_storage` | daily 02:00 | `storage_bytes_daily` usage event per tenant |
| `check_domains` | hourly | DNS + TLS check of tenant domains |

## 9. Business rules

**Roles**

| Action | editor | admin | owner | staff |
| --- | --- | --- | --- | --- |
| Documents, folders, products, product releases | ✓ | ✓ | ✓ | |
| Customers, deliveries, machines, drafts, waivers, publish, QR labels, exports | ✓ | ✓ | ✓ | |
| Spaces, branding, invitations, remove members, audit log, usage | | ✓ | ✓ | |
| PIN set/reveal/disable, operators, grants, archive machines | | ✓ | ✓ | |
| Change member roles | | | ✓ | |
| Create/deactivate tenants, manage domains | | | | ✓ (TOTP) |

A tenant always keeps at least one owner.

**Documents:** PDF only (checked by magic bytes), ≤ 100 MB. Size and SHA-256 must match the upload. Folder defaults
apply only at creation. Duplicates are allowed but flagged. A new version becomes current immediately. Language
variants share a `group_id` and must have distinct languages. Trash can be restored for 30 days; after that a
document is purged only if no release references it.

**Portal visibility**

| Visitor | Sees |
| --- | --- |
| Anyone with the QR token | `public` items of the current release |
| Valid PIN session | `public` + `customer` |
| Operator with an active grant | `public` + `customer` |
| Manufacturer member (app) | everything, all releases |
| Nobody on the portal | `internal` |

A machine page shows its own items plus shared items. A system page shows shared items plus the list of machines.
Safety instructions come first. Every file request is re-checked before a 120 s URL is issued. Limit: 60 requests/min
per IP hash. Responses are `Cache-Control: private, no-store`.

**PIN:** six digits generated by the server, stored as an Argon2id hash plus AES-256-GCM ciphertext (so admins can
reveal it). It is never logged and never sent in a GET response. A wrong, missing or disabled PIN always gives the
same `pin_rejected`. Five failures per IP hash in 15 min → blocked 15 min. Fifty consecutive failures per delivery →
locked 24 h. Rotating the PIN revokes all sessions.

**Publish** (one transaction): lock the delivery → a draft must exist → run the completeness check (`no_machines`,
`no_items`, `machine_without_items`, `version_not_ready`, `access_level_missing`, `language_missing`) → insert the
release and its items as frozen copies → mark it current → set `first_published_at` and record the
`machine_first_published` usage event → delete the draft → write the audit event `delivery.published`.

**Language matrix:** rows are document groups, columns are required languages, and each cell is `present`,
`missing` or `waived`. SeeDoc never translates.

**Diff** between releases: `added`, `removed`, `replaced` (other version), `access_changed`.

**Export:** a ZIP of one machine's release with folder structure plus `manifest.json` (`seedoc.export.v1`), kept
7 days.

**Operators:** invited per customer into an operator org. Grants are per machine and are re-checked on every request.

**Metering:** `machine_first_published` (once per machine), `storage_bytes_daily`, `ai_question`, `ai_tokens_in`,
`ai_tokens_out`.

**Tokens:** 32 random bytes, base64url (43 chars), never regenerated.

## 10. Data model

PostgreSQL 16 with `vector`, `pgcrypto` and `citext`.

```
tenants ─┬─< tenant_members >── users ──< sessions, password_reset_tokens
         ├─< invitations
         ├─< spaces ─< folders (tree) ─< documents ─< document_versions ─< text_chunks
         ├─< products ─< product_documents >── documents
         │       └──< product_releases ─< product_release_items ──> document_versions
         ├─< customers ─< deliveries ─< machines (public_token = machine QR)
         │       │           ├── public_token (= system QR)
         │       │           ├── delivery_drafts ─< draft_items
         │       │           ├─< delivery_releases ─< delivery_release_items
         │       │           ├─< language_waivers
         │       │           └── portal_pins ─< portal_sessions ; portal_attempts
         │       └─< customer_operator_orgs >── operator_orgs ─< operator_members >── users
         ├─< machine_grants
         ├─< tenant_domains, exports, usage_events, assistant_answers, uploads
         └─< audit_events
```

Key enums: `member_role` (`owner`, `admin`, `editor`), `access_level` (`public`, `customer`, `internal`),
`doc_type` (`operating_manual`, `installation_manual`, `maintenance_manual`, `safety_instruction`, `datasheet`,
`spare_parts_list`, `wiring_diagram`, `declaration_of_conformity`, `certificate`, `test_report`,
`training_material`, `other`), `processing_status`, `delivery_kind` (`machine`, `system`), `delivery_status`,
`pin_status`, `domain_status`, `export_status`, `usage_kind`.

Languages are ISO 639-1 codes (`de`, `en`, …), validated in the API rather than by an enum.
`users`, `sessions`, `password_reset_tokens`, `operator_orgs` and `operator_members` are global (no tenant RLS).
Immutability is enforced by DB triggers and grants. Full schema: `docs/DATA_MODEL.md`.

## 11. API overview

Base URL `/api/v1`. OpenAPI at `/api/v1/openapi.json` (docs UI not in production). JSON is `snake_case`.
For every endpoint, `operation_id` = router function = service function, the frontend function is
`camelCase(operation_id)`, and the hook is `use<Name>`.

| Area | Prefix | Examples |
| --- | --- | --- |
| Health / internal | `/health`, `/internal` | `get_health`, `internal_check_tls_allowed` |
| Auth | `/auth` | `login`, `logout`, `get_me`, `reauthenticate`, `request_password_reset`, `accept_invitation`, `setup_totp` |
| Tenant & team | `/app/tenants/{tenant_id}` | `get_tenant`, `list_members`, `create_invitation`, `list_audit_events`, `get_usage` |
| Library | `…/spaces`, `/folders`, `/uploads`, `/documents` | `create_upload`, `create_document`, `create_document_version`, `trash_document`, `link_language_variant` |
| Products | `…/products` | `create_product`, `set_product_documents`, `create_product_release`, `get_product_language_matrix` |
| Customers & deliveries | `…/customers`, `/deliveries`, `/machines` | `create_delivery`, `create_machine`, `attach_machine_document` |
| Draft & publish | `…/deliveries/{id}/…` | `create_draft`, `replace_draft_items`, `get_delivery_check`, `publish_delivery`, `diff_delivery_releases`, `download_qr_labels` |
| PIN, operators, exports | `…/pin`, `/operators`, `/grants`, `/exports` | `set_pin`, `reveal_pin`, `invite_operator`, `create_machine_grant`, `create_export` |
| Public portal | `/portal` | `portal_get_machine`, `portal_get_system`, `portal_unlock_machine`, `portal_ask_machine` (SSE), `portal_rate_answer` |
| Operator | `/operator` | `operator_list_machines`, `operator_get_machine`, `operator_ask_machine` |
| Staff | `/staff` | `staff_create_tenant`, `staff_create_domain`, `staff_check_domain`, `staff_find_users` |

Errors use the shape `{"error": {"code", "message", "details"}}`. The UI shows `t("errors.<code>")`. Codes include
`unauthenticated`, `forbidden`, `not_found`, `validation_failed`, `conflict`, `publish_blocked`, `draft_exists`,
`upload_incomplete`, `domain_not_ready`, `pin_rejected`, `pin_locked`, `rate_limited` and `ai_unavailable`.
Full list: `docs/API.md` and `docs/NAMING.md` §11.

## 12. Naming conventions

- Glossary (code ↔ German UI): `tenant` (Hersteller), `space` (Wissensraum), `folder` (Ordner), `document`,
  `version`, `product`, `product_release` (Produktfreigabe), `customer` (Kunde), `delivery` (Lieferung), `machine`
  (Maschine), system (Anlage, only as `delivery.kind = system`), `draft` (Entwurf), `delivery_release`
  (Lieferfreigabe), `language_waiver`, `operator_org` (Betreiber), `grant`, `domain`.
- **Forbidden in code:** `company`, `org` (alone), `manufacturer`, `collection`, `knowledge_space`, `asset`,
  `installed_machine`, `plant`, `locale`, `snapshot`, `revision`.
- Booleans start with `is_`/`has_`/`can_`. Timestamps end in `_at` (UTC). Numbers end in `_no`, counts in `_count`
  and sizes in `_bytes`. Foreign keys are `<singular>_id`.
- Tables are plural `snake_case`. Python is `snake_case`. TS functions are `camelCase`, components `PascalCase`.
  URLs are `kebab-case`.
- i18n keys look like `<area>.<screen>.<element>`, e.g. `documents.list.emptyTitle`. Dates use `dd.MM.yyyy` with
  locale `de-DE`.
- Audit actions are `<entity>.<past_tense_verb>`, e.g. `delivery.published`.
- Logs: `structlog` JSON with `snake_case` event names. Never log tokens, PINs, passwords, presigned URLs, raw IPs
  or document text.
- Git branches: one per developer (`DevArea-Jamshid`, `DevArea-Ritik`, see §14.5). Commits follow Conventional Commits
  with an area scope, e.g. `feat(deliveries): add completeness check`.

## 13. Configuration

Copy `.env.example` to `.env` (never commit `.env`). All variables are validated at startup.

| Group | Variables |
| --- | --- |
| App | `ENVIRONMENT` (`local`/`staging`/`production`), `APP_URL`, `APP_HOST` |
| Database (3 roles) | `DATABASE_URL` (`seedoc_app`), `DATABASE_ADMIN_URL` (`seedoc_admin`), `DATABASE_OWNER_URL` (`seedoc_owner`) |
| Object storage | `S3_ENDPOINT`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` |
| Secrets (32 bytes, base64) | `PIN_ENCRYPTION_KEY`, `TOTP_ENCRYPTION_KEY`, `IP_HASH_PEPPER` |
| AI | `AI_PROVIDER` (`openai`/`azure_openai`/`mistral`), `AI_API_KEY`, `AI_BASE_URL`, `EMBEDDING_MODEL`, `CHAT_MODEL` |
| Mail | `MAIL_API_KEY`, `MAIL_FROM` |
| Monitoring | `SENTRY_DSN` |
| Feature switches | `FEATURE_PORTAL_PIN`, `FEATURE_OPERATOR_ACCOUNTS`, `FEATURE_EXPORTS` |
| Frontend (public) | `VITE_API_BASE_URL`, `VITE_SENTRY_DSN`, `VITE_ENVIRONMENT` |

Generate a secret:

```bash
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

## 14. Local development

### 14.1 What is already built

| Area | State |
| --- | --- |
| Monorepo (`apps/api`, `apps/web`, `infra`), tooling, pre-commit | done (M0-A1) |
| Docker Compose stack + Makefile | done (M0-A2) |
| CI: lint, type-check, tests, image builds (`.github/workflows/ci.yml`) | done (M0-A3) |
| FastAPI skeleton: settings, all error codes, `RequestContext`, role/fresh-auth checks, `GET /api/v1/health` | done (M0-A4) |
| Web skeleton: Vite, React 19, TS strict, Tailwind 4, shadcn base, React Router, TanStack Query, Vitest | done (M0-B1) |
| `.github/CODEOWNERS`, PR template, "Task brief" issue template | done |
| Migration `0001_identity` (RLS), auth API, i18n, API client | done (M0-A5, M0-A6, M0-B2, M0-B3) |
| Staff API + TOTP, `make seed` demo data | done (M0-A8, M0-A10) |
| Mail, staging, app shell, auth + staff screens | **next** (M0-A7, M0-A9, M0-B4 … M0-B7) — see [Roadmap](#18-roadmap) |

### 14.2 Install these first

| Tool | Version | Windows (PowerShell) | macOS | Check |
| --- | --- | --- | --- | --- |
| Git | any recent | `winget install Git.Git` | `brew install git` | `git --version` |
| Docker Desktop (Compose v2) | any recent | `winget install Docker.DockerDesktop` | `brew install --cask docker` | `docker compose version` |
| Node.js | 22 LTS | `winget install OpenJS.NodeJS.LTS` | `brew install node@22` | `node --version` |
| pnpm | pinned in `package.json` (`packageManager`) | `corepack enable` (ships with Node) | `corepack enable` | `pnpm --version` |
| uv (Python manager) | latest | `winget install astral-sh.uv` | `brew install uv` | `uv --version` |
| Python | 3.12 | `uv python install 3.12` (uv picks it automatically) | same | `uv run python --version` in `apps/api` |
| make | optional | `winget install ezwinports.make` | preinstalled | `make --version` |

Editor: install the ESLint, Prettier and Ruff extensions. Start Docker Desktop before the steps below.

### 14.3 First-time setup

**1. Clone**

```bash
git clone https://github.com/Dev-Seedoc/seedoc-core.git
cd seedoc-core
```

**2. Get the contract docs.** `docs/`, `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` and
`.env.example` are **not in Git** (see `.gitignore`); get them from Raven / the shared drive and put them in the repo
root. Read them in the order of `docs/HANDOVER.md` §3 before writing code, and make your AI assistant load
`AGENTS.md` (§3 above).

**3. Create `.env`** in the repo root (never commit it). For local development this is enough; the three secrets may
stay empty locally, but must be set (32 random bytes, base64 — see §13) on staging/production:

```dotenv
ENVIRONMENT=local
APP_URL=http://localhost:5173
APP_HOST=localhost

DATABASE_URL=postgresql+asyncpg://seedoc_app:seedoc_app@localhost:5433/seedoc
DATABASE_ADMIN_URL=postgresql+asyncpg://seedoc_admin:seedoc_admin@localhost:5433/seedoc
DATABASE_OWNER_URL=postgresql+asyncpg://seedoc_owner:seedoc_owner@localhost:5433/seedoc

S3_ENDPOINT=http://localhost:9000
S3_REGION=eu-central-1
S3_BUCKET=seedoc-local
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin

PIN_ENCRYPTION_KEY=
TOTP_ENCRYPTION_KEY=
IP_HASH_PEPPER=

AI_PROVIDER=openai
AI_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4.1-mini

MAIL_API_KEY=
MAIL_FROM=SeeDoc <noreply@seedoc.cloud>

VITE_API_BASE_URL=/api/v1
VITE_ENVIRONMENT=local
```

**4. Install dependencies**

```bash
make install
```

Without make: `cd apps/api && uv sync`, then `cd ../.. && pnpm install`.

**5. Start Postgres, S3 and Mailpit**

```bash
make up
```

Without make: `docker compose -f infra/docker-compose.yml up -d --wait`. On first start the Postgres container
creates the three roles (`seedoc_owner`, `seedoc_app`, `seedoc_admin`) and the extensions from
`infra/postgres/init/01-roles.sql`, and `s3-init` creates the bucket `seedoc-local`.

**6. Run migrations**

```bash
make migrate
make seed
```

Without make: `cd apps/api && uv run alembic upgrade head && uv run python -m seedoc.seed`.

`make seed` creates the tenant "Demo Maschinenbau GmbH" with `owner@`, `admin@`, `editor@demo.example.com` and the staff
user `staff@seedoc.example.com`. It prints the passwords (and the staff TOTP link) **only once**, so store them.
Running it again changes nothing; `make seed ARGS=--reset-passwords` prints new passwords. Fill the three secrets in
`.env` first (§13), otherwise the staff user gets no TOTP and cannot use `/staff`.

**7. Start the API and the web app**

```bash
make dev
```

Without make, in two terminals: `cd apps/api && uv run uvicorn seedoc.main:create_app --factory --reload --port 8000`
and `pnpm --dir apps/web dev`.

**8. Check that it works**

| Open | Expect |
| --- | --- |
| http://localhost:5173 | The SeeDoc placeholder page |
| http://localhost:5173/api/v1/health | `{"status":"ok","db":"ok"}` (through the Vite proxy) |
| http://localhost:8000/api/v1/docs | Swagger UI with `get_health` |
| http://localhost:8025 | Mailpit inbox (all local e-mail lands here) |
| http://localhost:9001 | S3 console (`minioadmin` / `minioadmin`) |

**9. Run the checks** (the same ones CI runs)

```bash
make lint
make typecheck
make test
```

### 14.4 Local ports

| Port | Service |
| --- | --- |
| 5173 | Web (Vite dev server, proxies `/api` → 8000) |
| 8000 | API (FastAPI / uvicorn) |
| 5433 | Postgres 16 + pgvector (container port 5432; host port 5433 avoids a locally installed PostgreSQL) |
| 9000 / 9001 | S3 API / console (RustFS — MinIO no longer publishes public Docker images) |
| 1025 / 8025 | Mailpit SMTP / web UI |
| 8080 | Web container (only with `--profile app`) |

### 14.5 Day-to-day: branches and merging

Each developer has **one branch** and pushes only there. Nobody pushes to `main` directly. Work reaches `main` in
two steps, so integration problems show up on `DevArea-Ritik`, never on `main`:

```
DevArea-Jamshid ──(1) merge + test──▶ DevArea-Ritik ──(2) check-branch──▶ main (fast-forward)
```

| Branch | Who pushes | Goes into |
| --- | --- | --- |
| `DevArea-Jamshid` | Jamshid | `DevArea-Ritik` (Raven merges it after the integration tests pass) |
| `DevArea-Ritik` | Raven | `main` (fast-forward, after `make check-branch BRANCH=DevArea-Ritik` passes) |

Jamshid, every day:

```bash
git switch DevArea-Jamshid
git pull
git merge origin/main           # pick up everything already integrated
# … work, then before pushing:
make lint typecheck test        # Docker must be running, otherwise DB tests are only skipped
git push                        # CI runs on every push to DevArea-* branches
```

Raven, to integrate:

```bash
make check-branch BRANCH=DevArea-Jamshid   # (optional first look) his branch alone, as pushed
git switch DevArea-Ritik && git pull
git merge origin/DevArea-Jamshid           # (1) integrate; fix conflicts here, never on main
make lint typecheck test                   # integration tests on the combined code
git push
make check-branch BRANCH=DevArea-Ritik     # (2) all CI checks on the pushed combined branch
git push origin origin/DevArea-Ritik:refs/heads/main   # only after ALL CHECKS PASSED (fast-forward)
```

If a check fails, `main` is not touched: fix it on `DevArea-Ritik` (or ask Jamshid to fix it on his branch) and run
the steps again.

### 14.6 Troubleshooting

| Symptom | Fix |
| --- | --- |
| `password authentication failed for user "seedoc_owner"` | Something else uses the port in `.env` — check `DATABASE_*_URL` points at `localhost:5433` |
| Database tests show `SKIPPED … Docker is not running` | Start Docker Desktop; the tests start their own Postgres with testcontainers |
| `failed to connect to the docker API` | Docker Desktop is not running |
| Health returns `{"status":"error","db":"error"}` (503) | `make up` was not run, or the Postgres container is not healthy (`docker compose -f infra/docker-compose.yml ps`) |
| Roles/extensions missing after changing `01-roles.sql` | Init scripts run only on a fresh volume: `docker compose -f infra/docker-compose.yml down -v`, then `make up` |
| `uv` warns "Failed to hardlink files" | Harmless (cache on another drive); set `UV_LINK_MODE=copy` to silence it |
| `make: command not found` on Windows | `winget install ezwinports.make`, or use the "Without make" commands above |

### 14.7 Command reference

| Command | Does |
| --- | --- |
| `make test` | `pytest` (apps/api) + `vitest` (apps/web). DB tests use testcontainers and are skipped when Docker is not running |
| `make lint` / `make typecheck` | Ruff + ESLint / pyright strict + `tsc` |
| `make gen-api` | Regenerates `apps/web/src/lib/api/schema.d.ts` from the running API |
| `docker compose -f infra/docker-compose.yml --profile app up -d --build` | Also runs `seedoc-api` and `seedoc-web` (Caddy on :8080) in containers |

The Postgres container creates the three roles (`seedoc_owner`, `seedoc_app`, `seedoc_admin`) and the extensions
from `infra/postgres/init/01-roles.sql` on first start. Run `docker compose -f infra/docker-compose.yml down -v`
to reset the database.

## 15. Testing

| Suite | Location | Must prove |
| --- | --- | --- |
| Unit | `apps/api/tests/unit`, `apps/web/src/**/*.test.ts(x)` | chunking, PIN, permissions, diff, helpers |
| API | `apps/api/tests/api/` | each route: happy path, 401, 403 wrong role, 404 other tenant |
| Isolation | `apps/api/tests/isolation/` | tenant A cannot touch tenant B rows as `seedoc_app` |
| Immutability | `apps/api/tests/immutability/` | UPDATE/DELETE on release tables raises |
| Portal | `apps/api/tests/portal/` | internal never visible; customer only with PIN/grant; old release hidden |
| E2E | `apps/web/e2e/` (Playwright, nightly) | upload → release → delivery → publish → portal → ask |
| AI eval | `apps/api/eval/` | 30 German questions: correct page in top 6 ≥ 80 %, refusal without source |

Tests run against real Postgres (testcontainers), never SQLite.

## 16. Deployment

| Env | Where | Deploy | Data |
| --- | --- | --- | --- |
| local | Docker Compose (postgres+pgvector, S3 (RustFS), mailpit, api, worker, web) | — | `make seed` demo tenant |
| staging | Hetzner server | every merge to `main` | fake data only |
| production | separate Hetzner server, managed EU Postgres recommended | Git tag `vX.Y.Z` | real customers |

- Images: `seedoc-api` (API and worker, different commands) and `seedoc-web` (static build served by Caddy).
- Migrations (`alembic upgrade head`) run before the new API starts.
- Backups: nightly `pg_dump` to object storage, kept 30 days; bucket versioning; quarterly restore drill.
- Monitoring: Sentry, plus uptime checks on `/api/v1/health` and one real portal URL.

## 17. Team, work split and workflow

The detailed task list, due dates and handovers are in `docs/WORK_PLAN.md`.

| Area | Owner |
| --- | --- |
| Critical work: migrations, tenant isolation (RLS), immutability, auth/sessions/CSRF, staff/TOTP, uploads and file checks, release freezing and publish, portal API, PIN, domains/TLS, AI pipeline, operators and grants, exports, metering, infra, production | **Raven** (`@Ravencrest-01`) — also reviews every PR |
| All screens, UI kit, i18n and German texts, API client; supervised backend features (spaces/folders, language variants, products/customers/deliveries/machines CRUD, dashboard, audit list, QR label layout, language matrix, diff, usage, lists); mail templates; sample data; AI eval; E2E tests | **Jamshid** |
| Product scope, priorities, wording, accounts, customer contact | **Founder** |

Changes under the paths in `.github/CODEOWNERS` (migrations, security, auth, portal, PIN, releases, AI, jobs,
storage, tests, infra) always need Raven's approval.

- **Contract first:** a new endpoint, column or error code goes into `docs/` in a small PR before it is implemented.
- **Shared files** (`docs/*`, `AGENTS.md`, `errors.py`, `deps.py`, `audit.py`, `usage.py`, `client.ts`,
  `router.tsx`, `common.*`/`errors.*` i18n keys) change only through PRs reviewed by both developers.
- **Migrations:** one open migration PR at a time. Take the next `NNNN` from `main`.
- Whoever changes the API regenerates `schema.d.ts` in the same PR.
- PRs stay under ~400 lines and say "Task: <id>" and "Contract changes: …". Reviews happen within one working day.
  Rebase on `main` daily.
- Rhythm: a daily async update, a weekly 30-min sync and a founder demo every milestone Friday.
- Open question? Propose an answer and continue behind a `TODO(decision): …` comment instead of blocking.

## 18. Roadmap

| Milestone | Dates | Demo goal |
| --- | --- | --- |
| M0 Foundations | 5 – 18 Oct 2026 | Staff creates a tenant; invited admin logs in on staging |
| M1 Document library | 19 Oct – 1 Nov | 20 sample manuals uploaded, versioned, processed |
| M2 Products, deliveries, publish | 2 – 15 Nov | A 2-machine system published as release 1 |
| M3 Portal, QR, domains, PIN | 16 – 29 Nov | Printed label opens the portal on a test manufacturer domain |
| M4 AI assistant | 30 Nov – 13 Dec | 8 of 10 German questions cite the right page |
| M5a Pilot features I | 14 – 20 Dec | Language matrix and completeness check block a bad publish |
| Buffer | 21 Dec – 3 Jan | Catch-up only |
| M5b Pilot features II | 4 – 17 Jan 2027 | Operator view, controlled update + diff, ZIP export |
| M6 Validation & hardening | 18 – 29 Jan | Full workflow on production with real documents → `v1.0.0` |

**Cut rule:** if a milestone is more than 3 working days behind, or behind at two checkpoints in a row, cut in this
order: (1) release diff UI, (2) export, (3) PIN unlock, (4) assistant on the operator view.
**Never cut:** tenant isolation, immutability, manufacturer domains, the language matrix.

**Later (names reserved, not built):** bulk roll-out, cross-manufacturer portfolio, internal search and assistant,
feedback review, public API keys and webhooks, DMS connectors, analytics, price plans.

**Open founder decisions:** work split (F-1), accounts (F-2), sample documents (F-3), `/s/` path (F-4), default
visibility per doc type (F-5), pilot languages (F-6), production AI provider + DPA (F-7), pilot domain (F-8), keep PIN?
(F-9), export format (F-10), real documents (F-11), German copy reviewer (F-12), old data (F-13). See
`docs/ROADMAP.md` for due dates.

## 19. Decision log

| # | Decision | Reason |
| --- | --- | --- |
| D1 | `pypdfium2` instead of PyMuPDF | PyMuPDF is AGPL |
| D2 | Full-text with per-row `ts_config` (german, english, …) | Stemming: "Schrauben" must find "Schraube" |
| D3 | Forced RLS + non-owner app role + admin role | RLS is skipped for table owners and superusers |
| D4 | Caddy on-demand TLS with `ask` endpoint | Prevents certificate abuse |
| D5 | German-only UI for the pilot; `en.json` kept in sync | Founder decision |
| D6 | System portal path `/s/{token}` | Fresh start; confirm before the first print |
| D7 | PIN unlock under the viewed token | No third token type |
| D8 | PIN reveal via `POST` | Secrets must not travel in cacheable GETs |
| D9 | Table `audit_events` (plural) | Naming consistency |
| D10 | Added `product_documents`, `password_reset_tokens`, `portal_attempts`, `invitations.kind` | Gaps in the original guide's schema |
| D11 | ISO 639-1 language codes | The matrix compares languages, not regions |
| D12 | `snake_case` JSON and TS types | Generated types match the API 1:1 |
| D13 | AI provider still open (OpenAI EU / Azure EU / Mistral) | Decide before M4; all calls go through `ai/provider.py` |

## 20. The old system

`knowledge-hub-base` (Lovable/TanStack Start + Supabase + Vercel; ~100k lines of TS, 198 migrations, ~380 SQL
functions) proved the product idea and many business rules. We keep the rules, not the code.

- **Reference only:** do not copy code from it and do not let an AI use it as a style example.
- Useful when building the same feature: portal pages, delivery workspace, chat UI pieces, German wording and the
  design palette.
- Names changed: `installed_machines` → `machines`, `collections` → `folders`, `/a/` → `/s/`, `locale` → `language`.
