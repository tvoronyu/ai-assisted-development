# 🏛 Architecture — Customer Support Ticket System

> Audience: tech leads, senior engineers reviewing the design.

---

## 1. High-level architecture

```mermaid
flowchart LR
    Client[REST Client]

    subgraph FastAPI["FastAPI app (src/main.py)"]
        direction TB
        Tickets[api/tickets.py<br/>CRUD]
        Import[api/import_.py<br/>Bulk Import]
        Classify[api/classify.py<br/>Auto-classify]
        Healthz[GET /healthz]
    end

    subgraph Services
        TicketSvc[TicketService<br/>create / list / get / update / delete]
        Importer[TicketImporter<br/>parse + validate + persist]
        ClassSvc[ClassificationService<br/>persist result]
        Classifier[TicketClassifier<br/>rule-based]
    end

    subgraph Parsers
        Csv[CsvTicketParser]
        Json[JsonTicketParser]
        Xml[XmlTicketParser]
    end

    subgraph Persistence
        ORM[Ticket ORM<br/>SQLAlchemy 2.0 async]
        Engine[Async Engine<br/>asyncpg]
        DB[(PostgreSQL 17<br/>tickets / tickets_test)]
        Alembic[Alembic migrations]
    end

    Client -->|HTTP| Tickets
    Client -->|HTTP| Import
    Client -->|HTTP| Classify
    Client -->|HTTP| Healthz

    Tickets --> TicketSvc
    Tickets -.optional auto_classify.-> ClassSvc
    Import --> Importer
    Classify --> ClassSvc

    Importer --> Csv
    Importer --> Json
    Importer --> Xml
    Importer --> ORM

    ClassSvc --> Classifier
    ClassSvc --> ORM

    TicketSvc --> ORM
    ORM --> Engine
    Engine --> DB
    Alembic --> DB
```

---

## 2. Component breakdown

| Layer | Module | Responsibility |
|---|---|---|
| **API** | `src/api/tickets.py` | REST endpoints for ticket CRUD + pagination |
| | `src/api/import_.py` | `POST /tickets/import` — multipart upload, dispatch to parser |
| | `src/api/classify.py` | `POST /tickets/{id}/auto-classify` |
| | `src/api/deps.py` | DI: `SessionDep`, `TicketServiceDep`, `ClassificationServiceDep` |
| **Service** | `src/services/ticket_service.py` | CRUD logic, filter+pagination query building |
| | `src/services/importer.py` | Parser dispatch (by file extension), per-row validation, error collection |
| | `src/services/classifier.py` | `TicketClassifier` — rule-based, sync, no I/O |
| | `src/services/classification_service.py` | Apply classifier to stored ticket, persist `category`, `priority`, `confidence` |
| **Parsers** | `src/parsers/{csv,json,xml}_parser.py` | Bytes → list of raw dicts. Stateless. Raise `ParserError` on malformed input |
| | `src/parsers/base.py` | `TicketParser` Protocol, `ParserError` |
| **Schemas** (DTO) | `src/schemas/ticket.py` | Pydantic v2: `TicketCreate`, `TicketUpdate`, `TicketRead`, `TicketFilter`, `TicketListResponse`, `TicketMetadata` |
| | `src/schemas/import_.py` | `ImportSummary`, `ImportItemError` |
| | `src/schemas/classification.py` | `ClassificationResult` |
| **Models** (ORM) | `src/models/ticket.py` | SQLAlchemy 2.0 ORM `Ticket` (UUID, JSONB, native ENUM, ARRAY, server-side timestamps) |
| | `src/models/enums.py` | `Category`, `Priority`, `Status`, `Source`, `DeviceType` |
| **DB** | `src/db/session.py` | Async engine + `async_sessionmaker` + `get_session` dependency |
| | `src/db/base.py` | `class Base(DeclarativeBase)` |
| | `alembic/env.py` | Async-aware Alembic env reading `DATABASE_URL` from `Settings` |
| **Infra** | `src/config.py` | `pydantic-settings` `Settings` class |
| | `src/logging_config.py` | Stdlib logging configured at app startup |
| | `src/main.py` | FastAPI app, lifespan, router registration |

---

## 3. Data flow — Bulk import

