#!/bin/bash
# Warm Render free services before a private-alpha tester session.

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
  .github/warmup-render.sh [--expect-mode <safe-off|proof-shadow|real-workflow>]

Options:
  --expect-mode  Verify release config/env fingerprint without mutating Render config.
USAGE
}

EXPECTED_MODE="${ARGUS_WARMUP_EXPECT_MODE:-}"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --expect-mode)
      EXPECTED_MODE="${2:-}"
      if [ -z "$EXPECTED_MODE" ]; then
        echo "--expect-mode requires a value."
        usage
        exit 2
      fi
      shift 2
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

APP_URL="${ARGUS_WARMUP_APP_URL:-$ARGUS_PRIVATE_LAUNCH_APP_URL}"
API_URL="${ARGUS_WARMUP_API_URL:-$ARGUS_PRIVATE_LAUNCH_API_URL}"
OPS_TOKEN="${CUADRAO_OPS_TOKEN:-}"
TIMEOUT_SECONDS="${ARGUS_WARMUP_TIMEOUT_SECONDS:-180}"
SLEEP_SECONDS="${ARGUS_WARMUP_SLEEP_SECONDS:-5}"

deadline=$((SECONDS + TIMEOUT_SECONDS))

wait_for_url() {
  local label="$1"
  local url="$2"
  shift 2
  local attempt=1

  echo "Warming $label: $url"
  while true; do
    if curl -fsS --max-time 15 "$@" "$url" > /dev/null; then
      echo "OK: $label responded"
      return 0
    fi

    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "ERROR: $label did not respond within ${TIMEOUT_SECONDS}s"
      return 1
    fi

    echo "  waiting for $label... attempt $attempt"
    attempt=$((attempt + 1))
    sleep "$SLEEP_SECONDS"
  done
}

wait_for_readiness() {
  if [ -z "$OPS_TOKEN" ]; then
    echo "CUADRAO_OPS_TOKEN is required for product readiness warmup."
    return 1
  fi

  wait_for_url \
    "product readiness" \
    "${API_URL}/internal/readiness?force=true" \
    -H "Authorization: Bearer ${OPS_TOKEN}"
}

require_status_line() {
  local status="$1"
  local expected="$2"

  if ! grep -Fxq "$expected" <<< "$status"; then
    echo "ERROR: expected API mode line: $expected"
    return 1
  fi
}

assert_api_mode() {
  local mode="$1"
  local status

  if [ -z "$mode" ]; then
    return 0
  fi

  case "$mode" in
    safe-off|proof-shadow|real-workflow)
      ;;
    *)
      echo "Unknown expected API mode: $mode"
      usage
      return 2
      ;;
  esac

  echo "Checking release config for API mode: $mode"
  if ! status="$("$SCRIPT_DIR/render-env-sync.sh" release-config-audit --expect-mode "$mode")"; then
    printf "%s\n" "$status"
    return 1
  fi
  printf "%s\n" "$status"

  require_status_line "$status" "status=ready"
  require_status_line "$status" "release_profile_status=ready"
  if ! grep -Eq '^release_profile_hash=[0-9a-f]{64}$' <<< "$status"; then
    echo "ERROR: release config audit did not emit release_profile_hash."
    return 1
  fi
  if ! grep -Eq '^env_fingerprint=[0-9a-f]{64}$' <<< "$status"; then
    echo "ERROR: release config audit did not emit env_fingerprint."
    return 1
  fi
  if [ "$mode" = "real-workflow" ]; then
    if ! grep -Eq '^workflow_env_fingerprint=[0-9a-f]{64}$' <<< "$status"; then
      echo "ERROR: release config audit did not emit workflow_env_fingerprint."
      return 1
    fi
    require_status_line "$status" "workflow_env_status=ready"
  elif grep -q '^workflow_env_status=drift$' <<< "$status"; then
    echo "ERROR: release config audit reported workflow_env_status=drift for $mode."
    return 1
  fi

  echo "OK: release config matched $mode"
  run_workflow_runtime_proof "$mode"
}

workflow_proof_job_id() {
  WORKFLOW_PROOF_SEED="$1" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["WORKFLOW_PROOF_SEED"])
job_id = str(payload.get("job_id") or "").strip()
if not job_id:
    raise SystemExit("workflow proof seed did not return job_id")
print(job_id)
PY
}

run_workflow_runtime_proof() {
  local mode="$1"
  if [ "$mode" != "real-workflow" ]; then
    return 0
  fi

  local nonce
  local seed_output
  local job_id
  nonce="warmup-$(date +%s)-${RANDOM:-0}"

  echo "Checking Render workflow runtime proof"
  if ! seed_output="$(.github/workflow-proof.sh seed --nonce "$nonce")"; then
    echo "ERROR: failed to seed Render workflow proof job."
    return 1
  fi
  if ! job_id="$(workflow_proof_job_id "$seed_output")"; then
    echo "ERROR: failed to parse Render workflow proof job."
    return 1
  fi
  if ! .github/workflow-proof.sh remote --job-id "$job_id" --nonce "$nonce" >/dev/null; then
    echo "ERROR: Render workflow proof task failed."
    return 1
  fi
  if ! .github/workflow-proof.sh verify --job-id "$job_id" --expect-nonce "$nonce" --expect-provider-mode live_provider >/dev/null; then
    echo "ERROR: Render workflow runtime did not confirm live_provider."
    return 1
  fi

  echo "workflow_runtime_provider_mode=live_provider"
  echo "workflow_runtime_proof=ready"
}

echo "Argus private-launch warmup"
echo "Timeout: ${TIMEOUT_SECONDS}s"
echo ""

wait_for_url "API health" "${API_URL}/health"
wait_for_readiness
wait_for_url "frontend" "$APP_URL"
assert_api_mode "$EXPECTED_MODE"

echo ""
echo "Argus product path is ready for testers."
