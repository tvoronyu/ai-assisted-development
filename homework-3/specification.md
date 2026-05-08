# Virtual Card Lifecycle — Specification

> Ingest the information from this file, implement the Low-Level Tasks, and generate the code that will satisfy the High and Mid-Level Objectives.

## 0. Document Conventions

- **Money**: Stored as `int64` minor units + ISO-4217 currency code; never float; formatted on egress only (e.g. `1050` UAH → "10.50 ₴").
- **IDs**: ULID for resources (cards, limits), UUIDv7 for events; opaque to clients.
- **Timestamps**: RFC 3339 UTC everywhere; card limit windows evaluated in user's registered timezone (stored as IANA tz string).
- **Traceability notation**: mid-level objectives `MO-x`, low-level tasks `T-xx`, NFRs `NFR-xx`, edge cases `EC-xx`.
- **Error codes**: Stable string enums (e.g. `CARD_FROZEN`, `LIMIT_EXCEEDED`); never expose internal stack traces.
- **Monetary operations**: Use banker's rounding (HALF_EVEN).

---

## 1. High-Level Objective

Allow a Monobank-app user to create, control, and audit a virtual payment card end-to-end, while providing ops/compliance and fraud teams with the visibility and controls required in a regulated EU/UA neobank environment.

**Scope boundary:**
- **In scope**: Card lifecycle (create, freeze, unfreeze, cancel), spending limits (daily/monthly/per-merchant/per-MCC/geographic), transaction history with pagination, audit trail.
- **Out of scope**: Card issuing rails (BIN sponsor integration), KYC/AML onboarding, foreign-exchange engine, dispute intake, 3DS challenge UI.

---

## 2. Stakeholders & Personas

| Persona | Role | Primary Goals |
|---------|------|---------------|
| **Cardholder (end-user)** | Creates and controls their own virtual cards via mobile app | Quick card creation, control limits, view transaction history, PAN reveal for manual payment |
| **Ops/Compliance Officer** | Searches, views (masked), and freezes cards with mandatory reason-of-access logging | Visibility into card activity, audit trail integrity, frozen-card reporting |
| **Fraud Analyst** | Flags suspicious cards triggering auto-freeze and user notification; reviews velocity alerts | Rapid card suspension, escalation workflow, velocity metrics |
| **Internal Services (non-human)** | `ledger-svc` (authorization hook consumer), `notification-svc` (push delivery), `audit-svc` (event consumer), `card-vault` (PAN/CVV storage, PCI-DSS boundary) | Reliable integration, minimal latency, no PII leakage |

---

## 3. Mid-Level Objectives

| ID | Objective | Observable Signal | Owning Persona(s) |
|----|-----------|-------------------|-------------------|
| MO-1 | Cardholder can create a virtual card and see it in the app | Card appears in `GET /v1/cards` within 2 seconds | End-user |
| MO-2 | Freeze/unfreeze takes effect on the next authorization attempt | Authorization declined if frozen; succeeds if unfrozen | End-user |
| MO-3 | Cardholder can configure daily, monthly, per-merchant, per-MCC, and geographic limits with immediate effect | Limit change → next auth evaluated against new limit | End-user |
| MO-4 | Cardholder can browse paginated transaction history with filters by status, date range, and MCC | Paginated list returned with cursor; filter params working | End-user |
| MO-5 | Card can be permanently cancelled with a reason code; history is preserved for 7 years | Card status = `cancelled`; transactions still queryable; event log intact | End-user, Compliance |
| MO-6 | Every state-changing action produces an immutable, hash-chained audit event within 500ms | `card_event` row inserted; `prev_hash` validates chain; latency < 500ms | Compliance |
| MO-7 | Ops can search any user's cards with masked PAN, with mandatory access-reason recording | Search endpoint returns masked cards; access reason logged as audit event | Ops/Compliance |
| MO-8 | Fraud analyst can flag a card, triggering auto-freeze and a "Was this you?" push to the user | Card frozen; `FRAUD_FLAGGED` event emitted; push notification sent | Fraud |
| MO-9 | PAN and CVV never leave the card-vault boundary in plaintext | PAN/CVV absent from application logs, DB (outside vault), analytics | Security/Compliance |
| MO-10 | All monetary calculations are exact and reproducible using integer arithmetic | Spent totals match sum of transactions; no floating-point rounding errors | Compliance |

---

## 4. Non-Functional & Policy Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Security | PAN/CVV tokenized at vault; AES-256-GCM at rest; TLS 1.3 in transit; PCI-DSS SAQ-D scope minimized by vault boundary; no PAN/CVV in logs, DB (outside vault), analytics, or error bodies. |
| NFR-2 | Privacy | GDPR Article 17 — cards cancelled >7 years trigger erasure job (transaction amounts retained in aggregate, PII pseudonymized). Ops view shows masked PAN `5375 12** **** 1234` by default; full reveal requires elevated role + audit event. |
| NFR-3 | Audit | Append-only `card_event` table; each row includes `prev_hash` (SHA-256 of previous row); chain integrity checked on read by `audit-svc`; retained 7 years per UA NBU operational risk requirements. |
| NFR-4 | Reliability | 99.95% monthly availability target (≤22min downtime/month); RTO 15min, RPO 1min; card-vault calls have 5s timeout + 2 retries with exponential backoff. |
| NFR-5 | Idempotency | All non-GET endpoints require `Idempotency-Key` header; dedupe key = `(user_id, endpoint, idempotency_key)`; replay window 24h; mismatched body on same key → 422 `IDEMPOTENCY_MISMATCH`. |
| NFR-6 | Performance | See §10. |
| NFR-7 | Authorization | RBAC (roles: `user`, `ops`, `fraud`, `admin`) + ABAC (users may only access own cards; ops/fraud access all with audit); step-up auth (SCA via OTP) required for PAN/CVV reveal. |
| NFR-8 | Observability | Structured JSON logs with `trace_id`; RED metrics (rate, errors, duration) per endpoint exported to Prometheus; alert on `auth_decline_rate > 20%` over 5min and `audit_chain_break`. |
| NFR-9 | Compliance | PSD2 Article 97 SCA for PAN reveal; PCI-DSS SAQ-D card data flow documented; UA NBU operational risk reporting hooks via `audit-svc`; GDPR data-processing register entry for card data. |
| NFR-10 | Monetary Precision | All monetary values stored as `int64` minor units; no `float`/`double` anywhere in business logic; spent totals must equal `SUM` of individual transaction amounts with zero variance; banker's rounding (HALF_EVEN) on any rounding operation. |

---

## 5. Implementation Notes

