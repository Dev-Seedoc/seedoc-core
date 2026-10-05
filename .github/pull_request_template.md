Task: <!-- e.g. M2-B2 -->
Handover: <!-- H-xx, or "none" -->
Contract changes: <!-- "none", or list every new/changed endpoint, column, error code, i18n common/errors key, dependency -->

### What I built (3–5 sentences, in my own words)

### What I was unsure about

### How I tested it
<!-- commands you ran + what you clicked -->

- [ ] `make lint` passes
- [ ] `make typecheck` passes
- [ ] `make test` passes (Docker running)

### Checklist

- [ ] Only files from the task brief changed — files changed outside the brief: none
- [ ] No test changed to make code pass
- [ ] Names match `docs/API.md`, `docs/DATA_MODEL.md`, `docs/NAMING.md`; no new dependency
- [ ] New endpoint: tests for happy path, 401, 403 wrong role, 404 other tenant
- [ ] API changed: `make gen-api` run and `apps/web/src/lib/api/schema.d.ts` committed
- [ ] UI text only via `de.json` / `en.json` (formal "Sie")
- [ ] No secrets, tokens, PINs, presigned URLs or document text in code or logs
