#!/bin/bash
# Private Alpha local smoke gate for pre-deploy candidate validation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/argus-env.sh"
argus_load_root_env >/dev/null || true

usage() {
  cat <<'USAGE'
Usage:
  .github/local-smoke.sh [--expected-sha <sha>] [--workflow-mode <safe-off|proof-shadow>] [--contract-only]

Options:
  --expected-sha    Fail if the checked-out candidate SHA differs from this value.
  --workflow-mode   Local smoke workflow mode. Defaults to proof-shadow.
  --contract-only   Print candidate/mode/flag fingerprint without starting servers.
USAGE
}

API_HOST="${ARGUS_LOCAL_SMOKE_HOST:-127.0.0.1}"
API_PORT="${ARGUS_LOCAL_SMOKE_API_PORT:-8100}"
WEB_PORT="${ARGUS_LOCAL_SMOKE_WEB_PORT:-3100}"
TIMEOUT_SECONDS="${ARGUS_LOCAL_SMOKE_TIMEOUT_SECONDS:-180}"
SLEEP_SECONDS="${ARGUS_LOCAL_SMOKE_SLEEP_SECONDS:-2}"
WORKFLOW_MODE="${ARGUS_LOCAL_SMOKE_WORKFLOW_MODE:-proof-shadow}"
EXPECTED_SHA="${ARGUS_LOCAL_SMOKE_EXPECTED_SHA:-}"
CONTRACT_ONLY=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-sha)
      EXPECTED_SHA="${2:-}"
      if [ -z "$EXPECTED_SHA" ]; then
        echo "--expected-sha requires a value."
        usage
        exit 2
      fi
      shift 2
      ;;
    --workflow-mode)
      WORKFLOW_MODE="${2:-}"
      if [ -z "$WORKFLOW_MODE" ]; then
        echo "--workflow-mode requires a value."
        usage
        exit 2
      fi
      shift 2
      ;;
    --contract-only)
      CONTRACT_ONLY=true
      shift
      ;;
    help|-h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

case "$WORKFLOW_MODE" in
  safe-off|proof-shadow)
    ;;
  real-workflow)
    echo "real-workflow mode is not allowed for local smoke; use Render warmup/canaries for real workflow execution."
    exit 2
    ;;
  *)
    echo "Unknown local smoke workflow mode: $WORKFLOW_MODE"
    usage
    exit 2
    ;;
esac

API_URL="http://${API_HOST}:${API_PORT}"
WEB_URL="http://${API_HOST}:${WEB_PORT}"
SMOKE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/argus-local-smoke.XXXXXX")"
API_LOG="${SMOKE_DIR}/api.log"
WEB_LOG="${SMOKE_DIR}/web.log"
PIDS=()

cleanup() {
  local status=$?
  local pid
  if [ "${#PIDS[@]}" -eq 0 ]; then
    rm -rf "$SMOKE_DIR"
    exit "$status"
  fi
  for pid in "${PIDS[@]}"; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  for pid in "${PIDS[@]}"; do
    wait "$pid" >/dev/null 2>&1 || true
  done
  rm -rf "$SMOKE_DIR"
  exit "$status"
}
trap cleanup EXIT INT TERM

hash_stdin() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print $1}'
    return
  fi
  shasum -a 256 | awk '{print $1}'
}

configure_local_smoke_env() {
  export APP_ENV=local-smoke
  export CUADRAO_OPS_TOKEN="${CUADRAO_OPS_TOKEN:-local-smoke-token}"
  export ARGUS_READINESS_ASSET_TIMEOUT_SECONDS="${ARGUS_READINESS_ASSET_TIMEOUT_SECONDS:-10}"
  argus_export_dev_mode
  export ARGUS_CONTEXT_PACKETS_ENABLED=false
  export ARGUS_TITLE_AUTOGEN_ENABLED=false
  export ARGUS_BACKTEST_WORKFLOW_TASK="$ARGUS_BACKTEST_WORKFLOW_TASK_DEFAULT"
  export ARGUS_BACKTEST_REAL_WORKFLOW_TASK="$ARGUS_BACKTEST_REAL_WORKFLOW_TASK_DEFAULT"

  case "$WORKFLOW_MODE" in
    safe-off)
      export ARGUS_BACKTEST_JOBS_SHADOW_ENABLED=false
      export ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED=false
      export ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=false
      ;;
    proof-shadow)
      export ARGUS_BACKTEST_JOBS_SHADOW_ENABLED=true
      export ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED=false
      export ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=false
      ;;
  esac

  export NEXT_PUBLIC_MOCK_AUTH=true
  export NEXT_PUBLIC_ENABLE_SPANISH=true
  export NEXT_PUBLIC_ARGUS_API_URL="${API_URL}/api/v1"
  export NEXT_PUBLIC_OMNISEARCH_ENABLED=true
}