```mermaid
sequenceDiagram
    participant C as Client
    participant API as POST /tickets/import
    participant Imp as TicketImporter
    participant P as CSV/JSON/XML Parser
    participant V as Pydantic TicketCreate
    participant DB as PostgreSQL

    C->>API: multipart file=sample.csv
    API->>API: check Content-Length ≤ MAX_UPLOAD_SIZE_BYTES
    alt file too large
        API-->>C: 413 RequestEntityTooLarge
    end
    API->>API: detect parser by filename suffix
    alt unsupported extension
        API-->>C: 400 Bad Request
    end
    API->>API: read body bytes
    API->>Imp: import_records(parser, content)
    Imp->>P: parse(content) → Iterable[dict]
    alt parser raises ParserError
        P-->>Imp: ParserError(msg)
        Imp-->>API: ImportSummary(failed=1, errors=[row 0])
    else parsed OK
        loop for each raw record
            Imp->>V: TicketCreate.model_validate(raw)
            alt validation error
                V-->>Imp: ValidationError
                Imp->>Imp: append ImportItemError(row=N, error=...)
            else valid
                Imp->>DB: INSERT ticket
                alt DB error
                    DB-->>Imp: SQLAlchemyError
                    Imp->>DB: ROLLBACK
                    Imp->>Imp: append ImportItemError(row=N, error=...)
                else success
                    DB-->>Imp: ticket_id
                    Imp->>Imp: append created_id
                end
            end
        end
        Imp-->>API: ImportSummary(total, successful, failed, errors[], created_ids[])
    end
    API-->>C: 200 ImportSummary JSON
```

---

## 4. Data flow — Auto-classification

```mermaid
sequenceDiagram
    participant C as Client
    participant API as POST /tickets/{id}/auto-classify
    participant CS as ClassificationService
    participant Clf as TicketClassifier
    participant Pri as PriorityClassifier
    participant Cat as CategoryClassifier
    participant DB as PostgreSQL
    participant Log as logger.info

    C->>API: POST /tickets/{id}/auto-classify
    API->>CS: classify_by_id(id)
    CS->>DB: SELECT * FROM tickets WHERE id=:id
    alt not found
        DB-->>CS: None
        CS-->>API: None
        API-->>C: 404 Ticket not found
    else found
        DB-->>CS: Ticket row
        CS->>Clf: classify(subject, description)
        Clf->>Pri: classify(text)
        Note over Pri: substring match against<br/>urgent/high/low keywords<br/>(precedence-based)
        Pri-->>Clf: priority + confidence + keywords
        Clf->>Cat: classify(text)
        Note over Cat: substring match across<br/>5 categories<br/>(highest count wins)
        Cat-->>Clf: category + confidence + keywords
        Clf-->>CS: ClassificationResult
        CS->>DB: UPDATE category, priority, classification_confidence
        DB-->>CS: ok
        CS->>Log: auto_classify ticket=... priority=... confidence=...
        CS-->>API: (ticket, ClassificationResult)
        API-->>C: 200 ClassificationResult JSON
    end
```

---

## 5. Architectural Decision Records

### ADR-001 — Layered architecture (api → services → models)

**Context.** FastAPI examples often mix DB queries directly in route handlers. For a system with bulk-import and classification logic, this conflates concerns.

**Decision.** Strict layers:
- `api/` validates request (Pydantic), calls a service method, formats response. No DB queries here.
- `services/` owns business logic, transactions, error mapping.
- `models/` is the ORM only — no business rules.

**Consequences.** Slightly more files, but easier to test each layer in isolation, easier to swap persistence later. Also makes `dependency_overrides` in tests trivial.

### ADR-002 — DTOs (Pydantic) ≠ ORM models

**Context.** Tempting to reuse one class for both API contract and DB schema.

**Decision.** Two separate hierarchies. `Ticket` (ORM) lives in `models/`; `TicketCreate` / `TicketUpdate` / `TicketRead` (Pydantic) live in `schemas/`.

**Consequences.** Some duplication (today). But API contract can evolve without migrations, and ORM can add internal fields without leaking to clients.

### ADR-003 — PostgreSQL everywhere (no SQLite for tests)

**Context.** SQLite for tests is faster but uses a different SQL dialect. The project uses `JSONB`, native `ENUM`, `ARRAY` — none portable to SQLite without compromise.

**Decision.** PostgreSQL 17 for dev, test, prod. Tests run against a separate `tickets_test` DB created at session start, populated by `alembic upgrade head` via subprocess.

**Trade-offs.**
- ✅ Full prod-test parity, no "works on my machine" surprises
- ✅ Free use of PG-only features (`JSONB`, `ENUM`, `ARRAY`)
- ❌ Tests need Docker locally and `services: postgres:17-alpine` in CI
- ❌ Cold-start of test session ~2s longer than SQLite-in-memory

### ADR-004 — Rule-based classifier, no LLM in runtime

**Context.** TASKS.md describes "Auto-Classification" with `confidence` and `reasoning` fields — superficially LLM-friendly. The course is about GenAI, so the temptation is to call an LLM.

**Decision.** Pure rule-based keyword matching:
- **Priority** — keywords are listed verbatim in `TASKS.md` (`"can't access"`, `"critical"`, etc.)
- **Category** — keyword sets derived from problem-domain examples in the spec (`account_access` ← `login/password/2FA`, etc.)