- **Money**: Store as `int64` minor units + `char(3)` ISO-4217. Never `float` or `double`. Format on egress via locale-aware formatter. Banker's rounding (HALF_EVEN) on any rounding operation.
- **IDs**: ULID for `card_id`, `limit_id`; UUIDv7 for `event_id`, `transaction_id`. Never auto-increment integers for security-sensitive resources.
- **Card state machine**: `pending → active → frozen ↔ active → cancelled`. `cancelled` is terminal. No direct `pending → cancelled` without `active` intermediate if vault succeeds.
- **Transaction states**: `authorized → captured | reversed | expired`. `declined` is a separate event, not a state. Authorization hold expires per MCC (7 days retail, 30 days travel).
- **Limits evaluation order**: (1) card-status check → (2) geographic blocklist → (3) per-merchant blocklist → (4) online-only flag → (5) per-MCC cap → (6) per-transaction max → (7) daily rolling total → (8) monthly calendar total. First deny wins. Reason code reflects the first failing check.
- **Idempotency**: Dedupe store in Redis with key `vcard:idem:{user_id}:{endpoint}:{idempotency_key}` → serialized response; TTL 24h. Check before processing; store after successful response.
- **Errors**: RFC 7807 `application/problem+json`: `type` URI, `title`, `status`, `detail`, `code` (stable enum). Never expose stack traces or internal IDs in error body.
- **Time**: Server is single source of truth for timestamps. Reject client-supplied timestamps for state changes. Limit windows (daily/monthly) evaluated in user's stored IANA timezone.
- **Concurrency**: Optimistic locking on `cards.version` and `card_limits.version`. Failing update → 409 `VERSION_CONFLICT`; client retries with fresh `GET`.
- **Webhook / event ordering**: Events are published to Kafka `vcard.events.v1` in order; consumers must handle out-of-order delivery using `event_seq` + `prev_hash` chain.
- **PII redaction**: All logging passes through shared redaction middleware with `redact: ['pan', 'cvv', 'card_holder_name', 'track2', 'expiry', 'full_card_number']`.
- **Outbox pattern**: State changes write to DB `outbox` table in same transaction; async publisher reads outbox and emits to Kafka. No dual-write.

---

## 6. Context — Beginning State

Hypothetical existing services:
- **`auth-svc`**: Issues JWT + SCA OTP tokens; exposes `POST /sca/challenge` and `POST /sca/verify`.
- **`user-svc`**: User profiles, registered IANA timezone, KYC status; exposes gRPC `GetUser`.
- **`ledger-svc`**: Processes authorizations; calls `POST /internal/authorize` on `vcard-svc`.
- **`notification-svc`**: Push notifications via APNs/FCM; exposes `POST /notify`.
- **`card-vault`**: PCI-DSS HSM-backed; stores PAN/CVV keyed by `token_id`; exposes `POST /tokenize`, `POST /detokenize` (SCA-gated), `DELETE /token/:id`.
- **`audit-svc`**: Append-only event consumer from Kafka `vcard.events.v1`; exposes `GET /events?card_id=`.
- **Postgres `corebank` database**: Existing schemas for users, accounts, transactions.
- **Redis cluster**: Used by auth-svc for session; `vcard-svc` will add namespace `vcard:*`.
- **Kafka 3.6 cluster**: Existing topics.
- **Mobile app**: Has placeholder "Virtual Cards" tab with empty state screen.
- **No `vcard-svc`** exists. No `card`, `card_limit`, `card_event`, `transaction`, `fraud_flag` tables exist.

---

## 7. Context — Ending State

New artifacts after implementation:
- `vcard-svc` deployed (REST API + internal gRPC + Kafka producer via outbox).
- Postgres migrations applied: tables `card`, `card_limit`, `card_event`, `transaction`, `outbox`, `fraud_flag`.
- Redis namespace `vcard:idem:*` for idempotency store.
- Kafka topics created: `vcard.events.v1`, `vcard.fraud.v1`.
- OpenAPI 3.1 spec at `openapi/vcard.yaml` (source of truth for REST API).
- Mobile screens wired: card list, card detail, freeze toggle, limits editor, transaction list, cancel flow, reveal-PAN flow.
- Ops dashboard: card search (by user, status, masked PAN), card detail, freeze action, reason-of-access form.
- Fraud console: velocity alerts feed, flag-card form, escalation view.
- Runbook in `docs/runbook.md`.
- Prometheus alert rules: `VCardAuthDeclineRateHigh`, `VCardAuditChainBreak`, `VCardVaultLatencyHigh`.
- k6 load test plan at `tests/load/vcard.js`.

---

## 8. Low-Level Tasks

### Phase A — Data Layer & Schema (T-01..T-04)

#### T-01: Create `card` table migration

**Traces**: MO-1, MO-5, MO-6

**Prompt**: "Create a Postgres migration that adds the `card` table with all columns needed for virtual card lifecycle management."

**File**: `migrations/001_create_card.sql`

**Function / Class**: n/a (SQL migration)

