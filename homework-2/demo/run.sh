#!/usr/bin/env bash
# Boot the full stack (Postgres + FastAPI app via Docker Compose) and tail logs.
# Use Ctrl+C to stop tailing logs — containers keep running.
# Run `docker compose down` to stop and remove containers.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "✗ Docker not installed — see https://docs.docker.com/get-docker/" >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "→ Creating .env from .env.example"
  cp .env.example .env
fi

echo "→ Building images and starting services..."
docker compose up -d --build

echo "→ Waiting for app health..."
for _ in {1..30}; do
  if curl -fsS http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "✓ App is up at http://localhost:8000"
    echo "  Swagger UI:   http://localhost:8000/docs"
    echo "  OpenAPI JSON: http://localhost:8000/openapi.json"
    echo
    echo "→ Tailing app logs (Ctrl+C to stop tailing — containers keep running)"
    docker compose logs -f app
    exit 0
  fi
  sleep 1
done

echo "✗ App did not become healthy within 30s. Inspect logs:" >&2
docker compose logs --tail=50 app >&2
exit 1