**Reasoning.**
1. The spec describes priority as literal keywords — this is rule-based by design.
2. The course's "Use AI tools" guidance refers to the **development process** (Cursor, Claude Code), not putting LLMs in every product feature.
3. Past homework was marked down for over-engineering (added rate-limiter that wasn't asked for) — same restraint applies here.
4. Tests become deterministic and fast. No API key in CI. No flaky network calls.

**Consequences.** Confidence formula = `matched_keywords / total_in_winning_category`, clamped `[0, 1]`. For default cases (no match → `medium` priority / `other` category), confidence = `0.5` to indicate "neutral".

### ADR-005 — Postgres ENUM with `values_callable`

**Issue.** SQLAlchemy 2.0's default `PgEnum(MyEnum)` maps Python enum members by **name** (UPPERCASE), but `TASKS.md` requires lowercase values (`account_access`, `urgent`, etc.).

**Decision.** Always pass `values_callable=lambda obj: [e.value for e in obj]` to PG ENUM column types. Verified by inspecting Alembic-generated SQL.

### ADR-006 — `concurrency = ["thread", "greenlet"]` for coverage

**Issue.** SQLAlchemy async uses greenlet internally to bridge sync↔async boundaries (e.g. inside ORM relationship loading). Default `pytest-cov` does not trace code executed under greenlet, leading to **false** "not covered" reports for any code reached via the ORM.

**Symptom.** API endpoints showed 67% coverage despite 12 passing tests directly hitting them.

**Decision.** Set `concurrency = ["thread", "greenlet"]` in `[tool.coverage.run]`. Coverage jumped 89% → 97.80%.

### ADR-007 — `MAX_UPLOAD_SIZE_BYTES` env-driven

**Issue.** Bulk import with no size limit invites OOM. Hard-coding 100 MiB feels arbitrary.

**Decision.** Configurable via `MAX_UPLOAD_SIZE_BYTES` env var (default `512 * 1024 * 1024` = 512 MiB). Checked at endpoint **twice**: once via `Content-Length` header (cheap, before reading), once after `file.read()` (defence in depth, since clients can lie).

**Consequences.** Documented in `.env.example` with a comment explaining how the value relates to worker memory and request timeout. Engineer can confidently raise/lower it without re-reading the code.

---

## 6. Performance considerations

- **Server-side `gen_random_uuid()` for PK** — avoids round-trip for ID generation; works under concurrent inserts.
- **Indexes** on `category`, `priority`, `status`, `created_at`, `customer_email`, `customer_id` — supports filter combinations and sorted listing.
- **`order_by(Ticket.created_at.desc())` + LIMIT/OFFSET** — pagination is index-backed.
- **Per-row commit in importer** — 1000 rows take ~1.7s on a Mac M-series. Easier reasoning about partial failures than batched commits with savepoints. If higher throughput is needed, switch to `INSERT ... RETURNING id` with COPY-style batching.
- **Async stack throughout** — `asyncpg` driver, `AsyncSession`, `AsyncClient` in tests. No sync DB calls in async paths.
- **`pool_pre_ping=True`** on engine — survives idle connection drops without tail latency on first request after idle.
- **Concurrent benchmark** — 25 simultaneous `POST /tickets` complete in well under 10s with default pool.

---

## 7. Security considerations

| Concern | Mitigation |
|---|---|
| **Secrets in repo** | `.env` is gitignored; `.env.example` shows shape only. `DATABASE_URL` for prod via platform env vars (Render / Railway / RDS). |
| **SQL injection** | All queries via SQLAlchemy parameterized statements. Raw `text()` only used in tests for malformed-enum verification. |
| **DoS via bulk upload** | `MAX_UPLOAD_SIZE_BYTES` cap (512 MiB default), enforced at both Content-Length and post-read. |
| **XML XXE attacks** | `xml.etree.ElementTree.fromstring` (stdlib) is annotated with `# noqa: S314`. The application is course-internal; clients are authenticated upstream. For a public deployment, swap to `defusedxml`. |
| **PII in logs** | Classification logs include ticket UUID, category, priority, confidence — no PII (no email, name, message body). |
| **CORS** | Not enabled (out of scope for `TASKS.md`). Add `CORSMiddleware` if exposing to browser clients. |
| **Auth / Authorization** | Not implemented — out of scope. All endpoints are open. |

---

## 8. Future improvements (not in scope)

- **Webhook notifications** on ticket status change
- **Full-text search** on subject/description (Postgres `tsvector` + `GIN` index)
- **Audit log** as an append-only table (`ticket_history`)
- **LLM-augmented classifier** as opt-in `?use_llm=true` parameter
- **Pre-signed S3 upload URLs** for files > 512 MiB to bypass app worker memory
