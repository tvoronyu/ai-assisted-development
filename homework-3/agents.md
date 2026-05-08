# Virtual Card Service — Agent Guidelines

> This file configures AI coding agents (Claude Code, Cursor, GitHub Copilot) acting on the `vcard-svc` codebase. Read this file once at session start. Reference `specification.md` for domain requirements and `task IDs` (T-xx, MO-x, NFR-xx).

---

## 1. Purpose & Scope

This document governs agent behavior when generating, modifying, or reviewing code for `vcard-svc`, a virtual card microservice in a regulated EU/UA neobank environment. The service implements the complete card lifecycle from creation through cancellation, with spending limits, transaction history, and audit compliance.

Rules in this file are non-negotiable; agents must not relax them for "simplicity," "dev convenience," or "test shortcuts." The source of truth for requirements is `specification.md` (§8: Low-Level Tasks, T-01 through T-24). Task IDs are the unit of work; always reference the originating task when proposing or implementing changes.

An agent must read this file at the start of each session and reference it throughout. Conflicts with this file or `specification.md` trigger escalation (§10) rather than silent workarounds.

---

## 2. Tech Stack Assumptions

### Backend Language & Framework

**Primary stack: Go 1.22**
- HTTP framework: `net/http` + `chi` router for REST API
- gRPC: `google.golang.org/grpc` v1.60+ for internal service-to-service calls
- No logging framework dogma; common choices: `zerolog`, `zap`, or stdlib `log/slog` — agent must use the chosen logger consistently across all files, wrapping it in a custom redaction layer (see §6)

**Secondary stack: Node.js 20 + TypeScript (strict mode)**
- HTTP framework: Fastify with `@fastify/type-provider-zod` for runtime schema validation
- gRPC: `@grpc/grpc-js` v1.8+
- Logger: pino or winston (again, wrapped in redaction layer)

**Never mix languages in the same service.** If a `vcard-svc` implementation starts in Go, all modules must remain Go. If TS, all TS. Cross-language communication happens only at gRPC or HTTP boundaries between services.

### Data Layer

**Postgres 15 or later; no exceptions.**
- No SQLite fallbacks, no in-memory caches as primary store.
- Migrations: `golang-migrate` (Go) or `node-pg-migrate` (TS). Forward-only; no rollback scripts in production code. Compensating migrations must document rollback procedure outside the migration file.
- Schema: UTF-8 collation, TIMESTAMPTZ for all temporal columns, JSONB for extensible fields. Native Postgres ENUM types for card status, event types, and error codes.

**Redis 7+ (optional but recommended)**
- Namespace: `vcard:*` for all keys (idempotency cache, card/limit cache, reveal tokens, velocity counters).
- No session state; idempotency store only. TTL enforced at write time.
- Connection pooling: health checks + exponential backoff on unavailability. Redis failure must not block authorization (degrade to DB-only path, increased latency).

**Money: `int64` minor units + `CHAR(3)` ISO-4217**
- Never `float64`, `float32`, `Decimal`, or string. Example: 1050 UAH = 105000 minor units (kopiyky).
- Banker's rounding (HALF_EVEN) on any rounding operation. Format to user locale on HTTP egress only.

### Messaging & Events

**Kafka 3.6+**
- Outbox pattern: state changes write to DB `outbox` table in same transaction; async publisher drains outbox and publishes to Kafka topics.
- Topics: `vcard.events.v1` (card state events), `vcard.fraud.v1` (fraud flag events).
- No dual-write (DB + Kafka in same operation). If Kafka publish fails, outbox row persists and is retried.
- Partition key for `vcard.events.v1`: `card_id` (ensures per-card ordering).
- Message format: JSON with `event_id` (UUIDv7), `event_type` (string), `card_id`, `actor_id`, `payload` (JSONB), `occurred_at` (RFC 3339 UTC).

### IDs & Identifiers

- **Card ID, Limit ID**: ULID (25 chars, sortable, lower collision risk than UUIDv4).
- **Event ID, Transaction ID**: UUIDv7 (timestamp-sortable, RFC 4122 compliant).
- Never auto-increment integers for security-sensitive resources.
- IDs are opaque to clients; never log or expose internal ID schemes.

### OpenAPI Contract

- **OpenAPI 3.1** specification at `openapi/vcard.yaml` is the authoritative source of truth for REST endpoints.
- All endpoints (POST, GET, PUT, PATCH) defined in spec before implementation. Spec drives type generation; agent must not alter spec without reflecting changes in code and vice versa.
- Spectral linting in CI: style guide adherence, schema validation, no duplicate operation IDs.
- Schemas defined once in `components/schemas/`; reused across all endpoints. Pydantic or Zod models must match or be explicitly divergent (with comment explaining why).

### Testing & Verification

**Go**:
- Unit tests: stdlib `testing` + `testify/assert` + `testify/mock` (or `uber-go/mock` for interface mocking).
- Integration tests: `testcontainers-go` for Postgres + Redis. No production DB fixtures used in tests.
- Coverage goal: 80%+ across service layer; 95%+ for `internal/limits/evaluate.go` (limits evaluation) and `internal/money/` (monetary operations).

**TypeScript**:
- Unit tests: Vitest + `@testing-library/` for HTTP assertions.
- Integration tests: `testcontainers` + `ts-test` or `tsx`.
- Coverage: same 80%+ / 95%+ targets.

