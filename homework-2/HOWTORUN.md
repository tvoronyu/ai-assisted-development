# ▶️ How to Run

Усе виконується через **Docker Compose** — нічого не встановлюється локально (ні Python, ні Postgres, ні pip-залежності).

## 🔧 Вимоги

- **Docker Desktop** ≥ 4.x (включає Docker Engine та Docker Compose v2)
- 2 GB вільної пам'яті, ~500 MB на образи

```bash
docker --version              # ≥ 24
docker compose version        # ≥ v2.20
```

## 🔐 Змінні оточення

Скопіювати `.env.example` у `.env` (Compose автоматично підхопить):

```bash
cp .env.example .env
```

| Змінна | Опис | За замовчуванням |
|--------|------|------------------|
| `DATABASE_URL` | DSN до PostgreSQL (asyncpg) | `postgresql+asyncpg://tickets:tickets@postgres:5432/tickets` |
| `MAX_UPLOAD_SIZE_BYTES` | Граничний розмір файла bulk-import | `536870912` (512 MiB) |
| `LOG_LEVEL` | Рівень логування | `INFO` |
| `APP_ENV` | development \| test \| production | `production` |

> Усередині docker-network host для БД — `postgres` (ім'я сервісу), порт `5432`. Усі сервіси отримують це автоматично через compose.

## 🚀 Запуск повного стеку (Postgres + FastAPI app)

```bash
docker compose up -d --build
```

Що відбувається:
1. **Build образу** `homework-2-app` з Dockerfile (multistage: `builder` → `runtime` → `test`).
2. **Postgres 17-alpine** стартує з healthcheck (`pg_isready`).
3. **App** дочікується статусу `healthy` Postgres-а (`depends_on: condition: service_healthy`).
4. **Auto-міграції:** при кожному старті app виконує `alembic upgrade head`, потім запускає `uvicorn src.main:app --host 0.0.0.0 --port 8000`. Якщо migration падає — контейнер виходить з помилкою, Compose його перезапускає (`restart: unless-stopped`) до успіху.

Перевірка:

```bash
docker compose ps              # обидва сервіси (healthy)
curl http://localhost:8000/healthz   # → {"status":"ok"}
```

Інтерактивна документація:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI JSON: <http://localhost:8000/openapi.json>

## 🧪 Тестування — теж через Docker

Окремий профіль `test` із власним build target. Запуск однією командою:

```bash
docker compose --profile test run --rm tests
```

Що відбувається:
1. Build образу з `target: test` (runtime + dev deps + tests/).
2. Тестовий контейнер дочікується Postgres-а.
3. Запускається `pytest --cov=src --cov-report=term-missing`.
4. Тести самостійно створюють/мігрують `tickets_test` БД у тому ж Postgres-і та truncate-ять таблиці після кожного тесту.
5. Контейнер видаляється (`--rm`) — лишається лише exit code.

Очікуваний результат: **67 passed in ~50s**, coverage **97.80%** (gate 85%).

### Запуск підмножини тестів

```bash
# Швидкі unit
docker compose --profile test run --rm tests pytest -m unit

# Лише integration (без performance)
docker compose --profile test run --rm tests pytest -m integration

# Лише один файл
docker compose --profile test run --rm tests pytest tests/test_ticket_api.py -v

# Скип performance (швидко локально)
docker compose --profile test run --rm tests pytest -m "not performance"
```

### HTML coverage report

```bash
docker compose --profile test run --rm tests \
  pytest --cov=src --cov-report=html
# Звіт лишиться у /app/htmlcov у тимчасовому контейнері — переадресуй у файл:
docker compose --profile test run --rm \
  -v "$(pwd)/htmlcov:/app/htmlcov" tests \
  pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## 🔍 Лінт і типи (опційно, через docker)

```bash
docker compose --profile test run --rm tests ruff check src/ tests/ alembic/env.py
docker compose --profile test run --rm tests pyright src/ tests/
```

## ✅ Ручне тестування

Приклади запитів — у [`demo/sample-requests.http`](./demo/sample-requests.http) (відкрий у VSCode REST Client або JetBrains HTTP Client).

```bash
# Healthcheck
curl http://localhost:8000/healthz

# Створити квиток (з auto-classification)
curl -X POST 'http://localhost:8000/tickets?auto_classify=true' \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "demo",
    "customer_email": "demo@example.com",
    "customer_name": "Demo",
    "subject": "Cannot login",
    "description": "Production down. Cannot access account. Critical security issue."
  }'

# Bulk import з CSV
curl -X POST http://localhost:8000/tickets/import \
  -F "file=@tests/fixtures/sample_tickets.csv"

# Класифікувати existing ticket
curl -X POST http://localhost:8000/tickets/<UUID>/auto-classify
```

## 🛑 Зупинка та очищення

```bash
docker compose down            # зупинити контейнери, volume лишається
docker compose down -v         # + видалити volume Postgres (втрата даних)
docker compose down --rmi all  # + видалити образи
```

## 🚀 Quick start (TL;DR)

```bash
git clone https://github.com/tvoronyu/ai-assisted-development.git
cd ai-assisted-development/homework-2
cp .env.example .env
docker compose up -d --build
docker compose --profile test run --rm tests   # переконатися: 67 passed, 97.80% coverage
open http://localhost:8000/docs
```