**Details**: 
- Columns: `card_id ULID PK`, `user_id UUID NOT NULL FK users`, `token_id UUID NOT NULL` (vault reference), `masked_pan CHAR(19) NOT NULL` (e.g. `5375 12** **** 1234`), `card_holder_name VARCHAR(26) NOT NULL`, `currency CHAR(3) NOT NULL`, `status VARCHAR(16) NOT NULL CHECK IN ('pending','active','frozen','cancelled')`, `version INT NOT NULL DEFAULT 0`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL`, `cancelled_at TIMESTAMPTZ`, `cancel_reason VARCHAR(32)`, `timezone VARCHAR(64) NOT NULL`. 
- Indexes: `(user_id, status)`, `(status)`. 
- No PAN column.

**Acceptance Criteria**:
- [ ] Migration runs idempotently via `IF NOT EXISTS`.
- [ ] No `pan` or `cvv` column.
- [ ] `status` constraint enforced at DB level.

---

#### T-02: Create `card_limit` table and defaults seed

**Traces**: MO-3

**Prompt**: "Create a migration for `card_limit` table and a seed for default limits."

**File**: `migrations/002_create_card_limit.sql`

**Function / Class**: n/a

**Details**: 
- Columns: `limit_id ULID PK`, `card_id ULID NOT NULL FK card`, `limit_type VARCHAR(32) NOT NULL CHECK IN ('per_transaction','daily','monthly','per_merchant','per_mcc','geographic')`, `value INT8` (minor units; NULL = unlimited), `currency CHAR(3)`, `scope_key VARCHAR(64)` (merchant_id, MCC code, or ISO-3166 country code), `enabled BOOL NOT NULL DEFAULT TRUE`, `version INT NOT NULL DEFAULT 0`, `updated_at TIMESTAMPTZ NOT NULL`. 
- Unique: `(card_id, limit_type, scope_key)`. 
- Default seed: per_transaction = 50000 UAH (5000000 minor units), daily = 200000 UAH, monthly = 500000 UAH, geographic scope_key = 'UA,EU', online_only = TRUE (as a boolean flag on card, not limit row).

**Acceptance Criteria**:
- [ ] Unique constraint prevents duplicate limit types per card+scope.
- [ ] Seed values match Monobank defaults.

---

#### T-03: Create `transaction` table with indexes

**Traces**: MO-4

**Prompt**: "Create Postgres migration for the `transaction` table optimized for paginated reads by card."

**File**: `migrations/003_create_transaction.sql`

**Function / Class**: n/a

**Details**: 
- Columns: `transaction_id UUIDv7 PK`, `card_id ULID NOT NULL FK card`, `auth_id VARCHAR(64) UNIQUE`, `capture_id VARCHAR(64)`, `status VARCHAR(16) CHECK IN ('authorized','captured','reversed','expired','declined')`, `amount INT8 NOT NULL`, `currency CHAR(3) NOT NULL`, `original_amount INT8`, `original_currency CHAR(3)`, `merchant_id VARCHAR(64)`, `merchant_name VARCHAR(128)`, `mcc CHAR(4)`, `country CHAR(2)`, `network VARCHAR(16) CHECK IN ('visa','mastercard','other')`, `is_recurring BOOL NOT NULL DEFAULT FALSE`, `authorized_at TIMESTAMPTZ NOT NULL`, `captured_at TIMESTAMPTZ`, `hold_expires_at TIMESTAMPTZ`. 
- Indexes: `(card_id, authorized_at DESC)` for pagination; `(card_id, status)` for filtering; `(auth_id)` for authorization lookup.

**Acceptance Criteria**:
- [ ] Query `SELECT * FROM transaction WHERE card_id = $1 ORDER BY authorized_at DESC LIMIT 25` uses index.
- [ ] No `pan` column.

---

#### T-04: Create append-only `card_event` table with HMAC chain

**Traces**: MO-6, MO-8

**Prompt**: "Create migration for `card_event` table that supports an HMAC hash chain for audit integrity."

**File**: `migrations/004_create_card_event.sql`

**Function / Class**: n/a

**Details**: 
- Columns: `event_id UUIDv7 PK`, `card_id ULID NOT NULL FK card`, `event_type VARCHAR(64) NOT NULL` (e.g. `CARD_CREATED`, `CARD_FROZEN`, `LIMIT_UPDATED`, `AUTH_DECLINED`), `actor_id UUID NOT NULL`, `actor_role VARCHAR(16) CHECK IN ('user','ops','fraud','system')`, `payload JSONB NOT NULL`, `prev_hash CHAR(64)` (SHA-256 hex of previous event's hash; NULL for first event per card), `event_hash CHAR(64) NOT NULL`, `event_seq BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY`, `occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()`. 
- Constraint: no UPDATE/DELETE allowed (enforce via trigger or application policy + comment in migration). 
- Index: `(card_id, event_seq ASC)`.

**Acceptance Criteria**:
- [ ] `event_seq` is monotonically increasing.
- [ ] `event_hash` computed as SHA-256(`event_id || event_type || actor_id || payload::text || prev_hash`).
- [ ] Chain can be replayed and verified by `audit-svc`.

---

### Phase B — Card Lifecycle API (T-05..T-09)

#### T-05: POST /v1/cards — create virtual card

**Traces**: MO-1, MO-6, MO-9

**Prompt**: "Implement the create-card endpoint: call card-vault to tokenize, persist card row, emit audit event, return masked card details."

**File**: `internal/cards/create.go` (or `.ts`)

**Function/Class**: `CreateCard(ctx, req) → CardResponse`

**Details**: 
- Request: `{ currency, card_holder_name, idempotency_key }`. 
- Flow: (1) check idempotency cache; (2) call vault `POST /tokenize` → `token_id + masked_pan`; (3) write `card` row in `pending`; (4) transition to `active`; (5) write outbox entry `CARD_CREATED`; (6) store idempotency response; (7) return. 
- Response: `{ card_id, masked_pan, status, currency, created_at }`. 
- On vault failure: persist `pending`, return 202 with `retry_after`. 
- Never return `token_id` to client.

**Acceptance Criteria**:
- [ ] No PAN in response or logs.
- [ ] Duplicate `Idempotency-Key` returns same response.
- [ ] Audit event `CARD_CREATED` emitted within 500ms.
- [ ] Card appears in `GET /v1/cards` immediately after creation.

---

#### T-06: GET /v1/cards and GET /v1/cards/:id

**Traces**: MO-1, MO-7

**Prompt**: "Implement list and detail endpoints for virtual cards."

**File**: `internal/cards/read.go`

**Function/Class**: `ListCards`, `GetCard`

**Details**: 
- `GET /v1/cards` returns user's own cards (filtered by JWT `user_id`); supports `?status=active|frozen|cancelled` filter; returns array of `{ card_id, masked_pan, status, currency, created_at, updated_at }`. 
- `GET /v1/cards/:id` returns same shape + `limits_summary`. 
- Ops role sees any user's cards via `?user_id=`. 
- Ops access without `reason` query param → 400 `REASON_REQUIRED`. 
- Audit event `OPS_CARD_VIEW` emitted for ops access with `reason` in payload.

**Acceptance Criteria**:
- [ ] User cannot access another user's card (403).
- [ ] Ops access without reason → 400.
- [ ] Ops access emits audit event.
- [ ] No token_id in any response.

---

#### T-07: POST /v1/cards/:id/freeze and /unfreeze

**Traces**: MO-2, MO-6

**Prompt**: "Implement freeze and unfreeze endpoints with optimistic locking and audit trail."

**File**: `internal/cards/lifecycle.go`

**Function/Class**: `FreezeCard`, `UnfreezeCard`

**Details**: 
- Freeze: valid from state `active` only; update `status=frozen, version+=1` with `WHERE version=$expected`; emit `CARD_FROZEN`; push notification via `notification-svc`. 
- Unfreeze: valid from `frozen` only; same pattern; emit `CARD_UNFROZEN`. 
- Both require `Idempotency-Key`. 
- Freeze on already-frozen card → 200 idempotent (no new event). 
- Unfreeze on `cancelled` → 409 `INVALID_STATE_TRANSITION`. 
- Response: `{ card_id, status, updated_at }`. 
- Pending authorizations already in flight: not cancelled; will decline on capture if card still frozen at capture time.

**Acceptance Criteria**:
- [ ] Freeze on frozen → 200, no duplicate event.
- [ ] Concurrent freeze+unfreeze → one succeeds, one gets 409 `VERSION_CONFLICT`.
- [ ] Audit event within 500ms.
- [ ] Push notification sent on state change.

---

#### T-08: POST /v1/cards/:id/cancel

**Traces**: MO-5, MO-6

**Prompt**: "Implement card cancellation endpoint. State is terminal; history is preserved."

**File**: `internal/cards/lifecycle.go`

**Function/Class**: `CancelCard`

**Details**: 
- Valid from `active` or `frozen`; not from `cancelled` or `pending`. 
- Request: `{ reason_code: 'USER_REQUEST'|'LOST_STOLEN'|'FRAUD'|'OPS_ACTION' }`. 
- Flow: update `status=cancelled, cancelled_at=now(), cancel_reason, version+=1`; call `card-vault DELETE /token/:token_id`; emit `CARD_CANCELLED` with reason; do NOT delete transaction or event history. 
- Response: `{ card_id, status, cancelled_at, cancel_reason }`. 
- Open authorizations: honored to capture/expiry; new auths declined with `CARD_CANCELLED`.

**Acceptance Criteria**:
- [ ] Cannot transition `cancelled → active/frozen`.
- [ ] Vault token deleted.
- [ ] History preserved (transactions still queryable).
- [ ] Audit event emitted.
- [ ] Open authorized transactions still settle.

---

#### T-09: POST /v1/cards/:id/reveal (PAN + CVV with SCA)

**Traces**: MO-9, NFR-7

**Prompt**: "Implement PAN/CVV reveal endpoint requiring SCA step-up token. Returns single-use time-limited token."

**File**: `internal/cards/reveal.go`

**Function/Class**: `RevealCard`

**Details**: 
- Request header: `X-SCA-Token: <otp_token>`. 
- Flow: (1) validate SCA token with `auth-svc POST /sca/verify`; (2) call `card-vault POST /detokenize` → plaintext PAN + CVV; (3) generate single-use reveal token (UUID, TTL 60s, stored in Redis `vcard:reveal:{token}` → `{ pan, cvv, card_id }`); (4) emit audit event `PAN_REVEALED` with actor; (5) return `{ reveal_token, expires_at }`. 
- Client uses `reveal_token` to fetch PAN/CVV from a separate endpoint `GET /v1/cards/:id/pan?token=` (same 60s TTL, single-use). 
- PAN/CVV NEVER in application logs. 
- Reveal without valid SCA → 401 `SCA_REQUIRED`. 
- Expired SCA → 401 `SCA_EXPIRED`.

**Acceptance Criteria**:
- [ ] No PAN/CVV in logs at any log level.
- [ ] Reveal token is single-use (second GET → 401).
- [ ] Token expires after 60s.
- [ ] Audit event `PAN_REVEALED` emitted with actor_id.

---

### Phase C — Limits & Controls (T-10..T-13)

#### T-10: PUT /v1/cards/:id/limits — update card limits

**Traces**: MO-3, MO-6

**Prompt**: "Implement limits update endpoint with bounds validation and optimistic locking."

**File**: `internal/limits/handler.go`

**Function/Class**: `UpdateLimits`

**Details**: 
- Request: `{ limits: [{ limit_type, value, currency, scope_key, enabled }] }`. 
- Validation: `value >= 0` (0 = block all); `value <= product_ceiling` (per card-product config: per_transaction max 100000 UAH, daily max 500000 UAH, monthly max 2000000 UAH); currency must match card currency. 
- Upsert with `ON CONFLICT (card_id, limit_type, scope_key) DO UPDATE`. 
- Use `version` optimistic lock on each limit row. 
- Emit `LIMIT_UPDATED` per changed limit. 
- If new limit < already-spent daily/monthly total → accept; next auth will decline.

**Acceptance Criteria**:
- [ ] Value below 0 → 400 `INVALID_LIMIT`.
- [ ] Value above ceiling → 400 `LIMIT_ABOVE_CEILING` (ceiling echoed in response).
- [ ] Setting limit below spent total → 200 (no error).
- [ ] Each limit change → audit event.
- [ ] Concurrent updates → 409 on version conflict.

---

#### T-11: Limits evaluation engine (pure function)

**Traces**: MO-3, MO-10

**Prompt**: "Implement a pure, deterministic limits evaluation function that returns an authorization decision."

**File**: `internal/limits/evaluate.go`

**Function/Class**: `EvaluateLimits(card, limits, spent, request) → AuthDecision`

**Details**: 
- Input: card status, list of active limits, spent totals (daily rolling, monthly calendar), auth request (`amount, currency, merchant_id, mcc, country, is_online`). 
- Evaluation order (first deny wins): (1) card status check (`CARD_FROZEN`, `CARD_CANCELLED`); (2) geographic blocklist; (3) per-merchant blocklist; (4) online-only flag; (5) per-MCC cap; (6) per-transaction max; (7) daily rolling total (24h server time); (8) monthly calendar total (user timezone). 
- Returns `{ decision: 'approve'|'decline', reason_code, failing_limit_id? }`. 
- Pure function — no I/O, no side effects, injectable clock.

**Acceptance Criteria**:
- [ ] 100% unit-test coverage.
- [ ] All 8 check types have passing and failing test cases.
- [ ] Concurrent auth requests evaluated independently (no shared mutable state).
- [ ] Same inputs always produce same output.

---

#### T-12: POST /internal/authorize — authorization hook for ledger-svc

**Traces**: MO-3, MO-10

**Prompt**: "Implement internal authorization endpoint called by ledger-svc on every card authorization attempt."

**File**: `internal/limits/authorize_handler.go`

**Function/Class**: `HandleAuthorize`

**Details**: 
- Internal endpoint (mTLS, not exposed publicly). 
- Request: `{ card_id, amount, currency, merchant_id, mcc, country, network, is_recurring, auth_id }`. 
- Flow: (1) load card + limits from DB (cached in Redis `vcard:card:{card_id}` TTL 5s); (2) load spent totals; (3) call `EvaluateLimits`; (4) if approve: write `transaction` row in `authorized` state, update spent counters atomically; (5) if decline: write `card_event` with type `AUTH_DECLINED` + reason; (6) return `{ decision, reason_code, transaction_id? }`. 
- Latency SLO: p95 < 80ms (see §10).

**Acceptance Criteria**:
- [ ] p95 < 80ms under 500 RPS load.
- [ ] Declined auth emits audit event.
- [ ] Spent counters updated atomically (no double-count on retry with same `auth_id`).
- [ ] Currency mismatch → `CURRENCY_MISMATCH` decline.

---

#### T-13: Per-merchant and per-MCC allowlist/blocklist editor

**Traces**: MO-3

**Prompt**: "Implement endpoints for managing per-merchant and per-MCC limit rules."

**File**: `internal/limits/merchant_handler.go`

**Function/Class**: `SetMerchantRule`, `SetMCCRule`

**Details**: 
- `PUT /v1/cards/:id/limits/merchants/:merchant_id` → `{ enabled: bool, max_amount?: int }`. 
- `PUT /v1/cards/:id/limits/mcc/:mcc_code` → `{ enabled: bool, max_amount?: int }`. 
- Stored as `card_limit` rows with `scope_key = merchant_id` or `scope_key = mcc`. 
- Emit `LIMIT_UPDATED`. 
- `GET /v1/cards/:id/limits` returns all limits grouped by type.

**Acceptance Criteria**:
- [ ] Setting `enabled: false` for a merchant blocks all auths from that merchant.
- [ ] Setting `max_amount: 0` for an MCC category blocks all spend in that category.
- [ ] Audit event per change.

---

### Phase D — Transactions & Read Models (T-14..T-16)

#### T-14: GET /v1/cards/:id/transactions — paginated transaction list

**Traces**: MO-4

**Prompt**: "Implement cursor-based paginated transaction list endpoint with filtering."

**File**: `internal/transactions/handler.go`

**Function/Class**: `ListTransactions`

**Details**: 
- Query params: `?status=authorized|captured|reversed|expired`, `?from=ISO8601`, `?to=ISO8601`, `?mcc=XXXX`, `?cursor=<opaque>`, `?limit=25` (max 100). 
- Cursor = base64-encoded `(authorized_at, transaction_id)` — tamper-resistant (HMAC-signed). 
- Response: `{ transactions: [...], next_cursor: string|null, total_pending_amount: int }`. 
- Empty result: `200` with empty array + `null next_cursor`. 
- Each transaction: `{ transaction_id, status, amount, currency, original_amount, original_currency, merchant_name, mcc, country, is_recurring, authorized_at, captured_at, hold_expires_at }`. 
- Pending shown with hourglass flag.

**Acceptance Criteria**:
- [ ] Tampered cursor → 400 `INVALID_CURSOR`.
- [ ] Empty list → 200 (not 404).
- [ ] New card with no transactions → empty array.
- [ ] `limit > 100` → clamped to 100 (not 400).

---

#### T-15: Monthly summary materialized view

**Traces**: MO-4, MO-10

**Prompt**: "Create a materialized view or scheduled job that computes monthly transaction summaries per card."

**File**: `migrations/005_monthly_summary_view.sql`

**Function/Class**: `card_monthly_summary` (materialized view)

**Details**: 
- Materialized view: `card_id, year_month (YYYY-MM), total_spent INT8, transaction_count INT, currency`. 
- Refreshed on schedule (every 5min via pg_cron or app job). 
- Used by limits evaluation for monthly total (authoritative source = live sum for current month; materialized view for display). 
- Include index on `(card_id, year_month)`.

**Acceptance Criteria**:
- [ ] View refresh is idempotent.
- [ ] `total_spent` matches sum of `captured` transactions for the month.
- [ ] Pending (authorized) amounts included in display but not in hard-limit evaluation (policy decision noted in spec).

---

#### T-16: Real-time authorization push notification

**Traces**: MO-4, MO-1

**Prompt**: "Wire authorization outcomes (approve and decline) to notification-svc for instant push delivery."

**File**: `internal/notifications/push.go`

**Function/Class**: `SendAuthNotification`

**Details**: 
- Called after T-12 `HandleAuthorize`. 
- On approve: push `{ title: merchant_name, body: "−{amount} {currency} · Balance: {balance}", data: { transaction_id, type: 'AUTH_APPROVED' } }`. 
- On decline: push `{ title: "Card declined", body: "{reason_localized}", data: { reason_code, type: 'AUTH_DECLINED' } }`. 
- Fire-and-forget (do not block auth response). 
- Include FX info if `original_currency != currency`. 
- Decline reason must be human-readable and localized (Monobank signature: "Card frozen", "Daily limit exceeded").

**Acceptance Criteria**:
- [ ] Push sent within 1.5s of auth outcome (end-to-end p95).
- [ ] Decline reason localized and human-readable.
- [ ] Notification failure does not fail the authorization.
- [ ] FX original amount shown when currency differs.

---

### Phase E — Compliance, Audit & Fraud (T-17..T-20)

#### T-17: Audit event emitter with HMAC hash chain

**Traces**: MO-6, NFR-3

**Prompt**: "Implement the audit event emitter that maintains a hash chain per card for tamper detection."

**File**: `internal/audit/emitter.go`

**Function/Class**: `EmitEvent(ctx, event AuditEvent) error`

**Details**: 
- Fetch latest `event_hash` for the card (or empty string if first event). 
- Compute `event_hash = SHA-256(event_id + "|" + event_type + "|" + actor_id + "|" + payload_json + "|" + prev_hash)`. 
- Write to `card_event` table. 
- Publish to Kafka topic `vcard.events.v1` via outbox. 
- Key rotation: signing key versioned; `event_hash` prefixed with `v{key_version}:`. 
- Chain verification: `audit-svc` can replay from first event and verify each hash.

**Acceptance Criteria**:
- [ ] Hash chain verifiable from first event.
- [ ] Tampered row detectable (different `event_hash`).
- [ ] Key version prefix supports rotation without breaking old chain.
- [ ] Write latency p95 < 50ms.

---

#### T-18: Ops console search endpoint

**Traces**: MO-7, NFR-2, NFR-3

**Prompt**: "Implement ops card search endpoint with mandatory reason-of-access and audit logging."

**File**: `internal/ops/search_handler.go`

**Function/Class**: `SearchCards`

**Details**: 
- `GET /v1/ops/cards?user_id=&status=&masked_pan_suffix=4&reason=<text>`. 
- `reason` is required for ops/fraud roles (400 if missing). 
- Returns: `{ cards: [{ card_id, user_id, masked_pan, status, currency, created_at }], total: int }`. 
- Full PAN reveal in ops view requires separate `POST /v1/ops/cards/:id/reveal` (same SCA + elevated role). 
- Emit `OPS_CARD_SEARCH` event per search with `reason` in payload. 
- Pagination: offset-based for ops (not cursor); default 20, max 50.

**Acceptance Criteria**:
- [ ] Missing `reason` → 400 `REASON_REQUIRED`.
- [ ] Each search emits audit event.
- [ ] Full PAN not returned in search results (masked only).
- [ ] Ops user cannot unfreeze a user-frozen card without user consent (state check: `freeze_actor_role='user'` → 409 `CARDHOLDER_ACTION_REQUIRED`).

---

#### T-19: Fraud flag endpoint with auto-freeze and escalation

**Traces**: MO-8, NFR-8

**Prompt**: "Implement fraud analyst flag endpoint that auto-freezes the card and sends user notification."

**File**: `internal/fraud/flag_handler.go`

**Function/Class**: `FlagCard`

**Details**: 
- `POST /v1/ops/cards/:id/flag` (fraud role required). 
- Request: `{ reason_code: 'VELOCITY_SPIKE'|'UNUSUAL_PATTERN'|'USER_REPORTED'|'SYSTEM_ALERT', notes: string }`. 
- Flow: (1) freeze card (same as T-07 but `actor_role='fraud'`); (2) emit `FRAUD_FLAGGED` audit event; (3) write `fraud_flag` row; (4) publish to `vcard.fraud.v1` Kafka topic; (5) send push notification: "We noticed unusual activity and froze your card. Was this you? [Yes / No]". 
- Flag on already-cancelled card → 409 `TERMINAL_STATE`. 
- Velocity rule: auto-trigger `FlagCard` on 10 declines in 60s (system actor).

**Acceptance Criteria**:
- [ ] Card frozen atomically with fraud_flag write.
- [ ] User push sent.
- [ ] Kafka event published for downstream escalation.
- [ ] Flag on cancelled card → 409.
- [ ] Velocity auto-trigger fires at threshold.

---

#### T-20: GDPR erasure job for closed cards

**Traces**: MO-5, NFR-2

**Prompt**: "Implement scheduled GDPR erasure job for cards cancelled more than 7 years ago."

**File**: `internal/jobs/gdpr_erasure.go`

**Function/Class**: `RunGDPRErasure(ctx) error`

**Details**: 
- Scheduled daily (cron). 
- Find cards where `status='cancelled' AND cancelled_at < now() - INTERVAL '7 years'`. 
- For each: (1) pseudonymize `card.card_holder_name` → `ERASED_{card_id_suffix}`; (2) delete `card_limit` rows; (3) aggregate `transaction` rows to monthly totals only (delete individual rows, insert summary rows); (4) retain `card_event` rows (legal obligation, NFR-3); (5) emit `GDPR_ERASURE_COMPLETED` audit event; (6) do NOT delete the card row (audit continuity). 
- Erasure requested before 7y retention → 409 `RETENTION_LOCK` with `retention_expires_at` in response (EC-18).

**Acceptance Criteria**:
- [ ] PII pseudonymized (not deleted).
- [ ] Transaction details erased but monthly aggregates retained.
- [ ] Audit events retained.
- [ ] Idempotent (re-run on same card → no-op).
- [ ] `GDPR_ERASURE_COMPLETED` event emitted.

---

### Phase F — Cross-cutting & Verification (T-21..T-24)

#### T-21: Idempotency middleware

**Traces**: NFR-5

**Prompt**: "Implement idempotency middleware that deduplicates non-GET requests using Redis."

**File**: `internal/middleware/idempotency.go`

**Function/Class**: `IdempotencyMiddleware`

**Details**: 
- Extract `Idempotency-Key` header (required for POST/PUT/PATCH; 400 if missing). 
- Redis key: `vcard:idem:{user_id}:{method}:{path}:{idempotency_key}`. 
- On cache hit: return cached response (status + body). 
- On cache miss: proceed, store response after success. 
- TTL: 24h. 
- Body hash check: if same key but different body hash → 422 `IDEMPOTENCY_MISMATCH`. 
- Thread-safe: use Redis SET NX for atomic "in-flight" flag to prevent concurrent duplicate requests.

**Acceptance Criteria**:
- [ ] Same key + same body → identical response, no side effects.
- [ ] Same key + different body → 422.
- [ ] Concurrent same key → one proceeds, one waits and gets cached result.
- [ ] Missing header on POST → 400.

---

#### T-22: PII-safe structured logger with redaction

**Traces**: NFR-1, NFR-8

**Prompt**: "Implement shared structured logger with automatic PII field redaction."

**File**: `internal/logger/logger.go`

**Function/Class**: `NewLogger`, `RedactedLogger`

**Details**: 
- Wraps standard structured logger (zerolog or zap / pino). 
- Redaction list: `['pan', 'cvv', 'card_number', 'full_card_number', 'track2', 'expiry', 'card_holder_name']`. 
- Redaction applies to: log field keys (exact match + case-insensitive), JSON payload values where key matches. 
- Redacted value: `"[REDACTED]"`. 
- Redaction must apply recursively in nested JSON. 
- Include `trace_id` from context on every log line. 
- CI gate: grep test that logs containing any test PAN (`4111111111111111`) → test fails.

**Acceptance Criteria**:
- [ ] Field `pan` in any log level → `[REDACTED]`.
- [ ] Nested `{ "card": { "pan": "..." } }` → redacted.
- [ ] `trace_id` present on every line.
- [ ] CI grep gate in test suite catches PAN leaks.

---

#### T-23: Contract tests and load test plan

**Traces**: MO-1 through MO-10

**Prompt**: "Write OpenAPI contract tests and a k6 load test plan for the virtual card service."

**File**: `openapi/vcard.yaml`, `tests/load/vcard.js`

**Function/Class**: OpenAPI 3.1 spec, k6 script

**Details**: 
- OpenAPI spec covers all endpoints from T-05..T-09, T-10, T-12..T-14, T-18, T-19. 
- Schema validation in CI via `spectral lint`. 
- k6 scenarios: (1) baseline: 100 VUs, 5min, mixed read/write (list cards 60%, get detail 20%, freeze/unfreeze 15%, list transactions 5%); (2) spike: ramp to 2000 VUs in 30s, sustain 1min (authorize endpoint only); (3) soak: 50 VUs, 60min. 
- Thresholds: p95 < 200ms for read endpoints; p95 < 400ms for write endpoints; error rate < 0.1%.

**Acceptance Criteria**:
- [ ] OpenAPI spec lints clean.
- [ ] k6 baseline scenario passes thresholds.
- [ ] Load test documents `authorize` p95 target of 80ms.

---

#### T-24: Runbook, dashboards, and alert rules

**Traces**: NFR-8, NFR-4

**Prompt**: "Write operational runbook and Prometheus alert rules for the virtual card service."

**File**: `docs/runbook.md`, `deploy/alerts/vcard.rules.yaml`

**Function/Class**: n/a (YAML + Markdown)

**Details**: 
- Alert rules: `VCardAuthDeclineRateHigh` (>20% decline rate over 5min, SEV-2), `VCardAuditChainBreak` (chain integrity check fails, SEV-1), `VCardVaultLatencyHigh` (vault p95 > 2s, SEV-2), `VCardPendingCardStale` (card in `pending` > 5min, SEV-3). 
- Runbook sections: service overview, dependency map, incident runbook (per alert: symptoms, diagnosis steps, remediation), GDPR erasure manual trigger procedure, audit chain verification procedure.

**Acceptance Criteria**:
- [ ] Each alert has a matching runbook section.
- [ ] `VCardAuditChainBreak` triggers SEV-1 escalation.
- [ ] Runbook covers GDPR erasure manual trigger.

---

## 9. Edge Cases & Failure Modes

| ID | Scenario | Expected Behavior | Audit/Compliance Impact |
|----|----------|-------------------|------------------------|
| EC-01 | Card creation vault timeout (5s exceeded) | Persist `pending` card; return 202 with `retry_after`; client can retry idempotently | Audit event `CARD_CREATION_DEFERRED` emitted; card visible immediately but non-functional until active |
| EC-02 | Concurrent create + freeze on same card | Freeze rejected (card in `pending`); return 409 `INVALID_STATE_TRANSITION` | One audit event recorded; no duplicate |
| EC-03 | Authorization attempt on `pending` card | Declined as `CARD_NOT_READY`; generates `AUTH_DECLINED` event | Fraud analyst visible via dashboard; not counted toward decline rate |
| EC-04 | Daily limit window boundary (midnight UTC vs user TZ) | Evaluated in user's registered IANA timezone; boundary checked server time at evaluation | Audit event includes `evaluated_timezone` for reproducibility |
| EC-05 | Reverse on already-reversed transaction | Idempotent (no new `reversed` event); original still shows as `reversed` | Single audit entry; re-process flagged in logs but not as event |
| EC-06 | Merchant blocklist toggle during open auth | Open auth permitted (limit evaluated at `authorized` time); new auths blocked per new rule | Audit event `LIMIT_UPDATED` and `AUTH_DECLINED` separate; timestamps differ |
| EC-07 | MCC limit set to 0 (block category) | All auths in that category immediately declined as `MCC_BLOCKED` | Audit event includes previous max and new value (0) |
| EC-08 | Authorization hold expires before capture | Transaction state becomes `expired`; amount removed from daily/monthly totals | No audit event needed (system-driven state change) |
| EC-09 | Geographic limit with invalid country code | 400 `INVALID_COUNTRY_CODE`; limit not persisted | Validation error; no audit event |
| EC-10 | User requests early PAN reveal (within 60s of prev reveal) | New reveal token issued (old token may still be valid until TTL); no audit event dedup | Two `PAN_REVEALED` events recorded with timestamps |
| EC-11 | SCA token expired during reveal flow | 401 `SCA_EXPIRED` after step 1; no detokenization attempt; no audit event | Client must request new SCA challenge |
| EC-12 | Fraud flag on card with pending authorization | Card frozen; pending auth not auto-cancelled (will fail at capture) | `FRAUD_FLAGGED` event + pending `AUTH_DECLINED` if capture attempted |
| EC-13 | Ops access reason field contains PII | Reason text is NOT redacted in `OPS_CARD_SEARCH` audit payload (ops operator responsible) | Log line redacted; audit payload (in `card_event`) is plain per GDPR audit trail requirements |
| EC-14 | Idempotency cache eviction on same key before TTL | Request re-processed; new response stored | Side effects occur again (double-emit outbox entry); depends on downstream idempotency |
| EC-15 | Monthly summary view refresh during limit evaluation | Uses cached view (max 5s old); limits evaluated on view data | Limit decision may lag real spend by ≤5s; acceptable per §5 |
| EC-16 | Card cancellation with non-empty open authorizations | Open auths not cancelled; card marked `cancelled`; new auths declined | `CARD_CANCELLED` event emitted; capture of old open auth succeeds if still valid |
| EC-17 | GDPR erasure triggered manually on >7yr card | Erasure proceeds; emits `GDPR_ERASURE_COMPLETED` | Audit trail updated; compliance record complete |
| EC-18 | GDPR erasure requested on <7yr cancelled card | 409 `RETENTION_LOCK`; response includes `retention_expires_at` field | No audit event; user can retry after date |
| EC-19 | Hash chain verification detects tampered event | `audit-svc` logs alarm; `VCardAuditChainBreak` alert triggered | SEV-1 incident; investigation launched |
| EC-20 | Authorization declined, push notification fails | Auth outcome still declined; notification async (fire-and-forget) | Metrics track push failure rate separately; retry policy external |
| EC-21 | Velocity auto-trigger threshold (10 declines/60s) met on system card | System-actor `FlagCard` called automatically; card frozen | `FRAUD_FLAGGED` event with `actor_role='system'` and reason `VELOCITY_SPIKE` |
| EC-22 | Concurrent limit updates on same card | Optimistic locking: one succeeds, other gets 409 `VERSION_CONFLICT` | Both emit `LIMIT_UPDATED` events if both eventually succeed; client retries |
| EC-23 | Reveal token used twice | First GET succeeds; token deleted from Redis. Second GET → 401 `REVEAL_TOKEN_EXPIRED` | Logged; no audit event (user action) |
| EC-24 | Currency mismatch on limit set (limit in EUR, card in UAH) | 400 `CURRENCY_MISMATCH`; currency field required in request | Validation error; no state change |
| EC-25 | Card reactivation after freeze (state `frozen` → `active`) | Unfreeze endpoint transitions state; not a separate "reactivate" | Single `CARD_UNFROZEN` event; state machine respects idempotence |

---

## 10. Performance Expectations (Assumed Targets)

> All figures are **assumed targets** — not measured baselines. Anchored to Monobank UX, Stripe/Adyen public benchmarks, and Visa/MC network SLAs (see justification below).

| Operation | p50 | p95 | p99 | Justification |
|-----------|-----|-----|-----|---------------|
| POST /v1/cards (create) | 200ms | 600ms | 1200ms | Vault tokenize ≈400ms + DB write + outbox; async vault callback tolerates latency |
| GET /v1/cards (list own) | 20ms | 80ms | 150ms | Index-backed; < 20 cards per user typical |
| GET /v1/cards/:id (detail) | 30ms | 100ms | 200ms | Card + limits join; cacheable in Redis |
| POST /v1/cards/:id/freeze | 50ms | 150ms | 300ms | Version check + update + notification async; pessimistic latency on Kafka publish |
| POST /v1/cards/:id/cancel | 100ms | 250ms | 500ms | Vault DELETE adds latency; retries on timeout |
| PUT /v1/cards/:id/limits | 30ms | 80ms | 150ms | Upsert + version check; no I/O |
| GET /v1/cards/:id/transactions (paginate) | 40ms | 120ms | 250ms | Index scan; cursor validation HMAC-checked |
| POST /internal/authorize | 40ms | 80ms | 150ms | Limits evaluation pure fn; cache hit typical; Redis load < 5ms |
| POST /v1/cards/:id/reveal (SCA + detokenize) | 150ms | 400ms | 800ms | SCA verify ≈150ms + vault detokenize ≈200ms |
| GET /v1/ops/cards (search) | 50ms | 150ms | 300ms | Offset-based pagination; reason param logged |
| POST /v1/ops/cards/:id/flag (fraud) | 100ms | 200ms | 400ms | Freeze + fraud_flag write + Kafka + notification async |
| POST /internal/audit/emit-event | 20ms | 50ms | 100ms | Hash compute + outbox write; Kafka publish async |

**Justification**: All targets anchored to Monobank mobile UX expectations (visual feedback < 300ms for user actions, < 500ms acceptable for background tasks), Stripe/Adyen public API benchmarks (auth < 100ms p95), and Visa/MC settlement SLAs (authorization responses < 2s hard limit). Authorization SLO of 80ms p95 leaves 1.92s margin within 2s network timeout, accommodating retries and vault fallback.

---

## 11. Verification

### MO-1: Card creation visible within 2s

**Review checkpoint**: Tester creates card via mobile app; card appears in list within 2s visual refresh.

**Test categories**: E2E (mobile app → API → DB); integration (mock vault fast-path).

**Acceptance signal**: k6 baseline scenario records p95 create latency < 600ms; card queryable immediately after 201 response.

---

### MO-2: Freeze/unfreeze effective on next auth

**Review checkpoint**: Tester freezes card; next authorization declined; unfreezes; next auth succeeds.

**Test categories**: Integration (card → authorize endpoint); contract (state transitions in OpenAPI).

**Acceptance signal**: Mock authorization hooks verify frozen card returns `CARD_FROZEN` decline reason; no auth processing loops.

---

### MO-3: Limits updated with immediate effect

**Review checkpoint**: Tester sets daily limit to 1000 UAH; authorizes 500; second auth for 600 declined.

**Test categories**: Unit (EvaluateLimits function); integration (limits cache refresh).

**Acceptance signal**: Unit test: `TestEvaluateLimitsDailyExceeded`; integration: Redis cache invalidated < 100ms after limit update.

---

### MO-4: Transaction history paginated and filtered

**Review checkpoint**: Tester views 5 oldest transactions; navigates to next page; filters by MCC; result count correct.

**Test categories**: Integration (pagination cursor validation); contract (OpenAPI query params).

**Acceptance signal**: Cursor HMAC verification passes; MCC filter reduces result set by expected ratio; empty card shows empty array (not 404).

---

### MO-5: Cancelled card history preserved

**Review checkpoint**: Tester cancels card; queries old transactions; cancellation reason stored; no exception raised.

**Test categories**: Integration (DB constraints + soft-delete logic); compliance (GDPR retention).

**Acceptance signal**: `SELECT COUNT(*) FROM transaction WHERE card_id=$1 AND status='captured'` returns > 0 post-cancellation; `cancel_reason` field populated.

---

### MO-6: Audit events immutable and chain-verified

**Review checkpoint**: `audit-svc` replays card event log; computes hash chain; detects tamper attempt (DB row manually modified).

**Test categories**: Security (hash chain verification); integration (outbox → Kafka → audit-svc).

**Acceptance signal**: Replay computes all hashes matching DB `event_hash` column (< 1ms deviation); manual row modification breaks chain (detectable by audit-svc alert).

---

### MO-7: Ops search with masked PAN and audit logging

**Review checkpoint**: Ops user searches by user_id without reason → 400; adds reason → 200 with masked PAN; audit event `OPS_CARD_SEARCH` recorded.

**Test categories**: RBAC (role check); integration (search + audit emit); contract (reason field required).

**Acceptance signal**: Search without reason rejects; full PAN never in response; `card_event` row exists with search reason in payload.

---

### MO-8: Fraud flag auto-freezes and notifies

**Review checkpoint**: Fraud analyst flags card; card frozen immediately; user receives push; velocity auto-trigger test (10 declines in 60s) fires flag.

**Test categories**: Integration (freeze + notification + flag write atomic); load (velocity counter accuracy under concurrent declines).

**Acceptance signal**: Card status = `frozen` after flag API returns; push metadata includes `reason_code`; velocity counter increments correctly; auto-trigger fires at exactly 10 declines.

---

### MO-9: PAN/CVV never in logs or external storage

**Review checkpoint**: CI gate runs: grep `-r '4111111111111111'` (test PAN) in logs and DB export; grep for `[REDACTED]` in logs at PAN reveal flow.

**Test categories**: Security (redaction middleware); CI (static analysis).

**Acceptance signal**: Grep gate passes (0 test PANs found); log line at PAN reveal shows `[REDACTED]` in `pan` field; reveal_token stored only in Redis (TTL 60s).

---

### MO-10: Integer-only monetary arithmetic

**Review checkpoint**: Run settlement job; reconcile `SUM(transaction.amount WHERE captured_at IS NOT NULL) = SUM(card_event.payload->'amount')` for sample card.

**Test categories**: Integration (settlement + audit); compliance (reconciliation).

**Acceptance signal**: Reconciliation check passes (exact match, no rounding); `EvaluateLimits` function unit tests use `int64` exclusively (no floats in spent total accumulation).

---

### Cross-Cutting Verification

**No PAN in logs CI gate**: 
- Build step runs `grep -rE '4111|5555|6011|3782|[0-9]{16}' logs/ && exit 1 || true` (inverted exit code). 
- Failure → build fails. 
- Catches accidental PAN leaks in error messages.

**Audit chain replay**: 
- Daily job: `audit-svc` starts from first event of each card_id, recomputes hashes, compares to DB. 
- Mismatch → alert `VCardAuditChainBreak` (SEV-1). 
- Runbook includes manual replay procedure.

**Reconciliation check**: 
- Nightly job: `SELECT SUM(amount) FROM transaction WHERE card_id=$1 AND status='captured'` vs. monthly_summary materialized view `total_spent`. 
- Variance > 1% → alert (SEV-2). 
- Reports variance per card for manual investigation.

**Manual compliance review**: 
- PCI-DSS data flow diagram (data flow between services, token boundaries, vault scope). 
- Reviewed annually by compliance officer + security architect. 
- Documented in `docs/pci-dss-data-flows.pdf`.

---

## 12. Traceability Matrix

| MO | Tasks | NFRs | Edge Cases |
|----|-------|------|-----------|
| MO-1 | T-05, T-06, T-21 | NFR-6 (Performance) | EC-01, EC-02, EC-03 |
| MO-2 | T-07, T-12 | NFR-6, NFR-4 (Reliability) | EC-06, EC-25 |
| MO-3 | T-10, T-11, T-12, T-13 | NFR-6, NFR-10 (Monetary) | EC-04, EC-07, EC-09, EC-14, EC-15, EC-24 |
| MO-4 | T-14, T-15, T-16 | NFR-6 (Performance) | EC-08 |
| MO-5 | T-08, T-20 | NFR-2 (Privacy), NFR-3 (Audit) | EC-16, EC-17, EC-18 |
| MO-6 | T-04, T-17, T-24 | NFR-3 (Audit), NFR-8 (Observability) | EC-19 |
| MO-7 | T-06, T-18 | NFR-2 (Privacy), NFR-3 (Audit), NFR-7 (Authorization) | EC-13 |
| MO-8 | T-19 | NFR-8 (Observability) | EC-12, EC-21 |
| MO-9 | T-01, T-05, T-09, T-22 | NFR-1 (Security), NFR-9 (Compliance) | EC-11 |
| MO-10 | T-11, T-15 | NFR-10 (Monetary) | EC-05, EC-22 |

---

## 13. Open Questions & Assumptions

- **Assumed**: BIN sponsor latency p95 ≈ 400ms (factored into T-05 create latency SLO of 600ms p95).
- **Assumed**: SCA OTP verification via existing `auth-svc` adds ≈ 150ms (T-09 reveal SLO of 400ms p95 = 150ms SCA + 200ms detokenize).
- **Assumed**: Monobank uses UAH as primary currency; other currencies require account-matching per user KYC. Spec assumes UAH defaults.
- **Assumed**: Visa/MC hard authorization timeout = 2s network layer; T-12 `authorize` target (80ms p95) leaves 1.92s margin for retries.
- **Open**: Which card network (Visa vs Mastercard) for the BIN range — not required for this spec. Assume Visa as Monobank norm.
- **Open**: Whether geographic allowlist uses ISO-3166-1 alpha-2 (assumed) or proprietary code set — spec assumes ISO-3166-1.
- **Added stakeholder**: Fraud team (`fraud_analyst` persona) added beyond minimal scope — see Notes in README for rationale (completes the neobank operations picture).
- **Assumed**: Kafka message ordering guarantee = per-card (partition key = `card_id`); event consumers handle out-of-order delivery via `event_seq` + `prev_hash`.
- **Assumed**: PCI-DSS SAQ-D scope includes `vcard-svc` but vault is separate entity (SAQ-A-EP or level-1 processor); no PAN/CVV in `vcard-svc` memory post-tokenization.