json_env_report() {
  python3 - "$@" <<'PY'
import json
import os
import sys

keys = sys.argv[1:]
print(json.dumps({key: os.getenv(key, "") for key in keys}, sort_keys=True, separators=(",", ":")))
PY
}

local_env_fingerprint() {
  {
    printf "workflow_mode=%s\n" "$WORKFLOW_MODE"
    for key in \
      CUADRAO_PERSISTENCE_MODE \
      ARGUS_DEV_MEMORY_FALLBACK \
      ARGUS_MARKET_DATA_PROVIDER_MODE \
      CUADRAO_CHECKPOINTER_MODE \
      CUADRAO_MOCK_AUTH \
      ARGUS_BACKTEST_JOBS_SHADOW_ENABLED \
      ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED \
      ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED \
      ARGUS_BACKTEST_WORKFLOW_TASK \
      ARGUS_BACKTEST_REAL_WORKFLOW_TASK \
      NEXT_PUBLIC_MOCK_AUTH \
      NEXT_PUBLIC_ENABLE_SPANISH \
      NEXT_PUBLIC_ARGUS_API_URL \
      NEXT_PUBLIC_OMNISEARCH_ENABLED
    do
      printf "%s=%s\n" "$key" "${!key:-}"
    done
  } | LC_ALL=C sort | hash_stdin
}

candidate_sha() {
  git rev-parse HEAD
}

print_contract_report() {
  local sha
  sha="$(candidate_sha)"

  echo "Private Alpha local smoke"
  echo "candidate_sha=$sha"
  if [ -n "$EXPECTED_SHA" ] && [ "$EXPECTED_SHA" != "$sha" ]; then
    echo "expected_sha=$EXPECTED_SHA"
    echo "verification_status=drift"
    return 1
  fi
  echo "workflow_mode=$WORKFLOW_MODE"
  echo "runtime_mode=$(json_env_report \
    CUADRAO_PERSISTENCE_MODE \
    ARGUS_DEV_MEMORY_FALLBACK \
    ARGUS_MARKET_DATA_PROVIDER_MODE \
    CUADRAO_CHECKPOINTER_MODE \
    CUADRAO_MOCK_AUTH \
    ARGUS_BACKTEST_JOBS_SHADOW_ENABLED \
    ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED \
    ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED \
    ARGUS_BACKTEST_WORKFLOW_TASK \
    ARGUS_BACKTEST_REAL_WORKFLOW_TASK)"
  echo "feature_flags=$(json_env_report \
    NEXT_PUBLIC_ENABLE_SPANISH \
    NEXT_PUBLIC_OMNISEARCH_ENABLED)"
  echo "env_fingerprint=$(local_env_fingerprint)"
}

run_workflow_probe() {
  poetry run python - <<'PY'
import os

from workflows.trigger_proof import _task_id
from argus.api.chat import backtest_jobs

mode = os.environ["ARGUS_LOCAL_SMOKE_WORKFLOW_MODE"]
task = os.environ["ARGUS_BACKTEST_WORKFLOW_TASK"]
real_task = os.environ["ARGUS_BACKTEST_REAL_WORKFLOW_TASK"]

if _task_id(task) != task:
    raise SystemExit("workflow proof task id mismatch")
if real_task != "argus-backtests/run_backtest_job":
    raise SystemExit("real workflow task id mismatch")

shadow = backtest_jobs.backtest_jobs_shadow_enabled()
dispatch = backtest_jobs.backtest_jobs_dispatch_enabled()
execution = backtest_jobs.backtest_workflow_execution_enabled()
if mode == "safe-off" and (shadow or dispatch or execution):
    raise SystemExit("safe-off workflow flags are not off")
if mode == "proof-shadow" and not shadow:
    raise SystemExit("proof-shadow did not enable shadow job bookkeeping")
if dispatch or execution:
    raise SystemExit("local smoke must not dispatch or execute Render workflows")

print("workflow_probe=ready")
PY
}