**Load Testing**:
- k6 script at `tests/load/vcard.js`.
- Baseline scenario: 100 VUs, 5min, mixed read/write (65% read, 35% write).
- Must be runnable locally: `k6 run tests/load/vcard.js` with default thresholds defined in script.
- Thresholds: p95 < 200ms for GET endpoints, p95 < 400ms for write endpoints, error rate < 0.1%.

**CI/CD**:
- GitHub Actions pipeline: lint → format-check → type-check → unit tests → integration tests → no-PAN grep gate → contract lint → build.
- No-PAN grep gate: `grep -rE '4[0-9]{15}|5[0-9]{15}'` (Visa/MC BIN pattern) in logs and error output; fail build if matches found (except in test data labeled as such).
- Spectral lint: `openapi/vcard.yaml` must pass all rules.
- Coverage reports: minimum 80% across repo; highlight files < 80%.

---

## 3. Domain Rules (FinTech / Banking)

These are regulatory, operational, or design constraints that override convenience. Agents must implement them exactly or escalate (§10) if a task conflicts.

### Monetary Operations

1. **Money is `int64` minor units only.** No floats anywhere in business logic. Example: 1050 UAH = 105,000 minor units (kopiyky). Format for display using locale-aware formatters *on HTTP egress only*.
2. **Banker's rounding (HALF_EVEN) on any rounding.** Example: round(1.5) = 2, round(2.5) = 2. Never banker's rounding in reverse (no "round-trip" conversions that lose precision).
3. **Spent totals match SUM of individual transactions.** No accumulator drift. Verify via reconciliation job (specification.md §11).

### Card State Machine

4. **Card state machine is closed and terminal:** `pending → active → frozen ↔ active → cancelled`. No new states without an Architecture Decision Record (ADR) in `docs/adr/`. The `cancelled` state is permanent; no transition out of it.
5. **`pending` is transient.** If vault tokenization succeeds, immediately transition to `active`. If it times out, persist as `pending` and return 202; client can retry idempotently.
6. **Freeze and unfreeze are symmetric:** `frozen ↔ active` (not `pending`). Freeze on `pending` is invalid; unfreeze on `cancelled` is invalid. Return 409 `INVALID_STATE_TRANSITION`.
7. **Idempotent on already-frozen card:** freeze on `frozen` → 200 (no new event). Unfreeze on `active` → 200 (no new event).

### Authorization & Limits

8. **Limits are evaluated server-side only.** Client-supplied authorization decisions are ignored. Authorization request contains amount, merchant, MCC, country, network, is_recurring; server evaluates all limits in order, first deny wins.
9. **Evaluation order (specification.md §8, T-11):** card status check → geographic blocklist → per-merchant blocklist → online-only flag → per-MCC cap → per-transaction max → daily rolling total → monthly calendar total. Document this order in code comment.
10. **Daily window is server-time rolling (UTC); monthly window is calendar month in user's registered IANA timezone.** If user in `Europe/Kyiv`, a "daily" limit resets at midnight Kyiv time, not UTC. `specification.md` §5 specifies this.
11. **Limits are updated with immediate effect.** No grace period. If user sets daily limit from 1000 to 500 UAH, next authorization > 500 UAH is declined. If user has already spent 600 UAH in the day, accept the new limit; next auth will decline.

### Idempotency & Concurrency

12. **Idempotency is mandatory for all non-GET endpoints.** `Idempotency-Key` header required; 400 if missing on POST/PUT/PATCH. Dedupe store: Redis `vcard:idem:{user_id}:{method}:{path}:{idempotency_key}`. TTL 24h.
13. **Idempotency mismatch is 422, not 200.** Same key + different request body → return 422 `IDEMPOTENCY_MISMATCH` with `previous_body_hash` in response (help client debug). Not 409, not idempotent success.
14. **Optimistic locking on all mutable resources.** Every card and limit has `version INT`. Update with `WHERE version = $expected`. Version conflict → return 409 `VERSION_CONFLICT` with `current_version` in response. Client must retry with fresh GET.
15. **Concurrent requests with same idempotency key:** one proceeds, others wait (Redis SET NX + exponential backoff). Waiting requests return cached response (atomic per Redis).

### Audit & Immutability

