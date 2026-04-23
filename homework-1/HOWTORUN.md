# ▶️ How to Run

## 🔧 Вимоги

- **Node.js** ≥ 20.0 (протестовано на 20/23)
- **npm** ≥ 10

```bash
node --version
npm --version
```

## 📦 Встановлення

```bash
cd homeworks/homework-1
npm install
```

## 🔐 Змінні оточення

```bash
cp .env.example .env
```

| Змінна | Опис | За замовчуванням |
|--------|------|------------------|
| `PORT` | Порт HTTP-сервера | `3000` |
| `RATE_LIMIT_WINDOW_MS` | Вікно rate limiter'а (мс) | `60000` |
| `RATE_LIMIT_MAX` | Максимум запитів на IP у вікні | `100` |

## 🚀 Запуск

```bash
# Через demo-скрипт
./demo/run.sh

# Або напряму
npm start         # продакшн-режим
npm run dev       # з --watch (автоперезапуск на зміни)
```

Сервер доступний на `http://localhost:3000`.

Швидка перевірка:

```bash
curl http://localhost:3000/health
# {"status":"ok"}
```

## 🧪 Тестування

```bash
npm test                # всі тести
npm run test:watch      # watch-режим
npm run test:coverage   # з coverage (поріг ≥70%)
```

Coverage-звіт — у `coverage/lcov-report/index.html`.

## 🧹 Лінт і форматування

```bash
npm run lint            # перевірка
npm run lint:fix        # автофікс
npm run format          # Prettier форматування
```

## 📬 Ручне тестування

Готові приклади запитів — у [`demo/sample-requests.http`](./demo/sample-requests.http) (сумісно з VS Code REST Client / IntelliJ HTTP Client).

```bash
curl -X POST http://localhost:3000/transactions \
  -H "Content-Type: application/json" \
  -d '{"fromAccount":"ACC-12345","toAccount":"ACC-67890","amount":100.50,"currency":"USD","type":"transfer"}'
```

## 🛑 Зупинка

`Ctrl+C` у терміналі запуску.
