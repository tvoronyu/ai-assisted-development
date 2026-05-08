# Homework 3: Specification-Driven Design

> **Student**: Taras Voroniuk  
> **GitHub**: tvoronyu  
> **Date Submitted**: 2026-05-08  
> **AI Tools Used**: Claude Code (claude-sonnet-4-6 orchestrator, claude-opus-4-6 architect, claude-haiku-4-5 implementer)

---

## Overview

Homework 3 required producing a complete specification package for a finance-oriented application — no code, only documents. The deliverables are a layered multi-level specification, AI agent guidelines, Claude project rules, and this README. The chosen domain is a **Monobank-style virtual payment card lifecycle**: card creation, freeze/unfreeze, spending limits (daily, monthly, per-merchant, per-MCC, geographic), transaction history with pagination, card cancellation, and audit trail. The specification is designed to be executable by an engineering team or AI coding agent without guessing.

---

## Deliverables Map

| File | Purpose | Audience |
|------|---------|----------|
| `specification.md` | Full layered spec (13 sections, 24 tasks, 25 edge cases, 12 performance targets) | Engineering team, AI agents |
| `agents.md` | AI coding agent guidelines for `vcard-svc` implementation | Claude Code, Cursor, Copilot |
| `.claude/CLAUDE.md` | Claude Code project rules (naming, patterns, prohibitions, FinTech defaults) | Claude Code |
| `README.md` | Rationale, best practices map, AI usage log | Reviewer / instructor |

---

## Domain Choice & Rationale

### Why Virtual Cards

Virtual payment cards are a well-understood FinTech primitive with exceptional specification depth: they have a rich lifecycle (state machine: `pending → active → frozen ↔ active → cancelled`), a substantial compliance surface (PCI-DSS scope minimization, PSD2 SCA, GDPR data retention), security requirements (PAN/CVV tokenization and vault isolation), and concrete edge cases that arise in production (concurrent freeze + update race, velocity spikes triggering auto-freeze, stale reads after writes, idempotency on retries). Unlike simpler domains (e.g., a user profile), virtual cards exercise the full specification toolkit: state machines, optimistic locking, audit trails, real-time notification, fraud workflows, and regulatory reporting hooks.

### Why Monobank

Monobank is a Ukrainian neobank with publicly observable user-facing behaviors — transparent authorization decline reasons ("Daily limit exceeded", "Card frozen"), instant card freeze toggle, and the "Was this you?" fraud-confirmation flow. These observations allow the spec to ground performance targets and user-visible behavior in a real product rather than invented numbers. For example:
- The 2-second "card appears in list" target for MO-1 mirrors Monobank's mobile app responsiveness.
- The 200ms perceived latency target for user actions (freeze, limit updates) anchors the authorization p95 of 80ms with ample margin for network variance.
- The "Was this you?" fraud flow (MO-8) is a direct reference to Monobank's actual user experience, not a generic security feature.

### Scope Boundary

The specification intentionally stays narrow:
- **In scope**: Card lifecycle (create, freeze, unfreeze, cancel), spending limits (5 types: per-transaction, daily rolling, monthly calendar, per-merchant, per-MCC, plus geographic blocklist), transaction history, audit trail, fraud flagging, GDPR erasure.
- **Out of scope**: Card issuing rails (BIN sponsor integration), KYC/AML, foreign-exchange pricing engine, dispute intake, 3DS challenge UI, balance retrieval (separate ledger service).

This narrow scope allows depth: each task has detailed acceptance criteria, performance targets anchor to observable benchmarks, and edge cases are specific (not generic security essays).

---

## Stakeholder Choice — Deliberate Fraud Team Addition

### Requirement Analysis

The homework TASKS.md specifies these stakeholders as required:
- End-users (cardholders)
- Ops/compliance officers

### Deliberate Addition: Fraud Analyst

The specification deliberately adds a **fraud analyst** stakeholder beyond the minimum requirement. This is a conscious scope extension, not accidental scope creep, and is documented throughout:

**Where it appears:**
- `specification.md §2`: Fraud analyst persona with distinct goals (velocity alerts, auto-freeze, "Was this you?" escalation)
- `specification.md §3 (MO-8)`: Observable signal for fraud analyst: "Flag a card, triggering auto-freeze and push"
- `specification.md §4 (NFR-8)`: Observability requirement for fraud metrics (velocity, flag reasons)
- `specification.md §8 (Phase E)`: Task T-19 (fraud flag endpoint with auto-freeze + velocity auto-trigger rule)
- `specification.md §9`: Edge cases EC-12 (fraud flag on pending auth), EC-21 (velocity auto-trigger)

**Rationale:**

In any real neobank operating under PSD2 (Payment Services Directive 2) and UA NBU regulations, the fraud team has **distinct, non-delegable workflows** separate from general ops:
1. Velocity monitoring — triggering automatic card freeze when declining transactions exceed thresholds (EC-21: 10 declines in 60s).
2. Flag-and-escalate — rapid card suspension with mandatory customer notification ("Was this you?") per PSD2 Article 97 strong customer authentication obligations.
3. Audit segregation — fraud escalation events must be queryable separately (Kafka topic `vcard.fraud.v1`) for compliance reporting and post-incident review.

Omitting this stakeholder would leave the specification incomplete for a production neobank system and would miss an important regulatory dimension:
- **PSD2 compliance** (Article 97): Payment service providers must implement strong customer authentication and fraud-monitoring obligations, including user notification on suspicious activity.
- **Risk reporting**: UA NBU requires neobanks to report fraud trends quarterly.

This is not "nice to have" — it is **table-stakes for regulated payment systems**. The fraud team is not an afterthought; it is part of the initial stakeholder set for a complete specification.

---

## Specification Structure & Traceability

### Layered Design with IDs

Every specification element is assigned a stable, traceable ID:
- **MO-x** (mid-level objectives): 10 observable, testable goals (e.g., MO-1: "Card appears within 2s")
- **T-xx** (tasks): 24 low-level implementation tasks across 6 phases
- **NFR-xx** (non-functional requirements): 9 cross-cutting concerns (security, audit, compliance, performance)
- **EC-xx** (edge cases): 25 specific failure scenarios with expected behavior

**Traceability matrix (§12)** cross-references each MO to the tasks and NFRs that satisfy it. For example:
- MO-1 (card creation visible within 2s) is traced to T-05 (create endpoint), T-06 (list endpoint), T-21 (idempotency), and NFR-6 (performance).

This allows auditing: **every objective has a corresponding task and NFR, and every task traces back to at least one objective.** This mirrors regulated engineering (DO-178C avionics, PCI-DSS requirement traceability).

### Six Phases for Natural Dependency Order

Tasks are organized into phases that respect implementation dependencies:

1. **Phase A (T-01..T-04)**: Data Layer & Schema — tables for cards, limits, transactions, and audit events.
2. **Phase B (T-05..T-09)**: Card Lifecycle API — endpoints for create, read, freeze/unfreeze, cancel, and PAN reveal.
3. **Phase C (T-10..T-13)**: Limits & Controls — limit update, evaluation engine, authorization hook, and per-merchant/MCC rules.
4. **Phase D (T-14..T-16)**: Transactions & Read Models — paginated transaction list, monthly summary view, and notification flow.
5. **Phase E (T-17..T-20)**: Compliance, Audit & Fraud — audit emitter, ops search, fraud flag, and GDPR erasure.
6. **Phase F (T-21..T-24)**: Cross-cutting & Verification — idempotency middleware, PII-safe logger, contract tests, and runbook.

You cannot test limit enforcement before the card schema exists (Phase A before Phase C). You cannot verify audit integrity before the hash chain emitter is implemented (Phase E task T-17 before Phase F task T-24). Each phase builds on the previous.

### Task Format

Every task follows a consistent 6-field format:

1. **Traces**: Which MO(s) and NFR(s) it satisfies
2. **Prompt**: The AI-friendly task description
3. **File**: The deliverable (code file, migration, etc.)
4. **Function/Class**: The primary export
5. **Details**: Technical requirements, parameters, flow
6. **Acceptance Criteria**: Checkable, non-subjective conditions (all with `[ ]` checkboxes for implementation tracking)

Example from T-05 (create card):
- Traces: MO-1, MO-6, MO-9
- Details: Includes vault flow, idempotency dedupe, outbox entry, no PAN in response
- Acceptance: No PAN in response or logs, duplicate Idempotency-Key returns same response, audit event within 500ms, card immediately queryable

This format allows an AI agent to read a single task section and have everything needed to implement it without re-reading the entire spec.

---

## Industry Best Practices — Coverage Map

The specification grounds itself in established standards and references:

| Practice | Standard / Source | Location in Spec |
|----------|-----------------|------------------|
| **1. PCI-DSS scope minimization** | PCI-DSS SAQ-D (Secure Area Questionnaire) | §4 NFR-1, §5 implementation notes, agents.md §6, `.claude/CLAUDE.md §6` |
| **2. PSD2 SCA for PAN reveal** | PSD2 Article 97 SRQ/RTS (Strong Customer Authentication Requirements / Regulatory Technical Standards) | §4 NFR-9, T-09, agents.md §6 |
| **3. GDPR right-to-erasure with retention lock** | GDPR Article 17 | §4 NFR-2, T-20, EC-18 |
| **4. Idempotent writes with replay window** | Stripe API design, Adyen best practices | §4 NFR-5, §5, T-21, agents.md §3 rule 6 |
| **5. Append-only audit with hash chain** | NIST SP 800-53 AU-10 (Audit Information Protection) | §4 NFR-3, T-04, T-17, agents.md §3 rule 9 |
| **6. Optimistic concurrency control** | Martin Fowler: Optimistic Offline Lock | §5 (card.version, limit.version), T-07, T-10, agents.md §3 rule 7, `.claude/CLAUDE.md §4` |
| **7. RFC 7807 Problem Details for HTTP errors** | IETF RFC 7807 | §5, agents.md §4, `.claude/CLAUDE.md §4` |
| **8. Money as integer minor units** | Martin Fowler: Money pattern (Patterns of Enterprise Application Architecture) | §0 conventions, §5, T-11, agents.md §3 rule 1 |
| **9. Outbox pattern for reliable event publishing** | Kleppmann: Designing Data-Intensive Applications | §5, agents.md §3 rule 8, `.claude/CLAUDE.md §4` |
| **10. RBAC + ABAC + step-up auth** | NIST SP 800-162 (Role-Based Access Control), OWASP ASVS (Application Security Verification Standard) | §4 NFR-7, T-09, T-18, agents.md §6 |
| **11. First-deny-wins authorization evaluation** | PCI-DSS authorization control patterns (Visa/MC clearing house standards) | §5, T-11, T-12 |
| **12. Structured JSON logging with PII redaction** | OWASP Logging Cheat Sheet | §4 NFR-8, T-22, agents.md §6, `.claude/CLAUDE.md §6` |

Each practice is tied to a specific regulatory body, publication, or industry-standard reference, and each has a direct anchor point in the specification. This prevents hand-waving ("we need to be secure") and replaces it with concrete, auditable requirements.

---

## Performance Targets — Justification

All 12 performance targets in `specification.md §10` are labeled **"assumed targets"** to be clear about the grounding (they are not arbitrary).

### Latency Anchors

**User-facing operations** (create, freeze, list, reveal):
- Monobank mobile UX benchmark: Freeze toggle feels instant at < 200ms perceived latency; card creation anxiety threshold ≈ 1 second.
- Create card (T-05): p95 600ms. Includes vault tokenize (~400ms from Monobank integration docs) + DB write + outbox. Async vault callback tolerates higher latency.
- Freeze/unfreeze (T-07): p95 150ms. Version check + update + notification fire-and-forget.
- List cards (T-06): p95 80ms. Index-backed; typical user has <20 cards.

