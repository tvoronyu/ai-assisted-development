# ▶️ How to Run

## 🔧 Вимоги

- **Python 3.13** (встановлено через pyenv або системний)
- **Docker + Docker Compose** (для локального PostgreSQL 17)
- **make** (опціонально)

## 📦 Встановлення

```bash
cd homeworks/homework-2

# Створити та активувати virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Установити залежності (runtime + dev)
pip install -r requirements-dev.txt
```

## 🐘 Запустити PostgreSQL локально

```bash
docker compose up -d postgres
docker compose ps   # перевірити, що сервіс healthy
```

## 🔐 Змінні оточення

Скопіювати `.env.example` у `.env` і за потреби відредагувати:

```bash
cp .env.example .env
```

| Змінна | Опис | За замовчуванням |
|--------|------|------------------|
| `DATABASE_URL` | DSN до PostgreSQL (asyncpg) | `postgresql+asyncpg://tickets:tickets@localhost:5432/tickets` |
| `MAX_UPLOAD_SIZE_BYTES` | Граничний розмір файла для bulk import | `536870912` (512 MiB) |
| `LOG_LEVEL` | Рівень логування | `INFO` |
| `APP_ENV` | development \| test \| production | `development` |

## 🗄 Накотити міграції

```bash
.venv/bin/alembic upgrade head
```

## 🚀 Запуск API

```bash
.venv/bin/uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Сервер доступний на `http://127.0.0.1:8000`. Інтерактивна документація:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

## 🧪 Тестування

```bash
# Усі тести з покриттям
.venv/bin/pytest --cov=src --cov-report=term-missing

# Тільки unit / integration / performance
.venv/bin/pytest -m unit
.venv/bin/pytest -m integration
.venv/bin/pytest -m performance

# Згенерувати HTML coverage report
.venv/bin/pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## 🔍 Якість коду

```bash
.venv/bin/ruff check src/ tests/ alembic/env.py    # лінт
.venv/bin/ruff format src/ tests/ alembic/env.py   # форматування
.venv/bin/pyright src/ tests/                      # типи
```

## 📂 Створити нову Alembic-міграцію

```bash
.venv/bin/alembic revision --autogenerate -m "опис змін"
.venv/bin/alembic upgrade head
```

## ✅ Ручне тестування

Приклади запитів — у [`demo/sample-requests.http`](./demo/sample-requests.http).

```bash
# Healthcheck
curl http://127.0.0.1:8000/healthz

# Створити квиток
curl -X POST http://127.0.0.1:8000/tickets \
  -H "Content-Type: application/json" \
  -d @demo/sample_ticket.json

# Bulk import з CSV
curl -X POST http://127.0.0.1:8000/tickets/import \
  -F "file=@tests/fixtures/sample_tickets.csv"
```

## 🛑 Зупинка

```bash
# Зупинити uvicorn — Ctrl+C у терміналі

# Зупинити PostgreSQL контейнер
docker compose down

# Повністю видалити дані БД
docker compose down -v
```
