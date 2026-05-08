# Virtual Card Service — Claude Code Project Rules

> These rules apply when Claude Code is working inside the `vcard-svc` project. Read `../specification.md` for domain requirements and `../agents.md` for full agent guidelines. These rules are a concise, Claude-specific subset with additional IDE-level guidance.

## 1. Project Context

This is `vcard-svc`, a hypothetical Monobank-style virtual payment card service for a regulated UA/EU neobank. It implements card lifecycle (create, freeze/unfreeze, cancel), spending limits, transaction history, and audit trail. The system operates in a PCI-DSS and GDPR-regulated environment. Rules in this file reflect that context and cannot be relaxed for development convenience.

## 2. Package & File Structure

Expected directory tree:

```
vcard-svc/
├── cmd/server/main.go           # entrypoint
├── internal/
│   ├── cards/                   # card lifecycle domain
│   ├── limits/                  # limits evaluation + handlers
│   │   └── evaluate.go          # pure function, no I/O
│   ├── transactions/            # transaction read model
│   ├── audit/                   # event emitter + hash chain
│   ├── fraud/                   # fraud flag + velocity rules
│   ├── vault/                   # card-vault client (PCI boundary)
│   ├── idem/                    # idempotency middleware + store
│   ├── money/                   # integer money arithmetic
│   ├── logger/                  # PII-safe structured logger
│   ├── middleware/              # HTTP middleware (auth, RBAC, idem)
│   ├── jobs/                    # scheduled jobs (GDPR erasure)
│   └── db/                      # DB connection, migrations runner
├── transport/
│   └── http/                    # HTTP handlers (thin layer only)
├── migrations/                  # forward-only SQL migrations
├── openapi/
│   └── vcard.yaml               # OpenAPI 3.1 source of truth
├── tests/
│   └── load/vcard.js            # k6 load test plan
├── docs/
│   ├── adr/                     # Architecture Decision Records
│   └── runbook.md
└── deploy/
    └── alerts/vcard.rules.yaml  # Prometheus alert rules
```

## 3. Naming Conventions

**Go packages** (lowercase, no underscores):
- `internal/cards`, `internal/limits`, `internal/transactions`, `internal/audit`, `internal/fraud`, `internal/vault`, `internal/idem`, `internal/money`, `internal/logger`, `transport/http`

**Go types** (PascalCase):
- `Card`, `CardState`, `CardStatus`, `Limit`, `LimitType`, `LimitWindow`, `Transaction`, `AuthDecision`, `AuditEvent`, `FraudFlag`

**Go errors** (`Err` prefix):
- `ErrCardFrozen`, `ErrCardCancelled`, `ErrVersionConflict`, `ErrIdempotencyMismatch`, `ErrLimitExceeded`, `ErrSCARequired`

**DB tables** (snake_case singular):
- `card`, `card_limit`, `card_event`, `transaction`, `outbox`, `fraud_flag`

**Redis key namespaces**:
- `vcard:idem:{user_id}:{method}:{path}:{key}` — idempotency
- `vcard:card:{card_id}` — card state cache (TTL 5s)
- `vcard:reveal:{token}` — reveal token (TTL 60s, single-use)

**File names**: match primary export (e.g., `evaluate.go` for `EvaluateLimits`, `emitter.go` for `EmitEvent`). Test files: `evaluate_test.go`.

**Kafka topics**:
- `vcard.events.v1` — all card lifecycle events
- `vcard.fraud.v1` — fraud escalations

## 4. Patterns to Use

1. **Repository pattern for DB access**: `internal/cards/repository.go` with interface `CardRepository`; implementation in `internal/db/pg_card_repo.go`. Inject via constructor.

2. **Service layer for orchestration**: `internal/cards/service.go` with `CardService` struct. No DB calls in HTTP handlers.

3. **Pure function for limits engine**: `internal/limits/evaluate.go` exports `EvaluateLimits(card Card, limits []Limit, spent SpentTotals, req AuthRequest, clock Clock) AuthDecision`. Zero I/O, no global state, injectable clock for tests.

4. **Outbox pattern for Kafka**: State change + outbox row in single DB transaction. Background `OutboxPublisher` reads and emits. This means Kafka failures never roll back DB state.

5. **Optimistic locking**: `UPDATE card SET status=$1, version=version+1 WHERE card_id=$2 AND version=$3`. On 0 rows affected — fetch current version — return 409 `VERSION_CONFLICT`.

6. **Clock interface for testability**:
   ```go
   type Clock interface { Now() time.Time }
   type RealClock struct{}
   func (RealClock) Now() time.Time { return time.Now().UTC() }
   ```
   Inject in all services that depend on time.

7. **RFC 7807 error type**:
   ```go
   type ProblemDetail struct {
       Type   string `json:"type"`
       Title  string `json:"title"`
       Status int    `json:"status"`
       Detail string `json:"detail"`
       Code   string `json:"code"`
   }
   ```