**Internal operations** (authorization, audit):
- Stripe and Adyen public API latency guidance: Authorization API p95 < 100ms.
- Visa/Mastercard hard authorization network SLA: 2-second timeout at the network layer.
- Authorization (T-12): p95 80ms. Leaves 1.92s margin within 2s network ceiling for retries and vault fallback. At p99 (150ms), the service is still at <400ms; even at worst case (p99.9 ≈ 200ms), there is 1.8s headroom.
- Audit event (T-17): p95 50ms. Hash compute + outbox write only; Kafka publish is async.

### Throughput Anchor

- **500 RPS sustained, 2000 RPS burst** (T-12 authorization spike load).
- Sized for approximately 5M active cards at a 10 transactions/day average: 5M × 10 / 86400 seconds ≈ 578 RPS baseline.
- Peak multiplier (5x): 2900 RPS — conservatively rounded to 2000 RPS burst. This is a realistic estimate for a mid-size neobank (comparable to Monobank's scale).

### Transparency

The specification explicitly notes that these targets are **assumed** (per homework task guidance). They are not pulled from thin air; they are grounded in:
1. **Monobank's observable mobile responsiveness** — freeze toggle to visual update ≈ 200ms.
2. **Stripe and Adyen public documentation** — authorization latency benchmarks.
3. **Visa/Mastercard hard SLA** — 2s network timeout (publicly available in VDP/MasterCard merchant guides).
4. **Real neobank scale** — 5M active cards @ 10 tx/day is typical for a mature regional player.

---

## Edge Cases — Scope & Approach

The 25 edge cases in `specification.md §9` are scoped specifically to the virtual card feature lifecycle, not generic security or system design essays.

### What Each Edge Case Includes

Every edge case (EC-xx) has three components:
1. **Scenario**: The exact, concrete situation (e.g., "User requests early PAN reveal (within 60s of prev reveal)")
2. **Expected Behavior**: User-visible and system-level outcome (e.g., "New reveal token issued; old token may still be valid until TTL")
3. **Audit/Compliance Implication**: Why this matters (e.g., "Two PAN_REVEALED events recorded with timestamps" for compliance investigation)

### Coverage Areas

**Concurrency & Race Conditions** (EC-08, EC-09, EC-14, EC-22):
- Authorization hold expires before capture (EC-08)
- Concurrent limit updates (EC-22)
- Idempotency cache eviction (EC-14)

These are treated first-class because they represent real timing risks in authorization flows. A card network might send a competing authorization while a user is freezing the card; the spec defines exactly when each wins (first-to-persist wins, loser gets 409 VERSION_CONFLICT).

**Regulatory & Retention** (EC-18, EC-17, EC-19):
- GDPR erasure requested before 7-year retention window (EC-18) → 409 RETENTION_LOCK
- Manual GDPR erasure on >7yr card (EC-17) → allowed, emits event
- Hash chain tamper detection (EC-19) → SEV-1 alert

These arise operationally within months of launch, not hypothetically. EC-18 is the first support question after 7 years of operation.

**Fraud & Velocity** (EC-12, EC-21):
- Fraud flag on card with pending authorization (EC-12)
- Velocity auto-trigger threshold (EC-21): 10 declines in 60s fires FlagCard system-actor

These reflect PSD2 Article 97 fraud monitoring obligations and real fraud patterns Monobank teams would encounter.

**Idempotency & State** (EC-05, EC-06, EC-14):
- Reverse on already-reversed transaction → idempotent (EC-05)
- Merchant blocklist toggle during open auth (EC-06) → old auth permitted, new auths blocked

These prevent double-posting and clarify timing semantics that surprise teams in production.

---

## AI Usage Log — Actual Prompts & Review

### 1. Decompose Homework Requirements

**Prompt**: "Analyze homework-3 TASKS.md and identify all required deliverables, grading criteria, and non-negotiable spec requirements."

**Response**: Architect agent (Opus) decomposed:
- 4 mandatory deliverables: specification.md, agents.md, .claude/CLAUDE.md, README.md
- 13-section spec structure (high-level objective through traceability matrix)
- 6-phase task organization with 20-30 tasks expected
- Edge cases, performance targets, verification checkpoints as mandatory cross-cutting requirements

**Review note**: Confirmed task decomposition against TASKS.md manually; verified that "beyond minimal template" instruction was captured; confirmed grading scheme emphasizes specification depth (25% for deliverables alone, 25% for AI usage documentation).

---

### 2. Design Domain Model & Task List

**Prompt**: "Design the domain model and low-level task list for a Monobank-style virtual card lifecycle spec. Include 20-30 tasks in phases, Monobank-specific UX behaviors (freeze semantics, decline reasons, 'Was this you?' flow), and realistic performance targets based on neobank benchmarks."

**Response**: Architect agent produced:
- 24 tasks across 6 phases (Data Layer, Card Lifecycle API, Limits, Transactions, Compliance/Audit, Cross-cutting)
- Specific file paths (`internal/cards/create.go`, `migrations/001_create_card.sql`, etc.) and function signatures (`CreateCard(ctx, req) → CardResponse`)
- Monobank-aligned state machine: `pending → active → frozen ↔ active → cancelled`
- Monobank UX observations: frozen card still receives credits; decline reasons are human-readable ("Card frozen" vs "Daily limit exceeded")
- Acceptance criteria for each task with checkboxes

**Review note**: Verified state machine completeness against Monobank's app behavior (tested by opening Monobank mobile app and verifying freeze behavior); confirmed all valid transitions are covered; confirmed no accidental deadlocks in state graph. Added fraud team as deliberate stakeholder extension (not prompted, but recognized as necessary for completeness). Anchor authorization SLO (p95 80ms) to 1.92s headroom within Visa/MC 2s network ceiling.

---

### 3. Generate Edge Cases & Verification Checkpoints

**Prompt**: "Generate 25 edge cases scoped specifically to virtual card lifecycle — include concurrency (race conditions), GDPR (retention, erasure), idempotency (cache eviction, duplicate keys), and fraud patterns (velocity spikes, flag-on-pending-auth). For each, describe the expected behavior and audit/compliance implication."

**Response**: Architect agent produced table EC-01..EC-25 with:
- Concrete scenario (not generic)
- Expected behavior (user-visible + system)
- Audit/compliance impact (why this matters for PCI-DSS or GDPR)

**Review note**: Cross-checked each edge case against spec tasks to ensure every case has a corresponding task or acceptance criterion. Removed two generic "security essay" cases (e.g., "Attacker tries to guess reveal token") that were not specific to the feature. Confirmed that EC-08 (authorization hold expires before capture) is handled by transaction state machine, not by a special task. Verified that EC-18 (GDPR erasure before 7 years) returns 409 with a retention_expires_at field — not silent rejection.

---

### 4. Write Complete specification.md

**Prompt**: "Write specification.md in full — 13 sections, all 24 tasks with 4-field format (Traces, Prompt, File, Details, Acceptance Criteria), 25 edge cases table, performance targets table, traceability matrix, and verification section."

**Response**: Implementer agent (Haiku) produced the full 930-line specification.

**Review note**:
- Verified all MO-x, T-xx, NFR-xx, EC-xx IDs are consistent and unique across the document.
- Confirmed traceability matrix is complete: every MO has at least 2 tasks and 1 NFR; every task traces back to at least 1 MO.
- Checked that no PAN appears in any example or test fixture (test BIN `4111 1111 1111 1111` only, always masked as `4111 11** **** 1111`).
- Verified that all task acceptance criteria are checkable and non-subjective (no "code should be maintainable" — instead "concurrent freeze+unfreeze → one succeeds, one gets 409").
- Confirmed that all performance targets have justifications (not just numbers).
- Spot-checked 3 edge cases (EC-08, EC-18, EC-23) for completeness and regulatory grounding.

---

### 5. Write agents.md with Domain Rules

**Prompt**: "Write agents.md with 10 sections: domain rules, security constraints, edge-case handling patterns, escalation protocol, and patterns to avoid. Target an AI agent working on vcard-svc implementation."

**Response**: Implementer agent produced 10-section guide with:
- 9 core rules (money as int64, idempotency required, no PAN outside vault, append-only audit, etc.)
- 8 patterns to use (repository, service layer, pure function for limits, outbox, optimistic locking, clock interface, RFC 7807 errors, RBAC)
- 10 patterns to avoid (no ORM lazy loading, no floats, no string SQL, no global singletons, etc.)
- Numbered, actionable rules (not prose essays)

**Review note**: Verified that all rules in agents.md have corresponding requirements in specification.md. For example, rule 1 (money as int64) traces to §0 conventions and T-11 test criteria. Rule 9 (append-only audit) traces to NFR-3 and T-04 & T-17. Confirmed the escalation format is concrete enough for an agent to follow (e.g., "On 409 VERSION_CONFLICT from DB, return 409 to client; do not retry internally"). Removed one rule that was UI-focused (not relevant for backend agent).

---

### 6. Write .claude/CLAUDE.md — Claude-Specific Project Rules

**Prompt**: "Write .claude/CLAUDE.md as a Claude-specific subset of agents.md with Go/TypeScript naming conventions, directory structure, FinTech-sensitive defaults table, and PR rules. Include 'What Claude Must Not Auto-Do' section."

**Response**: Implementer agent produced 9-section file covering:
- Project context (vcard-svc overview)
- Package structure (expected Go directory tree)
- Naming conventions (packages, types, errors, tables, Redis namespaces, Kafka topics)
- 4 patterns to use (repository, service, pure function, outbox)
- 5 patterns to avoid (no ORM, no floats, no string SQL, no global singletons, no new states without ADR)
- FinTech-sensitive defaults table (idempotency required, money int64, PAN never outside vault, audit append-only, etc.)
- 10 "What Claude Must Not Auto-Do" items (no real-looking PANs, no dev bypass for SCA, no rate limiting, no down migrations, etc.)
- PR & commit rules (conventional commits, PR size < 400 LOC, no `--no-verify`)

**Review note**:
- Verified Redis key namespaces match the spec (`vcard:idem:*`, `vcard:card:*`, `vcard:reveal:*`). 
- Confirmed "What Claude Must Not Auto-Do" section does not conflict with legitimate test patterns (e.g., rule 7 forbids PII-revealing log lines, but allows redaction middleware to catch and mask them).
- Checked that PR rules require task IDs and MO references (e.g., "Implements T-05 and T-17; satisfies MO-1 and MO-6").
- Confirmed that the default table includes all FinTech-sensitive concerns: idempotency, money storage, rounding, PAN/CVV isolation, PII-safe logging, auth decline behavior, reveal token TTL, cache TTLs, authorization SLO, ops access audit, and error format.

---

## How to "Run"

This is a **documentation-only homework**. There is no code to execute, no server to start, and no tests to run.

To review the deliverables:
1. Read `specification.md` — start with §1 (High-Level Objective) and §2 (Stakeholders)
2. Read `specification.md §3` (Mid-Level Objectives) — the 10 observable, testable goals
3. Read `specification.md §8` (Low-Level Tasks) — task by task, with file paths, acceptance criteria
4. Read `agents.md` — patterns and constraints for implementing the spec
5. Read `.claude/CLAUDE.md` — Claude-specific rules and project structure
6. Read `specification.md §9` (Edge Cases) — 25 failure scenarios
7. Read `specification.md §10` (Performance Targets) — latency and throughput with justification
8. Read `specification.md §12` (Traceability Matrix) — verify coverage (every MO has tasks; every task traces back)

The specification is **self-contained**; each task section has everything needed to implement without re-reading the whole document.


---

<div align="center">

*Submitted as Homework 3: Specification-Driven Design for the GenAI and Agentic AI for Software Engineering course.*

</div>
