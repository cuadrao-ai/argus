#!/bin/bash
# One-shot local real-auth QA runner for issue #248.
# Sequence: nonprod guard -> QA-mode backend -> disposable identities ->
# Playwright recovery/session journeys against the real app on localhost:3000.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
bash scripts/qa/assert-nonprod-target.sh

# shellcheck disable=SC1091
source .github/argus-env.sh
argus_load_root_env
argus_require_qa_env
argus_export_qa_mode

EVIDENCE_DIR="$ROOT_DIR/temp/qa-evidence-248"
mkdir -p "$EVIDENCE_DIR"

BACKEND_PID=""
# Reap the old process fully so a health probe can never hit a dying server.
cleanup() {
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    BACKEND_PID=""
  fi
}
trap cleanup EXIT

start_backend() {
  cleanup
  poetry run uvicorn argus.api.main:app --host 127.0.0.1 --port 8000 \
    >> "$EVIDENCE_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!
  # An unauthenticated probe answers 401 once the API is serving requests.
  local code=""
  for _ in $(seq 1 60); do
    code="$(curl -s -o /dev/null -w "%{http_code}" \
      http://127.0.0.1:8000/api/v1/auth/session || true)"
    case "$code" in 200|401) return 0 ;; esac
    sleep 1
  done
  echo "❌ backend did not become healthy" >&2
  exit 1
}

start_backend
bash scripts/qa/setup-local-identities.sh

# One backend per spec file keeps the product's in-memory 8-attempts-per-email
# login limiter from throttling later journeys in the same run.
for spec in e2e/qa-248/1-recovery.spec.ts e2e/qa-248/2-sessions.spec.ts \
  e2e/qa-248/3-es-mobile.spec.ts e2e/qa-248/5-password-change-session.spec.ts \
  e2e/qa-248/6-argus-cookie-path.spec.ts; do
  start_backend
  (cd web && NEXT_PUBLIC_MOCK_AUTH=false bunx playwright test \
    --config=playwright.qa.config.ts "$spec" "$@")
done

# Outage phase: healthy auth provider, dead session-verification database.
# Memory checkpointer keeps startup off the dead DATABASE_URL.
cleanup
CUADRAO_CHECKPOINTER_MODE=memory \
  DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54390/postgres" \
  poetry run uvicorn argus.api.main:app --host 127.0.0.1 --port 8000 \
  >> "$EVIDENCE_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
for _ in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w "%{http_code}" \
    http://127.0.0.1:8000/api/v1/auth/session || true)"
  case "$code" in 200|401) break ;; esac
  sleep 1
done
(cd web && QA_EXPECT_VERIFICATION_OUTAGE=1 NEXT_PUBLIC_MOCK_AUTH=false \
  bunx playwright test --config=playwright.qa.config.ts \
  e2e/qa-248/4-verification-outage.spec.ts "$@")
