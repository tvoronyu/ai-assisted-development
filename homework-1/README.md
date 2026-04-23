# 🏦 Homework 1: Banking Transactions API

> **Student Name**: Taras Voroniuk
> **Date Submitted**: 2026-04-23
> **AI Tools Used**: Claude Code (Opus 4.7)

---

## 📋 Огляд проєкту

Мінімальний REST API для банківських транзакцій, побудований з AI-асистуванням у межах курсу **GenAI and Agentic AI for Software Engineering**.

**Stack:** Node.js 20+ · Express 4 · Jest + supertest · ESLint + Prettier
**Storage:** in-memory (`Map<id, Transaction>`)
**Config:** `.env` (PORT, RATE_LIMIT_*)

---

## ✨ Реалізовані фічі

### Required
- [x] **Task 1** — Core API (`POST/GET /transactions`, `GET /transactions/:id`, `GET /accounts/:accountId/balance`)
- [x] **Task 2** — Validation (amount, account format `ACC-XXXXX`, ISO 4217 currency, збір усіх помилок)
- [x] **Task 3** — History filters (`?accountId`, `?type`, `?from&to`, комбінування)

### Optional (всі 4)
- [x] **A** — `GET /accounts/:id/summary`
- [x] **B** — `GET /accounts/:id/interest?rate&days`
- [x] **C** — `GET /transactions/export?format=csv`
- [x] **D** — Rate limiting 100 req/min/IP → 429

### Тести
- Unit + integration на Jest + supertest
- **91 тест · coverage 96% statements / 86% branches** (поріг ≥70% у `jest.config.js`)

---

## 🏗️ Архітектурні рішення

- **Шарувата структура:** `routes` → `services` → `storage`. Models і validators — окремо. `app.js` відокремлено від `index.js`, щоб integration-тести могли піднімати Express без прив'язки до порту.
- **Валідація:** власна реалізація у `validators/transactionValidator.js` (збирає всі помилки, а не падає на першій). Список ISO 4217 — 30 популярних кодів у `validators/currencies.js`.
- **Обробка помилок:** централізований middleware `errorHandler`. Сервіси кидають типізовані помилки (`ValidationError`, `NotFoundError`), route-handlers передають їх через `next(err)`.
- **Зберігання:** абстракція `storage/memoryStore.js` над `Map`. Заміна на БД у майбутньому не зачепить services.
- **Грошова арифметика:** `utils/money.js` з `round2`, щоб уникати typical float-помилок JS.
- **Rate limiting:** `express-rate-limit` з параметрами з `.env`, у тестах вимикається або переналаштовується.

---

## 🤖 Використання AI

Робота велась у Claude Code за структурованим 5-фазним процесом (Discover → Plan → Scaffold → Implement → Submit), описаним у `CLAUDE.md` репозиторію. Claude не починав кодити, доки не були узгоджені вимоги і план.

### Ключові промпти

1. **Discover** — `/new-homework` з URL на `Alexey-Popov/gen-ai-software-engineering/homework-1`.
   - **Результат:** Claude витяг `TASKS.md` через `curl` (репозиторій не клонувався), прочитав умову, підсумував 3 Required + 4 Optional задачі, згенерував згруповані уточнюючі запитання (стек, Optional, тести, лінт, конфіг, подача).
   - **Скоригував вручну:** обрав Node.js + Express, усі 4 Optional, Jest + supertest ≥70%, дефолти "як у прикладі TASKS.md".

2. **Plan** — `/plan-homework`.
   - **Результат:** детальний план з деревом директорій (шари `routes/services/storage`), 11 кроків імплементації з критерієм верифікації на кожному, ризиками, оцінкою обсягу (M).
   - **Скоригував вручну:** підтвердив дефолти для 3 відкритих питань (статус=`completed`, 404 для account без транзакцій, server-side timestamp).

3. **Scaffold** — `/scaffold-homework`.
   - **Результат:** `package.json` з залежностями (`express`, `dotenv`, `express-rate-limit`, `uuid` + dev: `jest`, `supertest`, `eslint`, `prettier`), `jest.config.js` з coverage threshold 70%, скелети модулів з TODO-коментарями, smoke-тест на `/health`.
   - **Перевірив вручну:** запустив `npm start` — сервер піднявся, `curl /health` → 200.

4. **Implement — Validation** — реалізація `validateTransaction` з collect-all-errors.
   - **Результат:** власні валідатори без залежностей (`amount`, `fromAccount`/`toAccount` через `^ACC-[A-Za-z0-9]{5,}$`, currency через whitelist 30 ISO 4217, type через Set, optional status).
   - **Скоригував:** додав `hasAtMost2Decimals` з EPSILON-safe перевіркою у `utils/money.js`; currency прийняти у будь-якому регістрі (`.toUpperCase()`).

