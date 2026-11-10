#!/bin/bash
# QA Mode: production-parity browser QA.
# Usage: .github/qa.sh
#
# This script is authoritative for backend QA runtime flags. It intentionally
# uses real Supabase persistence, strict failures, Postgres checkpoints, and the
# live provider catalog so manual QA catches provider-resolution issues.

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/argus-env.sh"

if ! argus_load_root_env; then
  echo "Root .env missing; select CUADRAO_LOCAL_ENV_STORE first." >&2
  exit 1
fi
bash "$SCRIPT_DIR/../scripts/qa/assert-nonprod-target.sh"
argus_require_qa_env
argus_export_qa_mode
# SUPABASE_POSTGRES_DIRECT_URL and SUPABASE_POSTGRES_TRANSACTION_POOLER_URL may
# be present in .env for migrations or future serverless-style clients. QA uses
# session pooling for the persistent local backend/checkpointer runtime.

echo "🟢 QA Mode activated:"
echo "   - Persistence: Supabase (durable)"
echo "   - Market Data: Live provider catalog (production-like asset resolution)"
echo "   - Fallback: Strict (errors exposed for debugging)"
echo "   - Runtime checkpoints: Postgres"
echo "   - Database URL: Session Pooler -> internal DATABASE_URL"
echo "   - Receipt reads: python -m workflows.document_worker (the only reader)"
echo ""
echo "Frontend QA reminder:"
echo "   web/.env.local should use NEXT_PUBLIC_MOCK_AUTH=false for real auth"
echo "   and NEXT_PUBLIC_CUADRAO_API_URL=http://127.0.0.1:8000/api/v1"
echo ""
echo "Starting the document worker and FastAPI backend on http://127.0.0.1:8000"
echo ""

# The API never reads a receipt; the worker pulls each queued read from Postgres.
poetry run python -m workflows.document_worker &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true; wait "$worker_pid" 2>/dev/null || true' EXIT

poetry run fastapi dev src/argus/api/main.py