8. **RBAC middleware**: check JWT role claim before handler. Do not duplicate role checks inside service layer — trust middleware.

## 5. Patterns to Avoid

1. **No ORM magic relationships or lazy loading.** Write explicit SQL or use a lightweight query builder (sqlx, pgx). No GORM, no Ent.

2. **No floats for money.** `float64`, `float32`, `decimal.Decimal` (unless it wraps integer arithmetic) are all forbidden. Use `int64` minor units.

3. **No string concatenation for SQL.** Always use parameterized queries (`$1`, `$2`). Never `fmt.Sprintf("WHERE id = " + id)`.

4. **No global singletons constructed at import time.** Database pools, Redis clients, Kafka producers — all injected via constructor or `main.go` wiring.

5. **No new card states without an ADR.** The FSM (`pending → active → frozen ↔ active → cancelled`) is closed. Proposing a new state requires `docs/adr/XXX-new-state.md` merged first.

6. **No `any` / `interface{}` in domain types.** Use typed structs. Reserve `json.RawMessage` only for `payload` fields explicitly marked in spec.

7. **No `time.Now()` calls inside business logic.** Use injected `Clock` interface.

8. **No direct Kafka calls from service layer.** Write to outbox table; let publisher handle emission.

9. **No test assertions using `require` without import alias** (Go). Use `assert` for non-fatal, `require` for fatal — be intentional.

10. **No down migrations in production code.** Write compensating migrations. If rollback is needed, write `00X_revert_*.sql` going forward.

## 6. FinTech-Sensitive Defaults

These defaults apply unless `specification.md` explicitly says otherwise:

| Concern | Default |
|---------|---------|
| Idempotency | Required on all POST/PUT/PATCH; middleware enforced |
| Money storage | `int64` minor units + `CHAR(3)` currency |
| Rounding | Banker's rounding (HALF_EVEN) |
| PAN/CVV | Never outside `internal/vault/` boundary |
| Logging | PII-safe logger from `internal/logger`; no raw `fmt.Println` |
| Auth decline push | Fire-and-forget; never block the auth response |
| Reveal token TTL | 60 seconds, single-use |
| Idempotency cache TTL | 24 hours |
| Card cache TTL | 5 seconds |
| Authorization response | p95 < 80ms target (T-12) |
| Ops access | Requires `reason` param; emits audit event |
| Audit events | Append-only; never UPDATE or DELETE `card_event` |
| DB migrations | Forward-only; no `DROP COLUMN` on live data |
| Error format | RFC 7807 `application/problem+json` |
| Currency | `CURRENCY_MISMATCH` decline on auth if currencies differ |
| Concurrent updates | 409 `VERSION_CONFLICT` — do not retry internally |

## 7. PR & Commit Rules

- **Conventional commits**: `type(scope): description`. Scopes: `cards`, `limits`, `tx`, `audit`, `fraud`, `vault`, `idem`, `money`, `logger`, `ops`, `jobs`, `migrations`, `openapi`, `ci`.
- **PR description must reference task IDs**: e.g., "Implements T-05 (card creation) and T-17 (audit emitter)."
- **PR description must reference mid-level objectives**: e.g., "Satisfies MO-1 (card visible within 2s) and MO-6 (audit event within 500ms)."
- **PR size**: target < 400 LOC diff. Split large tasks into multiple PRs if needed.
- **Never merge without CI green**: lint, type-check, unit tests, integration tests, contract lint, no-PAN grep gate must all pass.
- **No `--no-verify` commits**: if a pre-commit hook fails, fix the underlying issue.

## 8. What Claude Must Not Auto-Do

1. **Do not generate seed data with real-looking PANs.** Use `4111 1111 1111 1111` (Visa test BIN) for all test fixtures. Display as masked: `4111 11** **** 1111`.

2. **Do not run migrations against shared environments** (staging, production) — only against the local dev database or testcontainers.

3. **Do not add new dependencies without listing them in the PR description** with the reason, the alternative considered, and the license.

4. **Do not add a "development bypass" for SCA** on PAN reveal. Use the mock `auth-svc` with test OTP tokens instead.

5. **Do not add rate limiting** unless explicitly in `specification.md`. It is not in the current spec.

6. **Do not auto-generate a `down` migration** when asked to create a migration. Generate the forward migration only.

7. **Do not commit directly to `main`** — all changes via PR.

8. **Do not add `console.log` / `fmt.Println` debug lines** in committed code. Use `internal/logger`.

9. **Do not write speculative tests** for code that was not requested in the current task.

10. **Do not silence linter warnings** without explicit permission from the orchestrator and a code comment explaining why.

## 9. References

- `../specification.md` — source of truth: domain requirements, task IDs (T-xx), NFRs (NFR-xx), edge cases (EC-xx)
- `../agents.md` — full agent guidelines (superset of this file)
- `openapi/vcard.yaml` — REST API contract (generate types from here)
- `docs/adr/` — Architecture Decision Records (must exist before state machine changes)
- `docs/runbook.md` — operational runbook (see T-24)