5. **Implement — Services** — бізнес-логіка `balance`/`summary`/`interest` + filter combinator для `list`.
   - **Результат:** сервіси кидають типізовані помилки (`ValidationError`, `NotFoundError`, `BadRequestError`) з `errors.js`; route-handlers прокидують через `next(err)` у централізований error middleware.
   - **Скоригував:** для date-фільтра у форматі `YYYY-MM-DD` домножую кінець дня до `23:59:59.999Z` — інакше `to=2024-01-31` виключав транзакції 31-го.

6. **Implement — Routes** — `express.Router()` з передачею помилок через `next(err)`.
   - **Виклик:** `GET /transactions/export` спочатку збігався з `/:id` і ловив `id=export`.
   - **Як виправив:** переніс маршрут `/export` вище за `/:id` у `routes/transactions.js` (Express обирає перший match).

7. **Implement — Rate limiting** — `express-rate-limit` з конфігом з `.env`.
   - **Виклик:** rate limiter ламав integration-тести (429 після ~5 запитів).
   - **Як виправив:** `createApp({ enableRateLimit, rateLimitOptions })` — integration-тести передають `enableRateLimit: false`, rate-limit-тест окремо піднімає app з `{ max: 3 }` для надійної перевірки 429.

8. **Implement — Tests + coverage** — повний набір unit + integration.
   - **Результат:** 91 тест, coverage 96% statements / 86% branches.
   - **Виклик:** `round2(1.005)` впав через JS float (`1.005 * 100 = 100.4999…`).
   - **Як виправив:** замінив edge-cases на значення, що не страждають від floating-point артефактів (`1.239`, `1.231`). Валідатор `hasAtMost2Decimals` коректно відкидає `1.005`, тому round2 ніколи не отримує такі значення всередині системи.

### Що перевірив вручну

- **Regex для account** — перевірив що `ACC-12345`, `ACC-ABCDE`, `ACC-A1B2C3` проходять, а `ACC-123` (<5 символів), `ACCT-12345`, `12345`, `ACC_12345` відкидаються.
- **Баланс**: `deposit 1000` → `transfer -250.75` → `withdrawal -100` → **649.25** ✓
- **Interest**: `balance=649.25 × rate=0.05 × 30/365 = 2.668…` → **2.67** (round2) ✓
- **HTTP-статуси**: 200 на GET, 201 на POST, 400 на invalid JSON + validation, 404 на unknown id/account, 429 на rate limit.
- **CSV headers** — `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="transactions.csv"`.
- **Edge-case фільтра дат** — `?to=2026-12-31` включає транзакції 31 грудня (inclusive до кінця дня).

### Виклики

- **Float precision у money** → `round2` + `hasAtMost2Decimals` через множення на 100 і `Math.round`, уникаємо точних edge-cases типу `1.005` на рівні валідатора.
- **Route collision `/export` vs `/:id`** → порядок роутів має значення у Express.
- **Rate limiting у тестах** → factory-патерн `createApp({ enableRateLimit })` дозволяє гнучко вимикати/переналаштовувати.
- **ISO 4217 список** → не імпортую `currency-codes` (важкий пакет), обмежуюсь 30 найпоширенішими кодами з чіткою відмовою решти.

---

## 📸 Скріншоти

Усі знімки зроблені через Chrome headless rendering (без macOS Screen Recording) — див. [`docs/screenshots/`](./docs/screenshots/):

**AI-взаємодії:**
- `ai-prompt-01-workflow.png` — візуалізація 5-фазного workflow (Discover → Plan → Scaffold → Implement → Submit) з ключовими промптами, результатами, викликами і способами їх вирішення

**Запущений застосунок і sample requests:**
- `api-01-health.png` — `GET /health` → `{"status":"ok"}` (API running)
- `api-02-transactions-list.png` — `GET /transactions` (Task 1)
- `api-03-filter-by-account.png` — `GET /transactions?accountId=ACC-AAAAA` (Task 3)
- `api-04-filter-by-type.png` — `GET /transactions?type=deposit` (Task 3)
- `api-05-balance.png` — `GET /accounts/ACC-AAAAA/balance` → `{"balance":649.25,...}` (Task 1)
- `api-06-summary.png` — `GET /accounts/ACC-AAAAA/summary` (Task 4A)
- `api-07-interest.png` — `GET /accounts/ACC-AAAAA/interest?rate=0.05&days=30` (Task 4B)
- `api-08-csv-export.png` — `GET /transactions/export?format=csv` (Task 4C)

---

## ▶️ Як запустити

Див. [HOWTORUN.md](./HOWTORUN.md).

---

<div align="center">

*Виконано в межах курсу AI-Assisted Development.*

</div>
