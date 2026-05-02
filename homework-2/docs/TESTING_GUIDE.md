# 🧪 Testing Guide — Customer Support Ticket System

> Audience: QA engineers, developers verifying the test suite.

---

## 1. Test pyramid

```mermaid
graph TD
    Perf["Performance / Benchmarks<br/>5 tests · ~30s"]
    Integ["Integration / API E2E<br/>52 tests · ~10s<br/>real HTTP via httpx + real PostgreSQL"]
    Unit["Unit / Pure Python<br/>10 tests · &lt;1s<br/>classifier rules + logging config"]

    Perf --> Integ
    Integ --> Unit

    style Perf fill:#fee,stroke:#c33
    style Integ fill:#ffe,stroke:#cc3
    style Unit fill:#efe,stroke:#3c3
```

| Tier | Marker | What it verifies |
|---|---|---|
| **Unit** | `@pytest.mark.unit` | Pure Python: classifier keyword matching (priority + category), logging config bootstrap |
| **Integration** | `@pytest.mark.integration` | Full HTTP stack via `httpx.AsyncClient` against the FastAPI app, real PostgreSQL, real Alembic migrations applied to `tickets_test` |
| **Performance** | `@pytest.mark.performance` | Latency / throughput / concurrency benchmarks — verify the system meets the timing thresholds in the spec |

---

## 2. How to run — everything via Docker

### Pre-req

Docker Desktop running. Postgres + app launch with one command — but they are NOT required for the test run because the test profile has its own Postgres dependency.

### All tests + coverage report

```bash
docker compose --profile test run --rm tests
```

What happens:

1. Compose builds the `test` stage of the Dockerfile (runtime image + dev deps + `tests/`).
2. Postgres service starts (or reuses existing one) and reaches `healthy`.
3. Tests container runs `pytest --cov=src --cov-report=term-missing`.
4. After exit the container is removed (`--rm`).

Expected output: **67 passed in ~50s**, coverage **97.80%** (gate 85%).

### Filter by marker

Override the default `pytest` command:

```bash
# Fast unit tests only
docker compose --profile test run --rm tests pytest -m unit

# Integration only (no perf)
docker compose --profile test run --rm tests pytest -m integration

# Performance only
docker compose --profile test run --rm tests pytest -m performance

# Skip slow performance suite
docker compose --profile test run --rm tests pytest -m "not performance"
```

### Filter by file or test name

```bash
# Single file
docker compose --profile test run --rm tests pytest tests/test_ticket_api.py -v

# Single test
docker compose --profile test run --rm tests pytest tests/test_ticket_model.py::test_subject_max_length_200

# By substring
docker compose --profile test run --rm tests pytest -k "auto_classify"
```

### HTML coverage report

Mount a host directory so the report survives container removal:

```bash
docker compose --profile test run --rm \
  -v "$(pwd)/htmlcov:/app/htmlcov" tests \
  pytest --cov=src --cov-report=html

open htmlcov/index.html
```

---

## 3. Test data

| Path | Purpose | Records |
|---|---|---|
| `tests/fixtures/sample_tickets.csv` | Valid CSV bulk import | 50 |
| `tests/fixtures/sample_tickets.json` | Valid JSON bulk import | 20 |
| `tests/fixtures/sample_tickets.xml` | Valid XML bulk import | 30 |
| `tests/fixtures/invalid_tickets.csv` | 3 invalid rows: bad email, missing name, short description | 3 |
| `tests/fixtures/invalid_tickets.json` | Truncated JSON (parser-level error) | — |
| `tests/fixtures/invalid_tickets.xml` | Unclosed tag (parser-level error) | — |

Generated via deterministic Python script with `random.seed(42)` — re-runnable.

In-test payloads use a `_payload(**overrides)` helper to keep the noise low; tests only state what they care about.

---

## 4. Test isolation strategy

```mermaid
sequenceDiagram
    participant pytest
    participant conftest as conftest.py
    participant pg as PostgreSQL admin
    participant alembic as alembic upgrade
    participant test_db as tickets_test DB

    pytest->>conftest: session start
    conftest->>pg: DROP / CREATE tickets_test
    conftest->>alembic: subprocess: alembic upgrade head
    alembic->>test_db: schema applied

    loop per test
        pytest->>conftest: test starts
        conftest->>test_db: AsyncSession
        Note over test_db: test runs assertions
        pytest->>conftest: test ends
        conftest->>test_db: TRUNCATE TABLE tickets RESTART IDENTITY CASCADE
    end

    pytest->>conftest: session end
    conftest->>conftest: dispose engine
```