16. **Append-only audit table:** `card_event` table. Never UPDATE or DELETE rows. Enforce via Postgres trigger (IF NEW.event_id IS DISTINCT FROM OLD.event_id THEN RAISE; or application-layer check in all queries).
17. **Hash chain for tamper detection:** each `card_event` has `prev_hash` (SHA-256 of previous event in card's sequence) and `event_hash` (SHA-256 of current event). Computed as SHA-256(event_id || "|" || event_type || "|" || actor_id || "|" || payload_json || "|" || prev_hash). Chain verifiable by `audit-svc` on read.
18. **Event sequence is monotonic:** `event_seq` GENERATED ALWAYS AS IDENTITY (auto-increment per card). Used for replay ordering.
19. **Every state-changing action emits an audit event within 500ms.** Card created, frozen, unfrozen, cancelled, limit changed, PAN revealed, ops access, fraud flag — all generate rows in `card_event` with actor_id, actor_role, and payload. Outbox pattern ensures async Kafka publish does not block response.

### PAN/CVV & Vault Boundary

20. **PAN and CVV never leave the card-vault boundary in plaintext.** Vault (`card-vault` service) is the PCI-DSS SAQ-D scope; `vcard-svc` is SAQ-A-EP (out of scope). PAN/CVV are tokenized at create time; `vcard-svc` stores only `token_id` (opaque UUID to vault). Reveal flow: `POST /v1/cards/:id/reveal` with SCA token → temporary reveal-token (single-use, 60s TTL, stored in Redis).
21. **Vault call failures on create:** persist card in `pending` status, return 202 with `retry_after: 30` header. Do not block card creation on vault unavailability.
22. **Vault call failures on cancel:** retry with exponential backoff (3 retries, 1s base, 2s max). If all fail, emit `CARD_CANCELLATION_DEFERRED` audit event, keep card in `pending_cancellation` state, alert ops.
23. **Vault is mTLS authenticated.** No bare HTTP calls. TLS 1.3 minimum. Certificate pinning (agent must not add code that skips cert verification).

### PII & Privacy (GDPR)

24. **Redaction is automatic.** All logging must pass through redaction middleware (§6). Redaction list: `['pan', 'cvv', 'card_number', 'full_card_number', 'track2', 'expiry', 'card_holder_name', 'track1']`. Value becomes `[REDACTED]` in logs. Apply recursively to nested JSON.
25. **GDPR right to erasure (Article 17):** cards cancelled > 7 years trigger erasure job (specification.md §8, T-20). Erasure: pseudonymize name → `ERASED_{card_id_suffix}`, aggregate transaction details to monthly summaries (delete detail rows), retain `card_event` rows (legal obligation). Do NOT delete the card row (audit continuity).
26. **Retention lock for early erasure:** if user requests erasure < 7 years after cancellation, return 409 `RETENTION_LOCK` with `retention_expires_at` in response.
27. **Ops view masked by default:** masked PAN format `5375 12** **** 1234` (first 4 + last 4 digits visible, middle masked). Full PAN reveal requires separate elevated role + SCA token + audit event.

### Error Handling

28. **All errors follow RFC 7807:** `application/problem+json` with `type` (URI, e.g., `urn:vcard:error:card-frozen`), `title` (short human-readable), `status` (HTTP status), `detail` (specifics), `code` (stable string enum, e.g., `CARD_FROZEN`). Never expose stack traces, SQL queries, or internal IDs in error response.
29. **Error codes are stable.** Once an error code is deployed (e.g., `CARD_FROZEN`), do not rename or remove it. Add new codes; never change old ones. Document breaking changes in runbook and notify clients.
30. **Validation errors are 400 with `code: 'VALIDATION_ERROR'`.** Include field name and constraint violated (e.g., `{ detail: "limit_value must be >= 0", fields: { limit_value: "must be >= 0" } }`). Do not expose regex patterns or internal validation logic.
31. **Authorization errors are 401 with `code: 'UNAUTHORIZED'` or role-specific codes:** `SCA_REQUIRED` (PAN reveal without SCA), `SCA_EXPIRED` (SCA token expired). Do not confuse 401 with 403.
32. **Conflict errors are 409:** `VERSION_CONFLICT` (optimistic lock), `INVALID_STATE_TRANSITION` (freeze on cancelled), `CARD_FROZEN` (decline reason for authorization). Include current state/version in response.

### Compliance & Logging

33. **No secrets in code or logs.** Vault URLs, API keys, signing keys loaded from environment variables or secure config store (e.g., Vault, AWS Secrets Manager). Never hardcode or log them.
34. **Structured JSON logs with trace_id.** Every log line includes `trace_id` (from request context, propagated via OpenTelemetry or custom header). Operators can grep logs by trace_id for incident investigation.
35. **Monitoring & alerting per specification.md §4 & §10.** Prometheus metrics: request rate (RPS), error rate, latency (p50/p95/p99). Alerts: `VCardAuthDeclineRateHigh` (>20% for 5min, SEV-2), `VCardAuditChainBreak` (hash mismatch, SEV-1), `VCardVaultLatencyHigh` (vault p95 > 2s, SEV-2), `VCardPendingCardStale` (card in pending > 5min, SEV-3).

---

## 4. Code Style

### Structure & Layering

1. **Layered architecture enforced:**
   - `transport/http/` (or `routes/`) — HTTP handlers only. Decode request, validate input schema, call service, encode response (RFC 7807 on error).
   - `internal/{domain}/` (e.g., `internal/cards/`, `internal/limits/`, `internal/audit/`) — business logic, pure functions, domain types.
   - `internal/db/` (or `models/`) — ORM models, queries, migrations.
   - `internal/logger/`, `internal/vault/`, `internal/notification/` — cross-cutting concerns and external integrations.
   - One primary type per file. File name matches primary export (e.g., `card_service.go` exports `CardService` or `CardCreator`).

2. **Handlers must not contain business logic.** A handler receives a request, calls exactly one service method, and shapes the response. Example (Go pseudocode):
   ```go
   func (h *CardHandler) Create(w http.ResponseWriter, r *http.Request) {
       var req CreateCardRequest
       if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
           h.respondError(w, 400, "INVALID_REQUEST", err.Error())
           return
       }
       card, err := h.svc.CreateCard(r.Context(), req)
       if err != nil {
           // map domain error to RFC 7807, write response
           h.respondError(w, statusCode(err), err.Code(), err.Detail())
           return
       }
       h.respond(w, 201, cardToResponse(card))
   }
   ```

3. **DTOs ≠ ORM models.** Pydantic schemas (Python), Zod schemas (TypeScript), or JSON structs (Go) are separate from Postgres table rows. Even if fields are identical today, keep them in different packages. DTO is for API contract; ORM model is for persistence. Examples:
   - Go: `transport/http/card_dto.go` (request/response) vs. `internal/db/card_model.go` (ORM).
   - TS: `schemas/card.ts` (Zod) vs. `models/card.ts` (TypeORM/Prisma).

4. **Dependency injection for testability.** Services and external clients (vault, notification-svc) are passed as constructor arguments, not global singletons. Example (Go):
   ```go
   type CardService struct {
       db    DB
       vault Vault
       logger Logger
   }
   func NewCardService(db DB, vault Vault, logger Logger) *CardService { ... }
   ```
   Test code can inject mocks without modifying production code.

5. **Pure functions for business logic.** The limits evaluation function (`EvaluateLimits`) must be pure: no I/O, no side effects, same inputs → same output. Inject a clock interface for determinism in tests.

### Naming Conventions

**Go**:
- Packages: lowercase, no underscores (`internal/cards`, `internal/limits`, `transport/http`).
- Types: PascalCase (`Card`, `CardState`, `AuthDecision`, `LimitWindow`).
- Functions: PascalCase for exported, camelCase for unexported (`CreateCard`, `fetchCardFromDB`).
- Errors: `Err` prefix or `Error` suffix (`ErrCardFrozen`, `CardFrozenError`). Exported errors are vars, not new instances each time.
- Constants: `SCREAMING_SNAKE_CASE` (`StateActive`, `LimitTypeDaily`).
- DB tables: snake_case singular (`card`, `card_limit`, `card_event`, `transaction`).
- DB columns: snake_case (`card_id`, `created_at`, `is_recurring`).

**TypeScript**:
- Modules/files: kebab-case (`card-service.ts`, `limit-evaluator.ts`).
- Types/Interfaces: PascalCase (`Card`, `CardState`, `AuthDecision`).
- Functions: camelCase (`createCard`, `evaluateLimits`).
- Constants: `SCREAMING_SNAKE_CASE` (`STATE_ACTIVE`, `LIMIT_TYPE_DAILY`).
- Schema exports (Zod): PascalCase suffix with `Schema` (`CardSchema`, `CreateCardRequestSchema`).

### Comments & Documentation

- **Default: no comments.** Code should be self-explanatory via naming.
- **Allowed:** one short line when the *why* is non-obvious (a hidden constraint, a workaround, a deliberate-looking-wrong choice). Examples:
  - `// Vault timeout 5s; BIN sponsor SLA allows up to 4.8s, leaving 200ms margin.`
  - `// Optimistic lock prevents race on concurrent freeze+unfreeze; client retries with fresh GET.`
- **Forbidden:** paraphrase what code does, reference task IDs or PR numbers, multi-line comment blocks, commented-out code, TODO/FIXME/XXX markers.
- **Public functions:** may have a one-line docstring if the name + signature aren't self-explanatory. Example (Go): `// EvaluateLimits returns an authorization decision based on card status and active limits.`

### Imports

- **Absolute paths from package root,** never relative (`..`). Go example: `import "github.com/monobank/vcard-svc/internal/cards"`. TS example: `import { Card } from "@/models/card"`.
- **Grouped in order:** stdlib → third-party → first-party (internal). Go tooling (`goimports`) enforces this; TS/ESLint can do likewise.
- **No unused imports.** Linter must catch and fail the build.

### Error Handling

- **Type errors; map to RFC 7807 in transport layer only.** Domain layer returns typed errors (Go: `error` interface with custom type; TS: `Error` with `code` property). HTTP layer maps to RFC 7807.
- **No bare `catch (e: unknown)` or `recover()` without typed re-raise.** Catch specific types; log context; return typed error.
- **No silent fallbacks for impossible cases.** If a precondition is violated (e.g., card not found when fetched with valid ID), panic/throw. Contract is broken; debug it.
- **Validate at boundaries (HTTP, file, external API), not at every internal call.** Internal functions assume valid inputs (checked by caller).

### Async / Concurrency

- **Anything touching I/O is async** (Go: goroutines + channels; TS: async/await).
- **No `time.Sleep` in async paths.** Use `time.After` (Go) or `setTimeout` (TS).
- **Database transactions:** explicit `BEGIN/COMMIT/ROLLBACK` with rollback on error. Optimistic locking via `WHERE version = $expected`.
- **Concurrency patterns:** use channels/mutexes only for coordination, not business logic. Business logic remains sequential and pure.

---

## 5. Testing & Verification Expectations

### Unit Tests

1. Every function in `internal/` ships with a unit test in the same package. Go: `_test.go` file; TS: `.spec.ts` sibling.
2. Mock external I/O (vault, notification-svc, Kafka). Never call production services in tests.
3. Test both success and failure paths. For limits evaluation (specification.md T-11), test all 8 evaluation steps with passing and failing cases.
4. Coverage targets:
   - `internal/limits/evaluate.go`: 95%+. All branches covered (card status check, geographic blocklist, merchant blocklist, online-only, per-MCC, per-transaction, daily rolling, monthly calendar).
   - `internal/money/` (if created for rounding, conversion): 95%+. Test banker's rounding, minor-unit overflow, currency mismatch.
   - Service layer (`internal/cards/`, `internal/limits/`, etc.): 80%+.
   - Overall repo: 80%+ (CI enforces; report failing files).

### Integration Tests

5. Use `testcontainers` (Go: `testcontainers-go`; TS: `testcontainers-js`) to spin up real Postgres + Redis in Docker. No mocks for data stores.
6. Test card creation flow end-to-end: create card → check idempotency → verify DB rows + Redis cache.
7. Test authorization flow: set limit → authorize below limit (approve) → authorize above limit (decline) → check audit event.
8. Test concurrent operations: freeze + unfreeze on same card → verify one wins, other gets 409.
9. Test idempotency: POST with key A, retry with key A → same response, no duplicate side effects. POST with key A then key B → different responses.

### Load Testing

10. k6 script at `tests/load/vcard.js` is runnable with `k6 run tests/load/vcard.js` (no CI-specific setup required locally).
11. Baseline scenario: 100 VUs, 5min, mixed read/write (65% GET /v1/cards, 15% GET /v1/cards/:id, 10% POST freeze, 5% GET transactions, 5% PUT limits).
12. Spike scenario: ramp from 100 VUs to 2000 VUs in 30s (authorization endpoint only); sustained for 1min.
13. Soak scenario: 50 VUs, 60min (catch resource leaks, connection pool exhaustion).
14. Thresholds defined in script:
    - p95 latency < 200ms for read endpoints, < 400ms for write endpoints.
    - Error rate < 0.1%.
    - Fails build if thresholds breached.

### OpenAPI Contract

15. `openapi/vcard.yaml` is source of truth. All endpoints defined before implementation.
16. CI: Spectral linting on every PR. Must pass all rules (no custom rule suppressions without documented justification).
17. Response schemas must match actual responses (agent must keep spec and code in sync).

### No-PAN Grep Gate

18. CI build includes a test step that runs:
    ```bash
    grep -rE '4[0-9]{15}|5[0-9]{15}' /logs /output /tmp || exit 0
    grep -rE '4111|5555|6011' /logs /output /tmp && exit 1 || exit 0
    ```
    Fails build if test PANs (`4111111111111111`, `5555555555554444`, `6011111111111117`) found in logs or error output. Prevents accidental PAN leaks.

### Before Marking Complete

19. Run verification pipeline in this order (all must pass):
    - **Lint:** `go vet ./...` (Go) or `eslint .` (TS).
    - **Format:** `gofmt -l .` (Go, must have 0 files) or `prettier --check .` (TS).
    - **Type check:** `go build ./...` (Go) or `tsc --noEmit` (TS).
    - **Unit tests:** `go test -v -race ./...` (Go) or `npm test` (TS), coverage report.
    - **Integration tests:** same, with `testcontainers` up.
    - **No-PAN grep gate:** custom script in CI or local test script.
    - Report results (passed / failed, which tests failed, coverage %).

---

## 6. Security & Compliance Constraints

### PII & Sensitive Data

**Never log:**
- `pan`, `cvv`, `card_number`, `full_card_number`, `track1`, `track2`, `expiry`, `card_holder_name`.
- Redaction middleware (§4) automatically replaces these field values with `[REDACTED]`. Agent must use this middleware on every logger instance; never `console.log` or `fmt.Println` for security-sensitive data.
- Redaction applies to all log levels (debug, info, warn, error). No exceptions "for local development."

**Never store outside vault:**
- PAN, CVV, Track data in `vcard-svc` Postgres. Vault (`card-vault` service) is the HSM-backed PCI boundary.
- `vcard-svc.card` table has only `token_id` (opaque to vault), `masked_pan` (first 4 + last 4 digits), and `card_holder_name` (for display; pseudonymized on GDPR erasure).

**Never echo in error response:**
- Idempotency-Key value (never bounce it back; use a hash).
- Internal resource IDs, auto-increment sequences.
- SQL query text, stack traces, schema introspection.

**Ops view is masked by default:**
- `GET /v1/ops/cards?user_id=...&reason=...` returns `masked_pan` (e.g., `5375 12** **** 1234`).
- Full PAN reveal is a separate endpoint requiring elevated role + SCA token (specification.md T-09).

### Vault Integration

**SCA mandatory for PAN/CVV reveal:**
- `POST /v1/cards/:id/reveal` requires `X-SCA-Token` header with valid OTP token from `auth-svc`.
- No bypass path "for dev" or "for testing." Use test SCA tokens from mock `auth-svc` instead.
- Vault errors (timeout, authentication failure) → 503 `VAULT_UNAVAILABLE`, never fallback to cached plaintext.

**mTLS to vault:**
- TLS 1.3 minimum. Certificate pinning enforced (agent must not add a flag to skip verification).
- Vault calls wrapped in retry logic: 3 retries with exponential backoff (base 1s, max 2s), then fail with 503.

### Migrations

**Forward-only, no rollback scripts in production code:**
- Each migration is a separate `.sql` file, numbered sequentially (001, 002, etc.).
- Migration up: alter table, add column, create index, update data — all in one file.
- If rollback is needed: write a *compensating* migration (e.g., `002_add_column.sql`, then later `015_remove_column.sql`). Do not execute rollback in production.
- Migrations must be idempotent: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`.

### RBAC

**Roles enforced at service boundary (HTTP middleware):**
- Roles: `user`, `ops`, `fraud`, `admin`.
- Middleware checks JWT `role` claim before handler execution.
- Users access only their own cards (FK via `user_id` in JWT). Ops/fraud/admin access all with audit.
- Every handler that differs by role must explicitly check role (no implicit inheritance).
- Audit event includes `actor_role` (user/ops/fraud/system).

### Idempotency

**Idempotency-Key is not logged or persisted beyond Redis TTL:**
- Extract from HTTP header; check Redis cache; do NOT log the raw key value (privacy).
- Do NOT store in Postgres. Redis TTL 24h is the retention window.

---

## 7. How the Agent Treats Edge Cases

The agent must handle these patterns explicitly — never silently ignore, swallow, retry internally, or fail with 500. Reference specification.md §9 (Edge Cases) for full matrix.

### State & Status Transitions

**Unknown or invalid state transitions:**
- Freeze on `pending` → 409 `INVALID_STATE_TRANSITION` (not 400, not 403).
- Unfreeze on `cancelled` → 409 `INVALID_STATE_TRANSITION`.
- Cancel on `pending` → 409 `INVALID_STATE_TRANSITION` (must transition to `active` or `frozen` first).
- Response includes `current_state` field to help client debug.

**Idempotent state changes:**
- Freeze on already-frozen card → 200 (idempotent); do NOT emit a new `CARD_FROZEN` event.
- Unfreeze on already-active card → 200 (idempotent); do NOT emit a new `CARD_UNFROZEN` event.

**Terminal state:**
- Card in `cancelled` state cannot transition back. Any operation on cancelled card → 409 `TERMINAL_STATE` (except query operations like GET, audit events, erasure).

### Idempotency

**Idempotency mismatch:**
- Same key + different request body → 422 `IDEMPOTENCY_MISMATCH` (not 409, not 200). Include `previous_body_hash` in response so client can debug.

**Concurrent requests with same key:**
- First request proceeds. Concurrent duplicates wait (Redis SET NX + backoff) and return the first request's cached response (atomic).
- If first request fails, waiting requests do NOT retry; they get the error response (no automatic retry of failed operations).

**Missing idempotency key:**
- POST/PUT/PATCH without `Idempotency-Key` header → 400 `MISSING_HEADER` (not 411 Length Required).
- GET requests do not require key (they are naturally idempotent).

### Authorization & Limits

**Version conflict (optimistic lock):**
- Client retries with fresh GET. Do NOT retry internally. Return 409 with `current_version` in response.
- Concurrent freeze + unfreeze on same card: one succeeds (version increments), other gets 409. Both generate audit events (separate timestamps), or the second one fails and generates no event (depends on implementation).

**Limit below current spend:**
- User sets daily limit to 500 UAH; already spent 600 UAH today → accept the change (200). Next authorization > 500 UAH is declined. Do NOT reject the limit-update request.

**Currency mismatch on limit:**
- Limit in EUR, card in UAH → 400 `CURRENCY_MISMATCH` (validation error). Limits must match card currency.

**Card state check in authorization:**
- Card in `pending` → decline as `CARD_NOT_READY`.
- Card in `frozen` → decline as `CARD_FROZEN`.
- Card in `cancelled` → decline as `CARD_CANCELLED`.
- All three generate `AUTH_DECLINED` audit event.

### Vault

**Vault timeout on create:**
- Persist card in `pending` status. Return 202 with `retry_after: 30` header. Do NOT block card creation.
- Emit `CARD_CREATION_DEFERRED` audit event.

**Vault timeout on cancel:**
- Retry with exponential backoff (3 attempts). If all fail, persist card in `pending_cancellation` state, emit `CARD_CANCELLATION_DEFERRED` event, alert ops.

**Vault unavailable on reveal:**
- Return 503 `VAULT_UNAVAILABLE`. Do NOT fall back to cached plaintext PAN.

### Transactions & Holds

**Authorization hold expires before capture:**
- Transaction state transitions to `expired` (system-driven, no audit event needed).
- Amount removed from daily/monthly spent totals (next authorization sees lower balance).

**Reverse on already-reversed transaction:**
- Idempotent: return 200, do not emit new `TRANSACTION_REVERSED` event. Log it (no audit event) for debugging.

### Pagination & Cursors

**Tampered pagination cursor:**
- Cursor is base64(HMAC-signed `(authorized_at, transaction_id)`). Agent must validate HMAC.
- Tamper detected → 400 `INVALID_CURSOR` (not 401, not 403). Never leak data or crash.

**Empty result set:**
- Card with no transactions: return 200 with `{ transactions: [], next_cursor: null }` (not 404).

**Cursor validation:**
- Invalid base64 → 400 `INVALID_CURSOR`.
- Missing HMAC signature or mismatched → 400 `INVALID_CURSOR`.

### GDPR & Retention

**Early erasure request (<7 years after cancellation):**
- Return 409 `RETENTION_LOCK` with `retention_expires_at` in response.

**Erasure idempotency:**
- Running GDPR erasure job twice on same card (or manual re-run) → idempotent (no error, no-op on second run).

### Audit & Compliance

**Audit chain break (tampered event):**
- `audit-svc` detects mismatch during replay verification. Emits alert `VCardAuditChainBreak` (SEV-1).
- `vcard-svc` does NOT detect; responsibility on `audit-svc` (consumer of Kafka events). However, on `card_event` write, agent must compute hash and store it (immutability enforced).

**Reason-of-access for ops:**
- Ops search without `reason` query param → 400 `REASON_REQUIRED`.
- `reason` field is NOT redacted in audit payload (it's the ops officer's responsibility; they understand the implications).

---

## 8. Allowed and Forbidden Actions

### Agent May Freely

- Scaffold new files in `internal/`, `transport/http/`, `migrations/`, `tests/`.
- Write tests before implementation (TDD strongly encouraged).
- Propose new database indexes (with performance justification in commit message).
- Update `openapi/vcard.yaml` when adding endpoints, and generate/update types from spec.
- Add structured log lines using the redaction-aware logger; log at appropriate levels (debug, info, warn, error).
- Refactor internal implementation (rename functions, reorganize packages) as long as public API and behavior remain unchanged.
- Optimize queries (add WHERE clause, index, denormalize) and rerun integration tests to verify correctness.

### Agent Must Ask Before

- Adding a new external dependency (`go.mod`, `package.json`). State the dependency, version, and why. Especially: cryptographic libraries, OAuth libraries, or anything that touches security.
- Changing the card state machine (requires ADR in `docs/adr/`).
- Changing error `code` enum values (breaking API change; notify clients).
- Modifying a migration file that has already been applied to a deployed environment (never rewrite history; write compensating migration instead).
- Adding a new Postgres table (clarify purpose, data retention, indexes).
- Changing performance SLOs (§10 in specification.md). If proposed optimization changes latency guarantees, escalate.

### Agent Must Never

- Hardcode secrets, API keys, signing keys, vault URLs. Use environment variables or secure config store.
- Disable linters without specific rule name and documented reason. Example: `nolint:gosec // vault mTLS enforces authentication, skip cert-verification lint` (but do NOT skip cert verification in code itself).
- Weaken CI gates (skip the no-PAN grep gate, lower coverage thresholds, disable Spectral linting).
- Use `float64` / `float32` for monetary values, even temporarily "for now" or "for prototyping."
- Call external networks (vault, auth-svc, notification-svc, Kafka) in unit tests. Mock them.
- Run `git push`, `git commit`, `gh pr create` — submission is the orchestrator's job.
- Generate seed data with realistic-looking PANs. Use well-known test BINs only (`4111111111111111` masked as `4111 11** **** 1111`).
- Add features not in `specification.md` (no "nice-to-haves"). Flag missing requirements in code comments or escalate; do not silently add them.
- Commit `.env` files, `node_modules/`, `.venv/`, `__pycache__/`, `.idea/`, build artifacts.
- Leave commented-out code, TODO/FIXME markers, or test/debug logging in committed files.

---

## 9. Prompt Patterns

When the orchestrator delegates a task to the agent, use these patterns for best results.

### For Implementation Tasks

```
Implement T-xx: [task name from specification.md].

Acceptance criteria:
- [paste criteria from spec]

Files to create/modify:
- [list from spec]

Do not add features beyond the acceptance criteria. 
Run lint + type-check + tests before reporting done.
Report: files created/modified, any non-obvious implementation decisions, test results.
```

### For Review Tasks

```
Review [file/function] against:
- specification.md §[section] for domain correctness
- agents.md §6 for security compliance  
- agents.md §7 for edge case handling

Report: issues found (with severity: critical/major/minor), suggestions, verdict (approve / request changes).
```

### For Debugging Tasks

```
Debug [symptom] in [file].

Current behavior: [what happens]
Expected behavior: [what should happen]
Hypothesis: [what you think is wrong]

Do not refactor surrounding code — fix the specific bug only.
Report: root cause, fix applied, test to verify.
```

### For Optimization Tasks

```
Optimize [operation] to meet SLO of [target].

Current latency: [measured p95]
Target latency: [from spec §10]
Constraints: [DB reads, network calls, etc.]

Preserve correctness; optimize implementation.
Report: changes made, new latency (k6 or integration test), if SLO met.
```

---

## 10. Escalation Protocol

Agent must stop and surface the conflict (do not silently "fix" it) when:

1. **Task conflicts with NFR:** e.g., "implement PAN logging for debug" conflicts with NFR-1 (security). Escalate; do not add bypass.

2. **Task requires new card state not in machine:** e.g., "add `dormant` state for inactive cards." State machine is closed (specification.md §3, rule 4). Escalate; do not extend without ADR.

3. **Task asks to skip idempotency validation "for this endpoint":** e.g., "GET /internal/admin/debug does not need Idempotency-Key." All non-GET endpoints require it (specification.md §3, rule 12). Escalate; do not create exception.

4. **Task would use float for money:** Even temporary "for intermediate calculations." Integer arithmetic only (§3, rule 1). Escalate; do not rationalize.

5. **Dependency introduces PCI-DSS scope expansion:** e.g., "add logging library that sends data to external analytics." Verify scope; if it leaks card data outside vault boundary, escalate.

6. **Two tasks have conflicting acceptance criteria:** e.g., T-05 says "return masked PAN"; T-18 says "return full PAN in search." Clarify intent with orchestrator.

7. **Task requires changes to already-deployed migration:** e.g., "alter the `card` table from T-01." Cannot rewrite history; must write compensating migration. Clarify strategy.

8. **Task requires modifying error codes:** e.g., "rename `CARD_FROZEN` to `FREEZE_STATUS`." Breaking change to clients. Escalate; discuss migration path (support both codes temporarily).

### Escalation Format

```
ESCALATION: [short description, one line]

Conflict: [what the task asks] vs [which rule / NFR / spec section it violates]

Options:
  A. [option that complies fully — may require more work]
  B. [option that violates a rule — needs justification / ADR]
  C. [third option, if any]

Recommendation: [A / B / C, with brief rationale]

Waiting for orchestrator decision.
```

---

## 11. Cross-Cutting Verification

### No-PAN CI Gate

Build includes:
```bash
# Fail if test PANs found in logs/output
grep -r '4111111111111111\|5555555555554444\|6011111111111117' /tmp/logs /app/output && exit 1 || exit 0
```

Test suite includes a log-capture test that verifies no PAN appears at any log level. If redaction middleware is removed, test fails.

### Audit Chain Replay

Daily job (or on-demand):
1. Start from first `card_event` for a given `card_id`.
2. Compute `event_hash` for each row: SHA-256(event_id + "|" + event_type + "|" + actor_id + "|" + payload_json + "|" + prev_hash).
3. Compare computed hash to stored `event_hash`.
4. Mismatch → alert `VCardAuditChainBreak` (SEV-1), investigate manually.

Manual procedure documented in `docs/runbook.md` (specification.md T-24).

### Reconciliation Check

Nightly job:
```sql
SELECT SUM(amount) AS spent_total
FROM transaction
WHERE card_id = $1 AND status = 'captured' AND EXTRACT(YEAR-MONTH FROM captured_at) = CURRENT_YEAR_MONTH;

SELECT total_spent
FROM card_monthly_summary
WHERE card_id = $1 AND year_month = CURRENT_YEAR_MONTH;
```

If variance > 1 minor unit (rounding tolerance), alert SEV-2, report variance per card.

---

## 12. Example: How Agent Applies Rules in Practice

**Scenario:** Task T-05 (create card). Agent receives:
> "Implement POST /v1/cards to create a virtual card. Call vault to tokenize, persist card, return masked PAN."

**Agent's process:**
1. Read specification.md §8 (T-05 details): flow steps, response shape, error handling.
2. Check agents.md §3 (domain rules): PAN never logs, vault timeout → persist as pending, idempotency required.
3. Check agents.md §4 (code style): handler layer calls service layer, service returns typed error, handler maps to RFC 7807.
4. Check agents.md §5 (testing): write unit test + integration test (with real Postgres, mocked vault).
5. Check agents.md §6 (security): use redaction logger, never store PAN in DB, validate vault URL from env.
6. Check agents.md §7 (edge cases): EC-01 (vault timeout on create), EC-02 (concurrent create + freeze).
7. Implement:
   - `transport/http/card_handler.go`: `Create(w http.ResponseWriter, r *http.Request)` — decodes request, calls `CardService.CreateCard`, encodes response.
   - `internal/cards/create.go`: `CreateCard(ctx context.Context, req CreateCardRequest) (*Card, error)` — business logic: check idempotency, call vault, persist card, emit audit event.
   - `internal/db/card_model.go`: `Card` ORM model with columns (no PAN).
   - `migrations/001_create_card.sql`: card table schema.
   - `internal/cards/create_test.go`: unit tests (mock vault, mock DB), integration test (real testcontainers Postgres + mocked vault).
8. Verify: lint, type-check, unit tests pass (>80% coverage), integration tests pass, k6 baseline scenario < 600ms p95.
9. Report: files created, implementation decisions (e.g., "used Redis for idempotency cache per NFR-5"), test results.

---

## 13. FAQs & Anti-Patterns

**Q: Can I add a feature not in the spec "just because it's useful"?**
A: No. Flag it in a code comment or escalate. Do not silently add features. Spec is the contract.

**Q: What if a test fails due to timing? Can I retry or add sleeps?**
A: Do not use `time.Sleep` or arbitrary retries. Investigate the root cause: is the SLO realistic? Is the test flaky? Fix the underlying issue.

**Q: Can I use a string to store money amounts for flexibility?**
A: No. Never. Use `int64` minor units. If clients need formatted output, format on egress.

**Q: What if vault is down? Can I use a fallback PAN cache?**
A: No. Return 503 `VAULT_UNAVAILABLE`. Do not fall back to cached plaintext. Clients will retry.

**Q: Can I add a "debug mode" that logs PANs?**
A: No. There is no debug mode. Redaction middleware applies everywhere. If debugging is needed, use structured logs with redaction + grep by trace_id.

**Q: The spec says "within 500ms" for audit events. Can I batch them to improve throughput?**
A: No. Individual event latency < 500ms. Batching would increase latency. Use async/outbox pattern instead (event stored immediately, Kafka publish async).

**Q: What if I find a security bug in the spec? Should I fix it?**
A: No. Escalate (§10). Do not silently change behavior.

**Q: Can I use a different ORM (SQLAlchemy, Prisma) than the spec assumes?**
A: Not in the primary codebase. If a task specifies Go, use `database/sql` or `sqlc`. If TS, use TypeORM or Prisma if the orchestrator says so. Agent should ask if unclear.

**Q: The spec says "no-PAN grep gate." Can I just comment it out for local testing?**
A: No. If you genuinely need to test PAN-handling logic, use well-known test BINs (e.g., `4111...`), label them in test data, and add them to the grep allowlist with a comment explaining why.

---

## 14. References

- **specification.md:** Domain requirements, tasks T-01..T-24, edge cases, performance SLOs.
- **openapi/vcard.yaml:** REST API contract (authoritative schema source).
- **docs/adr/:** Architecture decision records (new state, breaking changes).
- **docs/runbook.md:** Operational guide, incident response, alert procedures (per T-24).
- **CLAUDE.md (repo root):** Repo-wide guidelines (overrides and scope boundaries for all homeworks).

---

## Final Checklist for Agent Session

Before starting work on any task:

- [ ] Read this file (`agents.md`) once.
- [ ] Read `specification.md` §8 for task details.
- [ ] Read `specification.md` §9 (edge cases) relevant to the task.
- [ ] Read `specification.md` §10 (performance SLOs) to understand latency targets.
- [ ] Check existing code in `internal/` for patterns and conventions.
- [ ] Write a brief implementation plan (files to create, dependencies, edge cases).
- [ ] Implement, test, and verify.
- [ ] Report back with files modified, decisions made, test results.

---

End of agents.md.
