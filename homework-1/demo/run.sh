#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d node_modules ]; then
  echo "📦 Installing dependencies..."
  npm install
fi

if [ ! -f .env ]; then
  echo "🔐 Copying .env.example → .env"
  cp .env.example .env
fi

echo "🚀 Starting Banking Transactions API..."
exec npm start