- **Session-scoped** `test_engine` fixture creates `tickets_test` DB and runs Alembic.
- **Function-scoped** `db_session` and `client` fixtures truncate `tickets` after each test → independent test runs in any order.
- `client` fixture uses FastAPI's `app.dependency_overrides[get_session]` to inject the test session into the app stack.

---

## 5. Performance benchmarks

| Test | Target | Actual (M-series Mac, local Docker) |
|---|---|---|
| 25 concurrent `POST /tickets` | < 10s | ~0.5s |
| Bulk import 50 CSV records | < 5s | ~0.2s |
| Bulk import 1000 CSV records, then `GET /tickets?limit=200` | list < 2s | ~50ms |
| Classifier 100 invocations (sync, no DB) | < 1s | ~5ms |
| `GET /tickets/{id}` p95 latency over 50 calls | < 200ms | ~5ms |

The thresholds are **conservative** — designed to pass on slower CI runners. If a test fails on your machine, it's a real regression, not flake.

---

## 6. Manual testing checklist (pre-submit)

After all automated tests pass, sanity-check the user journeys:

### 6.1 Healthz + start

- [ ] `docker compose up -d --build` — postgres and app become `healthy`
- [ ] App auto-applies `alembic upgrade head` on start (visible in `docker compose logs app`)
- [ ] `curl http://localhost:8000/healthz` → `200 {"status":"ok"}`
- [ ] Open `http://localhost:8000/docs` — Swagger UI lists 8 endpoints

### 6.2 CRUD

- [ ] `POST /tickets` with valid body → `201`, returns full payload
- [ ] `POST /tickets` with `customer_email: "broken"` → `422`
- [ ] `POST /tickets` with `description: "short"` → `422`
- [ ] `GET /tickets/{id}` → `200`
- [ ] `GET /tickets/00000000-...` → `404`
- [ ] `GET /tickets?limit=10` → 10 items + total
- [ ] `GET /tickets?category=billing_question` → only billing
- [ ] `PUT /tickets/{id}` with `{"status": "in_progress"}` → status changes, other fields preserved
- [ ] `DELETE /tickets/{id}` → `204`, then `GET` → `404`

### 6.3 Bulk import

- [ ] `POST /tickets/import` with `sample_tickets.csv` → `successful: 50`
- [ ] `POST /tickets/import` with `sample_tickets.json` → `successful: 20`
- [ ] `POST /tickets/import` with `sample_tickets.xml` → `successful: 30`
- [ ] `POST /tickets/import` with `invalid_tickets.csv` → `successful: 0, failed: 3`, three error rows
- [ ] `POST /tickets/import` with a `.txt` file → `400`

### 6.4 Auto-classification

- [ ] `POST /tickets/{id}/auto-classify` for a "production down" ticket → `priority: urgent`
- [ ] `POST /tickets/{id}/auto-classify` for a "refund invoice" ticket → `category: billing_question`
- [ ] `POST /tickets/{id}/auto-classify` on `00000000-...` → `404`
- [ ] `POST /tickets?auto_classify=true` with valid body → returned ticket already has classified fields
- [ ] `PUT /tickets/{id}` with manual `category: feature_request` overrides classifier → next `GET` reflects override

### 6.5 Logs

- [ ] In server stdout, classification calls produce a line like:
  `INFO src.services.classification_service: auto_classify ticket=<uuid> category=urgent priority=account_access confidence=0.45`

---

## 7. Coverage breakdown — what's not at 100%

| Module | Coverage | Why |
|---|---|---|
| `src/api/import_.py` | 88% | The 413 (file > 512 MiB) path is hard to test without generating a 500+ MiB file in fixtures — chose not to. |
| `src/parsers/csv_parser.py` | 91% | UnicodeDecodeError path requires deliberately corrupt UTF-8 bytes. |
| `src/parsers/json_parser.py` | 90% | "Item is not an object" path requires JSON like `[1, 2]`. Not covered. |
| `src/services/importer.py` | 92% | DB-error rollback path (`SQLAlchemyError` mid-batch) requires mock or chaos injection. |

Total: **97.80%** — well above the 85% gate from `pyproject.toml`.

---

## 8. Linting & type checking

Через docker (тестовий image включає ruff і pyright):

```bash
docker compose --profile test run --rm tests ruff check src/ tests/ alembic/env.py
docker compose --profile test run --rm tests ruff format --check src/ tests/ alembic/env.py
docker compose --profile test run --rm tests pyright src/ tests/
```

All three should report 0 issues. Ruff selects `E, F, I, B, UP, S, N, SIM`; pyright runs in `basic` mode.