wait_for_url() {
  local label="$1"
  local url="$2"
  shift 2
  local deadline=$((SECONDS + TIMEOUT_SECONDS))
  local attempt=1

  echo "Checking ${label}: ${url}"
  while true; do
    local pid
    for pid in "${PIDS[@]}"; do
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "ERROR: Background process ${pid} died unexpectedly."
        echo "--- api.log ---"
        tail -80 "$API_LOG" 2>/dev/null || true
        echo "--- web.log ---"
        tail -80 "$WEB_LOG" 2>/dev/null || true
        return 1
      fi
    done
    if curl -fsS --max-time 10 "$@" "$url" >/dev/null; then
      echo "${label}=ready"
      return 0
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "ERROR: ${label} did not become ready within ${TIMEOUT_SECONDS}s"
      echo "--- api.log ---"
      tail -80 "$API_LOG" 2>/dev/null || true
      echo "--- web.log ---"
      tail -80 "$WEB_LOG" 2>/dev/null || true
      return 1
    fi
    echo "  waiting for ${label}... attempt ${attempt}"
    attempt=$((attempt + 1))
    sleep "$SLEEP_SECONDS"
  done
}

check_local_readiness() {
  local readiness_json="${SMOKE_DIR}/readiness.json"
  local status

  status="$(
    curl -sS \
      -o "$readiness_json" \
      -w "%{http_code}" \
      --max-time 20 \
      -H "Authorization: Bearer ${CUADRAO_OPS_TOKEN}" \
      "${API_URL}/internal/readiness?force=true"
  )"
  if [ "$status" != "200" ] && [ "$status" != "503" ]; then
    echo "ERROR: readiness returned HTTP ${status}"
    cat "$readiness_json"
    return 1
  fi

  verify_readiness_payload "$readiness_json"
}

verify_readiness_payload() {
  local readiness_json="$1"

  python3 - "$readiness_json" <<'PY'
import json
import os
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
checks = [
    check
    for check in payload.get("checks", [])
    if isinstance(check, dict)
]
statuses = {
    str(check.get("name")): str(check.get("status"))
    for check in checks
}
allowed_degraded_readiness = set()
if os.environ.get("CUADRAO_PERSISTENCE_MODE") == "memory":
    allowed_degraded_readiness.add("supabase")
unexpected_degraded = []
allowed_degraded_seen = False
for check in checks:
    name = str(check.get("name"))
    status = str(check.get("status"))
    if status in {"ready", "warm"}:
        continue
    if (
        name in allowed_degraded_readiness
        and status == "degraded"
        and check.get("reason") == "gateway_unavailable"
    ):
        allowed_degraded_seen = True
        continue
    unexpected_degraded.append({"name": name, "status": status, "reason": check.get("reason")})
if unexpected_degraded:
    raise SystemExit(f"unexpected degraded readiness checks: {unexpected_degraded!r}")
top_status = str(payload.get("status") or "unknown")
if top_status != "ready" and not allowed_degraded_seen:
    raise SystemExit(f"readiness failed: status={top_status!r} checks={statuses!r}")
if statuses.get("agent_runtime_workflow") != "ready":
    raise SystemExit(f"agent runtime readiness failed: {statuses!r}")
asset_status = statuses.get("asset_universe")
if asset_status not in {"ready", "warm"}:
    raise SystemExit(f"asset readiness failed: {statuses!r}")
print(f"readiness_status={payload.get('status', 'unknown')}")
PY
}

start_api() {
  echo "Starting local API on ${API_URL}"
  poetry run uvicorn argus.api.main:app --host "$API_HOST" --port "$API_PORT" >"$API_LOG" 2>&1 &
  PIDS+=("$!")
}

start_web() {
  echo "Starting local web on ${WEB_URL}"
  (
    cd web && bun run dev --hostname "$API_HOST" --port "$WEB_PORT"
  ) >"$WEB_LOG" 2>&1 &
  PIDS+=("$!")
}

configure_local_smoke_env
export ARGUS_LOCAL_SMOKE_WORKFLOW_MODE="$WORKFLOW_MODE"
if [ "${ARGUS_LOCAL_SMOKE_SOURCE_ONLY:-false}" = "true" ]; then
  return 0 2>/dev/null || exit 0
fi
print_contract_report

if [ "$CONTRACT_ONLY" = true ]; then
  echo "verification_status=ready"
  exit 0
fi

run_workflow_probe
start_api
start_web
wait_for_url "api_health" "${API_URL}/health"
check_local_readiness
wait_for_url "web" "$WEB_URL"

echo "verification_status=ready"
