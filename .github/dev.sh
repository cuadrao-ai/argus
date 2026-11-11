#!/bin/bash
# Dev Mode: fast iteration with memory persistence and synthetic data.
# Usage: .github/dev.sh
#
# This script is authoritative for backend dev-mode runtime flags. The root
# .env file provides secrets/defaults when present, but mode flags below win.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/argus-env.sh"

if ! argus_load_root_env; then
  echo "⚠️  Root .env missing. Dev mode can still start with synthetic assets,"
  echo "   select CUADRAO_LOCAL_ENV_STORE when you need credentials."
  set -u
fi

argus_export_dev_mode
# Dev mode is intentionally memory-only even if .env contains typed Supabase
# Postgres URLs such as SUPABASE_POSTGRES_SESSION_POOLER_URL.

echo "🔵 Dev Mode activated:"
echo "   - Persistence: Memory (ephemeral)"
echo "   - Market Data: Synthetic fixtures (no API calls)"
echo "   - Disk market-data cache: Disabled"
echo "   - Fallback: Tolerant (keeps going on errors)"
echo "   - Runtime checkpoints: Memory"
echo "   - Database URLs: Ignored"
echo "   - Receipt reads: None (memory has no shared queue; uploads stay queued)"
echo ""
echo "Starting FastAPI backend on http://127.0.0.1:8000"
echo ""

poetry run fastapi dev src/argus/api/main.py
