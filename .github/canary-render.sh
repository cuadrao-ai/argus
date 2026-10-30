#!/bin/bash
# The private-alpha canary: fixed checks that never follow features.
# Every failure names the check, release guard, or harness step that failed.

set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/argus-env.sh"
argus_load_root_env >/dev/null || true

APP_URL="${ARGUS_CANARY_APP_URL:-$ARGUS_PRIVATE_LAUNCH_APP_URL}"
API_URL="${ARGUS_CANARY_API_URL:-$ARGUS_PRIVATE_LAUNCH_API_URL}"
EMAIL="${ARGUS_CANARY_EMAIL:-${MOCK_USER_EMAIL:-}}"
# Kept only as a defense-in-depth redaction value for older operator env files.
PASSWORD="${ARGUS_CANARY_PASSWORD:-${MOCK_USER_PASSWORD:-}}"
SIGNUP_RUN_ID="${GITHUB_RUN_ID:-}"
SIGNUP_RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-}"
SIGNUP_LOCAL_NONCE="${ARGUS_CANARY_LOCAL_RUN_NONCE:-}"
SIGNUP_EMAIL=""
SUPABASE_URL="${ARGUS_CANARY_SUPABASE_URL:-${SUPABASE_URL:-${SUPABASE_PROJECT_URL:-}}}"
SUPABASE_SERVICE_ROLE_KEY="${ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY:-${SUPABASE_SERVICE_ROLE_KEY:-}}"
OPS_TOKEN="${CUADRAO_OPS_TOKEN:-}"
LANGUAGE="${ARGUS_CANARY_LANGUAGE:-es-419}"
EXPECT_MODE="${ARGUS_CANARY_EXPECT_MODE:-${ARGUS_WARMUP_EXPECT_MODE:-real-workflow}}"
EVIDENCE_PATH="${ARGUS_CANARY_EVIDENCE_PATH:-}"
CAPTURE_PATH="${ARGUS_CANARY_CAPTURE_PATH:-}"
CANDIDATE_SHA="${ARGUS_CANARY_SHA:-${GITHUB_SHA:-}}"
CHECKED_OUT_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
HARNESS_SHA="${ARGUS_CANARY_HARNESS_SHA:-$CHECKED_OUT_SHA}"
ALLOW_HARNESS_MISMATCH="${ARGUS_CANARY_ALLOW_HARNESS_MISMATCH:-false}"
SURFACE="${ARGUS_CANARY_SURFACE:-}"
CANARY_RUN_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ARTIFACT_PROBE="${ARGUS_CANARY_BROWSER_ARTIFACT_PROBE:-none}"
REDACTION_PROBE_VALUE="${ARGUS_CANARY_BROWSER_REDACTION_PROBE_VALUE:-}"
SIMULATE_REDACTION_FAILURE="${ARGUS_CANARY_REDACT_SIMULATE_FAILURE:-false}"
RELEASE_PROFILE_TOOL="$SCRIPT_DIR/private-alpha-release-profile.py"
# The release profile owns the check names; this script proves the commit check
# and mints the session the sign-in check depends on.
REQUIRED_CHECKS="$(python3 "$RELEASE_PROFILE_TOOL" canary-checks 2>/dev/null || true)"
SAME_COMMIT_CHECK="services_same_commit"
SIGN_IN_CHECK="signed_in_chat_answer"

if [ -z "$CHECKED_OUT_SHA" ]; then
  CHECKED_OUT_SHA="unknown"
fi
if [ -z "$CANDIDATE_SHA" ]; then
  CANDIDATE_SHA="$CHECKED_OUT_SHA"
fi

BROWSER_CHECKS_HANDOFF="$(mktemp)"
BROWSER_CHECK_EVIDENCE="$(mktemp)"
BROWSER_RAW_IDS="$(mktemp)"
BROWSER_STORAGE_STATE="$(mktemp)"
BROWSER_SESSION_HANDOFF="$(mktemp)"
BROWSER_AUTH_CURL_CONFIG="$(mktemp)"
SERVICE_ROLE_CURL_CONFIG="$(mktemp)"
OPS_CURL_CONFIG="$(mktemp)"
SIGNUP_AUTH_USERS_RESPONSE="$(mktemp)"
SIGNUP_AUTH_USER_IDS="$(mktemp)"
SIGNUP_ALLOWLIST_RESPONSE="$(mktemp)"
SIGNUP_APPROVAL_REQUEST="$(mktemp)"
API_JOB_RESPONSE="$(mktemp)"
API_MESSAGES_RESPONSE="$(mktemp)"
chmod 600 "$BROWSER_CHECKS_HANDOFF" "$BROWSER_CHECK_EVIDENCE" "$BROWSER_RAW_IDS"
chmod 600 "$BROWSER_STORAGE_STATE" "$BROWSER_SESSION_HANDOFF"
chmod 600 "$BROWSER_AUTH_CURL_CONFIG" "$SERVICE_ROLE_CURL_CONFIG"
chmod 600 "$OPS_CURL_CONFIG"
chmod 600 "$SIGNUP_AUTH_USERS_RESPONSE" "$SIGNUP_AUTH_USER_IDS"
chmod 600 "$SIGNUP_ALLOWLIST_RESPONSE"
chmod 600 "$SIGNUP_APPROVAL_REQUEST"
printf 'header = "apikey: %s"\n' "$SUPABASE_SERVICE_ROLE_KEY" \
  > "$SERVICE_ROLE_CURL_CONFIG"
printf 'header = "Authorization: Bearer %s"\n' "$SUPABASE_SERVICE_ROLE_KEY" \
  >> "$SERVICE_ROLE_CURL_CONFIG"
printf 'header = "Authorization: Bearer %s"\n' "$OPS_TOKEN" \
  > "$OPS_CURL_CONFIG"

SIGNUP_IDENTITY_SETUP_ATTEMPTED="false"
BROWSER_SESSION_MINTED="false"

cleanup() {
  local exit_status=$?
  local signup_cleanup_failed=0
  local session_revocation_failed=0
  trap - EXIT
  if [ "${SIGNUP_IDENTITY_SETUP_ATTEMPTED:-false}" = "true" ]; then
    cleanup_signup_identity || signup_cleanup_failed=1
  fi
  if [ "${BROWSER_SESSION_MINTED:-false}" = "true" ]; then
    revoke_browser_session_once || session_revocation_failed=1
  fi
  redact_browser_artifacts || true
  rm -f "$BROWSER_CHECKS_HANDOFF" "$BROWSER_CHECK_EVIDENCE" "$BROWSER_RAW_IDS"
  rm -f "$BROWSER_STORAGE_STATE" "$BROWSER_SESSION_HANDOFF"
  rm -f "$BROWSER_AUTH_CURL_CONFIG"
  rm -f "$OPS_CURL_CONFIG"
  rm -f "$SIGNUP_APPROVAL_REQUEST"
  rm -f \
    "$SERVICE_ROLE_CURL_CONFIG" \
    "$SIGNUP_AUTH_USERS_RESPONSE" \
    "$SIGNUP_AUTH_USER_IDS" \
    "$SIGNUP_ALLOWLIST_RESPONSE" \
    "$API_JOB_RESPONSE" \
    "$API_MESSAGES_RESPONSE"
  if [ "$signup_cleanup_failed" -ne 0 ]; then
    echo "ERROR: dedicated signup identity cleanup failed." >&2
    if [ "$exit_status" -eq 0 ]; then
      exit_status=1
    fi
  fi
  if [ "$session_revocation_failed" -ne 0 ]; then
    echo "ERROR: dedicated canary session revocation failed." >&2
    if [ "$exit_status" -eq 0 ]; then
      exit_status=1
    fi
  fi
  exit "$exit_status"
}
trap cleanup EXIT

WARMUP_OUTPUT=""
API_DEPLOY_STATUS_OUTPUT=""
WEB_DEPLOY_STATUS_OUTPUT=""
WORKFLOW_VERSION_STATUS_OUTPUT=""
ENV_FINGERPRINT=""
RELEASE_PROFILE_HASH=""
WORKFLOW_ENV_FINGERPRINT=""
WORKFLOW_ENV_STATUS=""
WORKFLOW_RUNTIME_PROVIDER_MODE=""
WORKFLOW_RUNTIME_PROOF=""
WORKFLOW_TASK=""
REAL_WORKFLOW_TASK=""
API_DEPLOY_SHA=""
WEB_DEPLOY_SHA=""
API_DEPLOY_STATUS=""
WEB_DEPLOY_STATUS=""
WORKFLOW_VERSION_COMMIT=""
WORKFLOW_VERSION_ID=""
WORKFLOW_VERSION_STATUS=""
USER_ID=""
BROWSER_ACCESS_TOKEN=""
BROWSER_STATUS="not_run"
BROWSER_FAILED_CHECK=""
BROWSER_FAILURE_REASON=""
FAILED_CONVERSATION_ID=""
FAILED_BACKTEST_JOB_ID=""
SHELL_CHECK_RESULTS=""
CANARY_STATUS="running"
CANARY_FAILED=""
CANARY_FAILURE_REASON=""
CANARY_CAPTURE_WRITE_STATUS="not_attempted"
CANARY_CAPTURE_WRITE_FAILURE_REASON=""

print_sanitized_warmup_output() {
  CANARY_WARMUP_OUTPUT="$WARMUP_OUTPUT" python3 - <<'PY'
import json
import os

for line in os.environ["CANARY_WARMUP_OUTPUT"].splitlines():
    stripped = line.strip()
    if not stripped:
        print(line)
        continue
    if stripped.startswith("{") and (
        '"unresolved_jobs"' in stripped
        or '"user_id"' in stripped
        or '"task_run_id"' in stripped
    ):
        try:
            report = json.loads(stripped)
        except json.JSONDecodeError:
            print("stale_job_scan_output=<redacted>")
            continue
        print(
            "stale_job_scan_status="
            f"{report.get('status', '<unknown>')} "
            f"scanned={report.get('scanned_count', '<unknown>')} "
            f"stale={report.get('stale_count', '<unknown>')} "
            f"reconciled={report.get('reconciled_count', '<unknown>')} "
            f"unresolved={report.get('unresolved_count', '<unknown>')} "
            f"errors={report.get('error_count', '<unknown>')}"
        )
        continue
    if stripped.startswith("unresolved stale job:"):
        print("unresolved stale job: <redacted>")
        continue
    if any(token in stripped for token in ("user_id", "task_run_id", "unresolved_jobs")):
        print("stale_job_scan_output=<redacted>")
        continue
    print(line)
PY
}

extract_warmup_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2); found=1; exit } END { if (!found) exit 1 }' <<< "$WARMUP_OUTPUT"
}

extract_status_value() {
  local status="$1"
  local key="$2"
  awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2); found=1; exit } END { if (!found) exit 1 }' <<< "$status"
}

workflow_commit_matches_candidate() {
  local workflow_commit="$1"
  local candidate_commit="$2"

  [[ "$candidate_commit" =~ ^[0-9a-f]{40}$ ]] || return 1
  [[ "$workflow_commit" =~ ^[0-9a-f]{7,40}$ ]] || return 1
  [[ "$candidate_commit" == "$workflow_commit"* ]]
}

record_check() {
  SHELL_CHECK_RESULTS="${SHELL_CHECK_RESULTS}${1}=${2}"$'\n'
  echo "canary_check=${1} status=${2}"
}

build_release_evidence_json() {
  CANARY_STATUS="$CANARY_STATUS" \
  CANARY_SURFACE="$SURFACE" \
  CANARY_FAILED="$CANARY_FAILED" \
  CANARY_FAILURE_REASON="$CANARY_FAILURE_REASON" \
  CANARY_REQUIRED_CHECKS="$REQUIRED_CHECKS" \
  CANARY_SHELL_CHECK_RESULTS="$SHELL_CHECK_RESULTS" \
  CANARY_BROWSER_CHECK_EVIDENCE="$BROWSER_CHECK_EVIDENCE" \
  CANARY_BROWSER_STATUS="$BROWSER_STATUS" \
  CANARY_CAPTURE_WRITE_STATUS="$CANARY_CAPTURE_WRITE_STATUS" \
  CANARY_CAPTURE_WRITE_FAILURE_REASON="$CANARY_CAPTURE_WRITE_FAILURE_REASON" \
  CANARY_EXPECTED_MODE="$EXPECT_MODE" \
  CANARY_RELEASE_PROFILE_HASH="$RELEASE_PROFILE_HASH" \
  CANARY_ENV_FINGERPRINT="$ENV_FINGERPRINT" \
  CANARY_WORKFLOW_ENV_FINGERPRINT="$WORKFLOW_ENV_FINGERPRINT" \
  CANARY_WORKFLOW_ENV_STATUS="$WORKFLOW_ENV_STATUS" \
  CANARY_WORKFLOW_RUNTIME_PROVIDER_MODE="$WORKFLOW_RUNTIME_PROVIDER_MODE" \
  CANARY_WORKFLOW_RUNTIME_PROOF="$WORKFLOW_RUNTIME_PROOF" \
  CANARY_WORKFLOW_TASK="$WORKFLOW_TASK" \
  CANARY_REAL_WORKFLOW_TASK="$REAL_WORKFLOW_TASK" \
  CANARY_API_DEPLOY_SHA="$API_DEPLOY_SHA" \
  CANARY_WEB_DEPLOY_SHA="$WEB_DEPLOY_SHA" \
  CANARY_API_DEPLOY_STATUS="$API_DEPLOY_STATUS" \
  CANARY_WEB_DEPLOY_STATUS="$WEB_DEPLOY_STATUS" \
  CANARY_WORKFLOW_VERSION_COMMIT="$WORKFLOW_VERSION_COMMIT" \
  CANARY_WORKFLOW_VERSION_ID="$WORKFLOW_VERSION_ID" \
  CANARY_WORKFLOW_VERSION_STATUS="$WORKFLOW_VERSION_STATUS" \
  CANARY_EXPECTED_SHA="$CANDIDATE_SHA" \
  CANARY_CHECKED_OUT_SHA="$CHECKED_OUT_SHA" \
  CANARY_HARNESS_SHA="$HARNESS_SHA" \
  CANARY_LANGUAGE="$LANGUAGE" \
  python3 - <<'PY'
import json
import os
import pathlib

def optional(value: str):
    return value or None

required = [name for name in os.environ["CANARY_REQUIRED_CHECKS"].splitlines() if name]
checks: dict[str, dict[str, object]] = {}
browser_evidence = pathlib.Path(os.environ["CANARY_BROWSER_CHECK_EVIDENCE"])
if browser_evidence.is_file() and browser_evidence.stat().st_size:
    checks.update(json.loads(browser_evidence.read_text(encoding="utf-8")))
for line in os.environ["CANARY_SHELL_CHECK_RESULTS"].splitlines():
    name, _, status = line.partition("=")
    if name:
        checks.setdefault(name, {})["status"] = status
if required and set(checks) - set(required):
    raise SystemExit("canary evidence named a check the release profile does not require")

payload = {
    "status": os.environ["CANARY_STATUS"],
    "surface": os.environ["CANARY_SURFACE"],
    "failed": optional(os.environ["CANARY_FAILED"]),
    "failure_reason": optional(os.environ["CANARY_FAILURE_REASON"]),
    "checks": checks,
    "browser_status": os.environ["CANARY_BROWSER_STATUS"],
    "capture_write_status": os.environ["CANARY_CAPTURE_WRITE_STATUS"],
    "capture_write_failure_reason": optional(
        os.environ["CANARY_CAPTURE_WRITE_FAILURE_REASON"]
    ),
    "expected_mode": os.environ["CANARY_EXPECTED_MODE"],
    "release_profile_hash": optional(os.environ["CANARY_RELEASE_PROFILE_HASH"]),
    "env_fingerprint": optional(os.environ["CANARY_ENV_FINGERPRINT"]),
    "workflow_env_fingerprint": optional(os.environ["CANARY_WORKFLOW_ENV_FINGERPRINT"]),
    "workflow_env_status": optional(os.environ["CANARY_WORKFLOW_ENV_STATUS"]),
    "workflow_runtime_provider_mode": optional(os.environ["CANARY_WORKFLOW_RUNTIME_PROVIDER_MODE"]),
    "workflow_runtime_proof": optional(os.environ["CANARY_WORKFLOW_RUNTIME_PROOF"]),
    "workflow_task": optional(os.environ["CANARY_WORKFLOW_TASK"]),
    "real_workflow_task": optional(os.environ["CANARY_REAL_WORKFLOW_TASK"]),
    "api_deploy_sha": optional(os.environ["CANARY_API_DEPLOY_SHA"]),
    "web_deploy_sha": optional(os.environ["CANARY_WEB_DEPLOY_SHA"]),
    "api_deploy_status": optional(os.environ["CANARY_API_DEPLOY_STATUS"]),
    "web_deploy_status": optional(os.environ["CANARY_WEB_DEPLOY_STATUS"]),
    "workflow_version_commit": optional(os.environ["CANARY_WORKFLOW_VERSION_COMMIT"]),
    "workflow_version_id": optional(os.environ["CANARY_WORKFLOW_VERSION_ID"]),
    "workflow_version_status": optional(os.environ["CANARY_WORKFLOW_VERSION_STATUS"]),
    "candidate_sha": os.environ["CANARY_EXPECTED_SHA"],
    "checked_out_sha": os.environ["CANARY_CHECKED_OUT_SHA"],
    "harness_sha": os.environ["CANARY_HARNESS_SHA"],
    "language": os.environ["CANARY_LANGUAGE"],
    "privacy": "no_raw_ids; labels are sha256 prefixes",
}
print(json.dumps(payload, sort_keys=True))
PY
}

write_json_artifact() {
  local destination="$1"
  local artifact_kind="$2"
  if [ -z "$destination" ]; then
    return 0
  fi
  mkdir -p "$(dirname "$destination")"
  local evidence_json
  evidence_json="$(build_release_evidence_json)"
  CANARY_DESTINATION="$destination" \
  CANARY_ARTIFACT_KIND="$artifact_kind" \
  CANARY_EVIDENCE_JSON="$evidence_json" \
  CANARY_USER_ID="$USER_ID" \
  CANARY_RAW_IDS_FILE="$BROWSER_RAW_IDS" \
  python3 - <<'PY'
import json
import os
import pathlib

from scripts.ops.canary_capture_sanitizer import UUID_PATTERN

payload = json.loads(os.environ["CANARY_EVIDENCE_JSON"])
payload["artifact_kind"] = os.environ["CANARY_ARTIFACT_KIND"]
encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
raw_ids = {os.environ["CANARY_USER_ID"]}
raw_ids_file = pathlib.Path(os.environ["CANARY_RAW_IDS_FILE"])
if raw_ids_file.is_file():
    raw_ids.update(raw_ids_file.read_text(encoding="utf-8").splitlines())
if UUID_PATTERN.search(encoded) or any(
    raw_id and raw_id in encoded for raw_id in raw_ids
):
    raise SystemExit("privacy-safe canary artifact contained a raw private identifier")
path = pathlib.Path(os.environ["CANARY_DESTINATION"])
path.write_text(encoded, encoding="utf-8")
path.chmod(0o600)
print(f"canary_{os.environ['CANARY_ARTIFACT_KIND']}_path={path}")
PY
}

write_canary_evidence() {
  write_json_artifact "$EVIDENCE_PATH" "evidence"
}

write_canary_capture() {
  if [ -z "$CAPTURE_PATH" ]; then
    return 1
  fi

  mkdir -p "$(dirname "$CAPTURE_PATH")"
  local exit_code=0
  local release_evidence_json
  release_evidence_json="$(build_release_evidence_json)"
  CANARY_CAPTURE_PATH="$CAPTURE_PATH" \
  CANARY_STATUS="$CANARY_STATUS" \
  CANARY_FAILED="$CANARY_FAILED" \
  CANARY_FAILURE_REASON="$CANARY_FAILURE_REASON" \
  CANARY_RELEASE_EVIDENCE_JSON="$release_evidence_json" \
  CANARY_MESSAGES_FILE="$API_MESSAGES_RESPONSE" \
  CANARY_JOB_RESPONSE_FILE="$API_JOB_RESPONSE" \
  python3 - <<'PY' || exit_code=$?
import json
import os
import pathlib
from typing import Any

from scripts.ops.canary_capture_sanitizer import (
    assert_sanitized_capture,
    sanitize_capture_value as sanitize,
)


def read_json_file(path: str) -> Any:
    if not path:
        return None
    file_path = pathlib.Path(path)
    if not file_path.exists() or file_path.stat().st_size == 0:
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def first_dict(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict):
            return value
    return None


def extract_message_artifacts(messages_payload: Any) -> dict[str, Any]:
    artifacts: dict[str, Any] = {
        "message_artifacts": [],
        "result_card": None,
        "explanation_context": None,
        "final_response_payload": None,
        "confirmation_payload": None,
    }
    if not isinstance(messages_payload, dict):
        return artifacts
    items = messages_payload.get("items")
    if not isinstance(items, list):
        return artifacts
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        final_response_payload = metadata.get("final_response_payload")
        artifacts["message_artifacts"].append(
            {
                "role": item.get("role"),
                "metadata_keys": sorted(str(key) for key in metadata.keys()),
                "has_result_card": isinstance(metadata.get("result_card"), dict)
                or isinstance(metadata.get("conversation_result_card"), dict),
                "has_backtest_job": isinstance(metadata.get("backtest_job"), dict),
            }
        )
        if artifacts["result_card"] is None:
            artifacts["result_card"] = first_dict(
                metadata.get("result_card"),
                metadata.get("conversation_result_card"),
                (final_response_payload or {}).get("result_card")
                if isinstance(final_response_payload, dict)
                else None,
            )
        if artifacts["explanation_context"] is None:
            artifacts["explanation_context"] = first_dict(
                metadata.get("explanation_context"),
                (final_response_payload or {}).get("explanation_context")
                if isinstance(final_response_payload, dict)
                else None,
            )
        if artifacts["final_response_payload"] is None and isinstance(
            final_response_payload, dict
        ):
            artifacts["final_response_payload"] = final_response_payload
        if artifacts["confirmation_payload"] is None:
            artifacts["confirmation_payload"] = first_dict(
                metadata.get("confirmation_payload"),
                metadata.get("confirmation"),
            )
    return artifacts


messages_payload = read_json_file(os.environ["CANARY_MESSAGES_FILE"])
message_artifacts = extract_message_artifacts(messages_payload)
job_response = read_json_file(os.environ["CANARY_JOB_RESPONSE_FILE"])
release = json.loads(os.environ["CANARY_RELEASE_EVIDENCE_JSON"])
final_response_payload = message_artifacts.get("final_response_payload")
job_run = job_response.get("run") if isinstance(job_response, dict) else None
result = first_dict(
    final_response_payload.get("result")
    if isinstance(final_response_payload, dict)
    else None,
    job_run,
)
payload = {
    "schema_version": 1,
    "artifact_kind": "capture",
    "status": os.environ["CANARY_STATUS"],
    "failure": {
        "failed": os.environ["CANARY_FAILED"] or None,
        "reason": os.environ["CANARY_FAILURE_REASON"] or None,
        "status": os.environ["CANARY_STATUS"],
    },
    "release": release,
    "launch_payload": {
        "language": release["language"],
        "confirmation_payload": message_artifacts.get("confirmation_payload"),
    },
    "result": result,
    "result_card": message_artifacts.get("result_card"),
    "explanation_context": message_artifacts.get("explanation_context"),
    "final_response_payload": message_artifacts.get("final_response_payload"),
    "message_artifacts": message_artifacts.get("message_artifacts", []),
    "job_response": job_response,
    "privacy": "no_raw_ids; labels are sha256 prefixes; secrets redacted",
}

path = pathlib.Path(os.environ["CANARY_CAPTURE_PATH"])
sanitized_payload = sanitize(payload)
assert_sanitized_capture(sanitized_payload)
path.write_text(
    json.dumps(sanitized_payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
path.chmod(0o600)
print(f"canary_capture_path={path}")
PY
  return "$exit_code"
}

prepare_capture_destination() {
  if [ -z "$CAPTURE_PATH" ]; then
    fail_canary "canary_harness" "missing_capture_destination"
  fi
  if ! mkdir -p "$(dirname "$CAPTURE_PATH")" \
    || ! (umask 077; : > "$CAPTURE_PATH") \
    || ! chmod 600 "$CAPTURE_PATH"; then
    fail_canary "canary_harness" "capture_destination_not_writable"
  fi
  rm -f "$CAPTURE_PATH"
  CANARY_CAPTURE_WRITE_STATUS="ready"
}

fail_canary() {
  CANARY_STATUS="failed"
  CANARY_FAILED="$1"
  CANARY_FAILURE_REASON="$2"
  if grep -Fxq -- "$CANARY_FAILED" <<< "$REQUIRED_CHECKS"; then
    record_check "$CANARY_FAILED" "failed"
  fi
  echo "ERROR: canary failed at ${CANARY_FAILED}: ${CANARY_FAILURE_REASON}"
  if write_canary_capture; then
    CANARY_CAPTURE_WRITE_STATUS="written"
    CANARY_CAPTURE_WRITE_FAILURE_REASON=""
  else
    CANARY_CAPTURE_WRITE_STATUS="failed"
    CANARY_CAPTURE_WRITE_FAILURE_REASON="capture_write_failed"
  fi
  echo "canary_capture_write_status=$CANARY_CAPTURE_WRITE_STATUS"
  if [ -n "$CANARY_CAPTURE_WRITE_FAILURE_REASON" ]; then
    echo "canary_capture_write_failure_reason=$CANARY_CAPTURE_WRITE_FAILURE_REASON"
  fi
  write_canary_evidence || true
  exit 1
}

run_same_commit_check() {
  if ! API_DEPLOY_STATUS_OUTPUT="$("$SCRIPT_DIR/render-env-sync.sh" api-deploy-status)"; then
    fail_canary "$SAME_COMMIT_CHECK" "api_deploy_status_failed"
  fi
  if ! WEB_DEPLOY_STATUS_OUTPUT="$("$SCRIPT_DIR/render-env-sync.sh" web-deploy-status)"; then
    fail_canary "$SAME_COMMIT_CHECK" "web_deploy_status_failed"
  fi
  if ! WORKFLOW_VERSION_STATUS_OUTPUT="$("$SCRIPT_DIR/render-env-sync.sh" workflow-version-status)"; then
    fail_canary "$SAME_COMMIT_CHECK" "workflow_version_status_failed"
  fi
  API_DEPLOY_SHA="$(extract_status_value "$API_DEPLOY_STATUS_OUTPUT" commit || true)"
  WEB_DEPLOY_SHA="$(extract_status_value "$WEB_DEPLOY_STATUS_OUTPUT" commit || true)"
  API_DEPLOY_STATUS="$(extract_status_value "$API_DEPLOY_STATUS_OUTPUT" status || true)"
  WEB_DEPLOY_STATUS="$(extract_status_value "$WEB_DEPLOY_STATUS_OUTPUT" status || true)"
  WORKFLOW_VERSION_ID="$(extract_status_value "$WORKFLOW_VERSION_STATUS_OUTPUT" workflow_version_id || true)"
  WORKFLOW_VERSION_STATUS="$(extract_status_value "$WORKFLOW_VERSION_STATUS_OUTPUT" status || true)"
  WORKFLOW_VERSION_COMMIT="$(extract_status_value "$WORKFLOW_VERSION_STATUS_OUTPUT" commit || true)"

  if [ "$API_DEPLOY_STATUS" != "live" ]; then
    fail_canary "$SAME_COMMIT_CHECK" "api_deploy_not_live"
  fi
  if [ "$WEB_DEPLOY_STATUS" != "live" ]; then
    fail_canary "$SAME_COMMIT_CHECK" "web_deploy_not_live"
  fi
  if [ "$API_DEPLOY_SHA" != "$CANDIDATE_SHA" ]; then
    fail_canary "$SAME_COMMIT_CHECK" "api_deploy_sha_mismatch"
  fi
  if [ -z "$WEB_DEPLOY_SHA" ]; then
    fail_canary "$SAME_COMMIT_CHECK" "web_deploy_sha_missing"
  fi
  if [ "$WORKFLOW_VERSION_STATUS" != "ready" ]; then
    fail_canary "$SAME_COMMIT_CHECK" "workflow_version_not_ready"
  fi
  if ! workflow_commit_matches_candidate "$WORKFLOW_VERSION_COMMIT" "$CANDIDATE_SHA"; then
    fail_canary "$SAME_COMMIT_CHECK" "workflow_version_commit_mismatch"
  fi
  if [ -z "$WORKFLOW_VERSION_ID" ]; then
    fail_canary "$SAME_COMMIT_CHECK" "workflow_version_id_missing"
  fi
  echo "canary_api_deploy_status=$API_DEPLOY_STATUS"
  echo "canary_web_deploy_status=$WEB_DEPLOY_STATUS"
  echo "canary_api_deploy_sha=$API_DEPLOY_SHA"
  echo "canary_web_deploy_sha=$WEB_DEPLOY_SHA"
  echo "canary_workflow_version_status=$WORKFLOW_VERSION_STATUS"
  echo "canary_workflow_version_commit=$WORKFLOW_VERSION_COMMIT"
  echo "canary_workflow_version_id=$WORKFLOW_VERSION_ID"
  record_check "$SAME_COMMIT_CHECK" "passed"
}

validate_canary_harness_contract() {
  if ! python3 "$RELEASE_PROFILE_TOOL" validate >/dev/null; then
    fail_canary "release_config" "release_profile_invalid"
  fi
  RELEASE_PROFILE_HASH="$(python3 "$RELEASE_PROFILE_TOOL" hash)"
  local check
  for check in "$SAME_COMMIT_CHECK" "$SIGN_IN_CHECK"; do
    if ! grep -Fxq -- "$check" <<< "$REQUIRED_CHECKS"; then
      fail_canary "canary_harness" "check_not_in_release_profile"
    fi
  done
  local profile_language
  profile_language="$(python3 "$RELEASE_PROFILE_TOOL" canary-value language)"
  if [ "$LANGUAGE" != "$profile_language" ]; then
    fail_canary "canary_harness" "canary_language_mismatch"
  fi
  if [ "$HARNESS_SHA" != "$CHECKED_OUT_SHA" ]; then
    fail_canary "canary_harness" "canary_harness_sha_mismatch"
  fi
  case "$ALLOW_HARNESS_MISMATCH" in
    true|false) ;;
    *) fail_canary "canary_harness" "canary_harness_mismatch_mode_invalid" ;;
  esac
  if [ "$CANDIDATE_SHA" != "unknown" ] && [ "$CHECKED_OUT_SHA" != "unknown" ] && [ "$CANDIDATE_SHA" != "$CHECKED_OUT_SHA" ]; then
    if [ "$ALLOW_HARNESS_MISMATCH" != "true" ]; then
      fail_canary "canary_harness" "canary_commit_mismatch"
    fi
    if [ "${GITHUB_EVENT_NAME:-}" != "workflow_dispatch" ]; then
      fail_canary "canary_harness" "canary_harness_mismatch_not_dispatch"
    fi
  fi
  echo "canary_expected_sha=$CANDIDATE_SHA"
  echo "canary_checked_out_sha=$CHECKED_OUT_SHA"
  echo "canary_harness_sha=$HARNESS_SHA"
}

run_release_config_guard() {
  if ! WARMUP_OUTPUT="$(.github/warmup-render.sh --expect-mode "$EXPECT_MODE")"; then
    print_sanitized_warmup_output
    fail_canary "release_config" "warmup_probe_failed"
  fi
  print_sanitized_warmup_output

  ENV_FINGERPRINT="$(extract_warmup_value env_fingerprint || true)"
  WORKFLOW_ENV_FINGERPRINT="$(extract_warmup_value workflow_env_fingerprint || true)"
  WORKFLOW_ENV_STATUS="$(extract_warmup_value workflow_env_status || true)"
  WORKFLOW_RUNTIME_PROVIDER_MODE="$(extract_warmup_value workflow_runtime_provider_mode || true)"
  WORKFLOW_RUNTIME_PROOF="$(extract_warmup_value workflow_runtime_proof || true)"
  WORKFLOW_TASK="$(extract_warmup_value workflow_task || true)"
  REAL_WORKFLOW_TASK="$(extract_warmup_value real_workflow_task || true)"
  local warmup_profile_status
  local warmup_profile_hash
  warmup_profile_status="$(extract_warmup_value release_profile_status || true)"
  warmup_profile_hash="$(extract_warmup_value release_profile_hash || true)"

  if [ "$warmup_profile_status" != "ready" ] || [ "$warmup_profile_hash" != "$RELEASE_PROFILE_HASH" ]; then
    fail_canary "release_config" "release_profile_hash_mismatch"
  fi
  if [[ ! "$ENV_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]]; then
    fail_canary "release_config" "missing_env_fingerprint"
  fi
  if [[ ! "$WORKFLOW_ENV_FINGERPRINT" =~ ^[0-9a-f]{64}$ ]] || [ "$WORKFLOW_ENV_STATUS" != "ready" ]; then
    fail_canary "release_config" "workflow_env_drift"
  fi
  if [ "$WORKFLOW_RUNTIME_PROVIDER_MODE" != "live_provider" ] || [ "$WORKFLOW_RUNTIME_PROOF" != "ready" ]; then
    fail_canary "release_config" "workflow_runtime_proof_missing"
  fi
  if [ -z "$WORKFLOW_TASK" ] || [ -z "$REAL_WORKFLOW_TASK" ]; then
    fail_canary "release_config" "workflow_task_missing"
  fi

  echo "canary_expected_mode=$EXPECT_MODE"
  echo "canary_release_profile_hash=$RELEASE_PROFILE_HASH"
  echo "canary_env_fingerprint=$ENV_FINGERPRINT"
  echo "canary_workflow_env_fingerprint=$WORKFLOW_ENV_FINGERPRINT"
  echo "canary_workflow_env_status=$WORKFLOW_ENV_STATUS"
  echo "canary_workflow_runtime_provider_mode=$WORKFLOW_RUNTIME_PROVIDER_MODE"
  echo "canary_workflow_runtime_proof=$WORKFLOW_RUNTIME_PROOF"
  echo "canary_workflow_task=$WORKFLOW_TASK"
  echo "canary_real_workflow_task=$REAL_WORKFLOW_TASK"
}

mint_browser_session_state() {
  if ! (
    cd web
    ARGUS_CANARY_APP_URL="$APP_URL" \
    ARGUS_CANARY_EMAIL="$EMAIL" \
    ARGUS_CANARY_SUPABASE_URL="$SUPABASE_URL" \
    ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
    ARGUS_CANARY_BROWSER_STORAGE_STATE="$BROWSER_STORAGE_STATE" \
    ARGUS_CANARY_BROWSER_SESSION_HANDOFF="$BROWSER_SESSION_HANDOFF" \
      bun e2e/support/private-alpha-canary-session.ts mint
  ); then
    if [ -s "$BROWSER_SESSION_HANDOFF" ]; then
      BROWSER_SESSION_MINTED="true"
    fi
    return 1
  fi
  BROWSER_SESSION_MINTED="true"
}

revoke_browser_session() {
  (
    cd web
    ARGUS_CANARY_SUPABASE_URL="$SUPABASE_URL" \
    ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY="$SUPABASE_SERVICE_ROLE_KEY" \
    ARGUS_CANARY_BROWSER_SESSION_HANDOFF="$BROWSER_SESSION_HANDOFF" \
      bun e2e/support/private-alpha-canary-session.ts revoke
  )
}

revoke_browser_session_once() {
  if [ "${BROWSER_SESSION_MINTED:-false}" != "true" ]; then
    return 0
  fi
  if ! revoke_browser_session; then
    return 1
  fi
  BROWSER_SESSION_MINTED="false"
}

load_browser_session() {
  local values
  if ! values="$(CANARY_SESSION_EMAIL="$EMAIL" python3 - "$BROWSER_SESSION_HANDOFF" <<'PY'
import json
import os
import pathlib
import stat
import sys

path = pathlib.Path(sys.argv[1])
if not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
    raise SystemExit("private browser session handoff is missing or exposed")
payload = json.loads(path.read_text(encoding="utf-8"))
if payload.get("schema_version") != 1:
    raise SystemExit("private browser session handoff has the wrong schema")
email = str(payload.get("email") or "").strip().casefold()
if email != os.environ["CANARY_SESSION_EMAIL"].strip().casefold():
    raise SystemExit("private browser session belongs to the wrong identity")
for key in ("user_id", "access_token", "refresh_token"):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit("private browser session handoff is incomplete")
    print(value)
PY
  )"; then
    return 1
  fi
  USER_ID="$(printf '%s\n' "$values" | sed -n '1p')"
  BROWSER_ACCESS_TOKEN="$(printf '%s\n' "$values" | sed -n '2p')"
  printf 'header = "Authorization: Bearer %s"\n' "$BROWSER_ACCESS_TOKEN" \
    > "$BROWSER_AUTH_CURL_CONFIG"
  chmod 600 "$BROWSER_AUTH_CURL_CONFIG"
}

run_browser_checks() {
  local browser_checks
  browser_checks="$(grep -vFx -- "$SAME_COMMIT_CHECK" <<< "$REQUIRED_CHECKS" || true)"
  if ! env -u CUADRAO_OPS_TOKEN \
    -u ARGUS_WORKFLOW_DATABASE_URL \
    -u RENDER_API_KEY \
    -u SUPABASE_SERVICE_ROLE_KEY \
    -u ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY \
    ARGUS_CANARY_BROWSER_STORAGE_STATE="$BROWSER_STORAGE_STATE" \
    ARGUS_CANARY_BROWSER_USER_ID="$USER_ID" \
    ARGUS_CANARY_BROWSER_CHECKS="$browser_checks" \
    ARGUS_CANARY_BROWSER_CHECKS_HANDOFF="$BROWSER_CHECKS_HANDOFF" \
    ARGUS_CANARY_BROWSER_ARTIFACT_PROBE="$ARTIFACT_PROBE" \
    ARGUS_CANARY_BROWSER_REDACTION_PROBE_VALUE="$REDACTION_PROBE_VALUE" \
    "$SCRIPT_DIR/canary-browser.sh"; then
    BROWSER_STATUS="failed"
    return 1
  fi
  BROWSER_STATUS="passed"
}

import_browser_check_results() {
  local values
  if ! values="$(
    CANARY_SESSION_USER_ID="$USER_ID" \
    CANARY_REQUIRED_CHECKS="$REQUIRED_CHECKS" \
    CANARY_SAME_COMMIT_CHECK="$SAME_COMMIT_CHECK" \
    CANARY_HANDOFF_CONTRACT="$ROOT_DIR/web/e2e/support/private-alpha-canary-handoff.json" \
    python3 - "$BROWSER_CHECKS_HANDOFF" "$BROWSER_CHECK_EVIDENCE" "$BROWSER_RAW_IDS" <<'PY'
import hashlib
import json
import os
import pathlib
import re
import stat
import sys

handoff_path, evidence_path, raw_ids_path = (pathlib.Path(arg) for arg in sys.argv[1:4])
if not handoff_path.is_file() or not handoff_path.read_text(encoding="utf-8").strip():
    raise SystemExit("browser check handoff is missing")
if stat.S_IMODE(handoff_path.stat().st_mode) & 0o077:
    raise SystemExit("browser check handoff permissions are not private")
try:
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    raise SystemExit("browser check handoff is invalid") from exc
# The browser's handoff contract file owns what the browser may report.
contract = json.loads(
    pathlib.Path(os.environ["CANARY_HANDOFF_CONTRACT"]).read_text(encoding="utf-8")
)
statuses = contract["statuses"]
reason_contract = contract["reason"]
if (
    payload.get("schema_version") != contract["schema_version"]
    or payload.get("source") != contract["source"]
):
    raise SystemExit("browser check handoff contract is invalid")
if payload.get("user_id") != os.environ["CANARY_SESSION_USER_ID"]:
    raise SystemExit("browser check handoff belongs to another identity")

required = [name for name in os.environ["CANARY_REQUIRED_CHECKS"].splitlines() if name]
browser_checks = [name for name in required if name != os.environ["CANARY_SAME_COMMIT_CHECK"]]
checks = payload.get("checks")
if not isinstance(checks, dict) or list(checks) != browser_checks:
    raise SystemExit("browser check handoff does not report the profile's browser checks")

reason_pattern = re.compile(reason_contract["pattern"])
id_pattern = re.compile(r"[0-9A-Za-z_-]{1,64}")
evidence: dict[str, dict[str, object]] = {}
raw_ids: list[str] = []
failed: tuple[str, str, dict] | None = None
for name in browser_checks:
    entry = checks[name]
    if not isinstance(entry, dict) or entry.get("status") not in set(statuses.values()):
        raise SystemExit("browser check handoff has an invalid check status")
    summary: dict[str, object] = {"status": entry["status"]}
    reason = entry.get("reason")
    if reason is not None:
        if (
            not isinstance(reason, str)
            or len(reason) > reason_contract["max_length"]
            or not reason_pattern.fullmatch(reason)
        ):
            raise SystemExit("browser check handoff has an unsafe failure reason")
        summary["reason"] = reason
    attempts = entry.get("sign_in_attempts")
    if attempts is not None:
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise SystemExit("browser check handoff has an invalid sign-in attempt count")
        summary["sign_in_attempts"] = attempts
    for key, value in entry.items():
        if not key.endswith("_id") or value is None:
            continue
        if not isinstance(value, str) or not id_pattern.fullmatch(value):
            raise SystemExit("browser check handoff has an invalid identity")
        raw_ids.append(value)
        prefix = key[: -len("_id")]
        summary[f"{prefix}_label"] = (
            f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:12]}"
        )
    evidence[name] = summary
    if entry["status"] != statuses["passed"] and failed is None:
        failed = (name, reason or f"check_{entry['status']}", entry)

evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
raw_ids_path.write_text("\n".join(raw_ids) + "\n", encoding="utf-8")
for name, summary in evidence.items():
    line = f"canary_check={name} status={summary['status']}"
    if "reason" in summary:
        line += f" reason={summary['reason']}"
    if "sign_in_attempts" in summary:
        line += f" sign_in_attempts={summary['sign_in_attempts']}"
    print(line, file=sys.stderr)

if failed is None:
    print("-|-|-|-")
else:
    name, reason, entry = failed
    def identity(key: str) -> str:
        value = entry.get(key)
        return value if isinstance(value, str) else "-"
    print("|".join((name, reason, identity("conversation_id"), identity("backtest_job_id"))))
PY
  )"; then
    return 1
  fi
  IFS='|' read -r \
    BROWSER_FAILED_CHECK \
    BROWSER_FAILURE_REASON \
    FAILED_CONVERSATION_ID \
    FAILED_BACKTEST_JOB_ID <<< "$values"
  [ "$BROWSER_FAILED_CHECK" = "-" ] && BROWSER_FAILED_CHECK=""
  [ "$BROWSER_FAILURE_REASON" = "-" ] && BROWSER_FAILURE_REASON=""
  [ "$FAILED_CONVERSATION_ID" = "-" ] && FAILED_CONVERSATION_ID=""
  [ "$FAILED_BACKTEST_JOB_ID" = "-" ] && FAILED_BACKTEST_JOB_ID=""
  echo "canary_browser_check_handoff=verified"
}

recover_browser_failure_capture_inputs() {
  if [ -z "$FAILED_CONVERSATION_ID" ] || [ -z "$BROWSER_ACCESS_TOKEN" ]; then
    return 0
  fi
  curl -fsS --config "$BROWSER_AUTH_CURL_CONFIG" \
    "${API_URL}/api/v1/conversations/${FAILED_CONVERSATION_ID}/messages" \
    > "$API_MESSAGES_RESPONSE" || true
  if [ -n "$FAILED_BACKTEST_JOB_ID" ]; then
    curl -fsS --config "$BROWSER_AUTH_CURL_CONFIG" \
      "${API_URL}/api/v1/backtest-jobs/${FAILED_BACKTEST_JOB_ID}" \
      > "$API_JOB_RESPONSE" || true
  fi
  echo "canary_failed_browser_capture_inputs=collected"
}

redact_browser_artifacts() {
  local results_dir="web/temp/playwright-results"
  [ -d "$results_dir" ] || return 0
  rm -f "$results_dir/.redacted"
  CANARY_REDACT_DIR="$results_dir" \
  CANARY_REDACT_PASSWORD="$PASSWORD" \
  CANARY_REDACT_EMAIL="$EMAIL" \
  CANARY_REDACT_SESSION_PATH="$BROWSER_SESSION_HANDOFF" \
  CANARY_REDACT_STORAGE_STATE_PATH="$BROWSER_STORAGE_STATE" \
  CANARY_REDACT_PROBE_VALUE="$REDACTION_PROBE_VALUE" \
  CANARY_REDACT_SIMULATE_FAILURE="$SIMULATE_REDACTION_FAILURE" \
    python3 - <<'PY'
import json
import os
import pathlib

from scripts.ops.canary_capture_sanitizer import UUID_PATTERN

# Playwright's failure context embeds every rendered input value, including the
# canary credential probe, so no browser artifact leaves this job unmasked.
directory = pathlib.Path(os.environ["CANARY_REDACT_DIR"])
if os.environ.get("CANARY_REDACT_SIMULATE_FAILURE") == "true":
    raise SystemExit("simulated browser artifact redaction failure")

session_values = []
session_path_value = os.environ.get("CANARY_REDACT_SESSION_PATH", "").strip()
if session_path_value:
    session_path = pathlib.Path(session_path_value)
    if session_path.is_file() and session_path.stat().st_size:
        payload = json.loads(session_path.read_text(encoding="utf-8"))
        for key in ("access_token", "refresh_token"):
            value = payload.get(key) if isinstance(payload, dict) else None
            if isinstance(value, str) and value:
                session_values.append(value)
storage_state_value = os.environ.get("CANARY_REDACT_STORAGE_STATE_PATH", "").strip()
if storage_state_value:
    storage_path = pathlib.Path(storage_state_value)
    if storage_path.is_file() and storage_path.stat().st_size:
        storage_state = json.loads(storage_path.read_text(encoding="utf-8"))
        cookies = storage_state.get("cookies") if isinstance(storage_state, dict) else None
        if isinstance(cookies, list):
            for cookie in cookies:
                value = cookie.get("value") if isinstance(cookie, dict) else None
                if isinstance(value, str) and value:
                    session_values.append(value)
masked_values = sorted(
    (
        value
        for value in (
            os.environ.get("CANARY_REDACT_PASSWORD", "").strip(),
            os.environ.get("CANARY_REDACT_EMAIL", "").strip(),
            os.environ.get("CANARY_REDACT_PROBE_VALUE", "").strip(),
            *session_values,
        )
        if value
    ),
    key=len,
    reverse=True,
)
for path in sorted(directory.rglob("*")):
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        path.unlink(missing_ok=True)
        print(f"canary_browser_artifact_dropped={path.name}")
        continue
    redacted = text
    for value in masked_values:
        redacted = redacted.replace(value, "<redacted>")
    # Every rendered id is private, including ids from earlier canary runs.
    redacted = UUID_PATTERN.sub("<redacted>", redacted)
    if redacted != text:
        path.write_text(redacted, encoding="utf-8")
    path.chmod(0o600)
# The workflow uploads these files only when this marker exists, so a deployed
# tree without this redaction pass publishes nothing.
(directory / ".redacted").write_text("1\n", encoding="utf-8")
PY
}

run_disabled_signup_denial_canary() {
  env -u CUADRAO_OPS_TOKEN \
    -u SUPABASE_SERVICE_ROLE_KEY \
    -u ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY \
    CANARY_REQUESTED_SIGNUP_DENIAL_API_URL="$API_URL" \
    CANARY_REQUESTED_SIGNUP_DENIAL_EMAIL="$SIGNUP_EMAIL" \
    CANARY_REQUESTED_SIGNUP_DENIAL_OPS_TOKEN="$OPS_TOKEN" \
    python3 "$SCRIPT_DIR/canary-requested-signup-denial.py"
}

service_role_curl() {
  curl -fsS --config "$SERVICE_ROLE_CURL_CONFIG" "$@"
}

resolve_signup_identity() {
  CANARY_SIGNUP_RUN_ID="$SIGNUP_RUN_ID" \
    CANARY_SIGNUP_RUN_ATTEMPT="$SIGNUP_RUN_ATTEMPT" \
    CANARY_SIGNUP_LOCAL_NONCE="$SIGNUP_LOCAL_NONCE" \
    python3 - <<'PY'
import os
import re

run_id = os.environ["CANARY_SIGNUP_RUN_ID"]
run_attempt = os.environ["CANARY_SIGNUP_RUN_ATTEMPT"]
local_nonce = os.environ["CANARY_SIGNUP_LOCAL_NONCE"]
safe_local_nonce = re.fullmatch(
    r"[a-z0-9](?:[a-z0-9-]{6,40}[a-z0-9])",
    local_nonce,
)
safe_run_id = re.fullmatch(r"[1-9][0-9]*", run_id)
safe_run_attempt = re.fullmatch(r"[1-9][0-9]*", run_attempt)
if run_id and run_attempt and not local_nonce:
    if not (safe_run_id and safe_run_attempt):
        raise SystemExit(1)
    print(f"delivered+argus-{run_id}-{run_attempt}@resend.dev")
elif not run_id and not run_attempt and safe_local_nonce:
    print(f"delivered+argus-local-{local_nonce}@resend.dev")
else:
    raise SystemExit(1)
PY
}

signup_identity_is_safe() {
  CANARY_LOGIN_EMAIL="$EMAIL" \
    CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" \
    CANARY_SIGNUP_RUN_ID="$SIGNUP_RUN_ID" \
    CANARY_SIGNUP_RUN_ATTEMPT="$SIGNUP_RUN_ATTEMPT" \
    CANARY_SIGNUP_LOCAL_NONCE="$SIGNUP_LOCAL_NONCE" \
    python3 - <<'PY'
import os
import re

login_email = os.environ["CANARY_LOGIN_EMAIL"].strip().casefold()
signup_email = os.environ["CANARY_SIGNUP_EMAIL"]
run_id = os.environ["CANARY_SIGNUP_RUN_ID"]
run_attempt = os.environ["CANARY_SIGNUP_RUN_ATTEMPT"]
local_nonce = os.environ["CANARY_SIGNUP_LOCAL_NONCE"]
safe_local_nonce = re.fullmatch(
    r"[a-z0-9](?:[a-z0-9-]{6,40}[a-z0-9])",
    local_nonce,
)
safe_run_id = re.fullmatch(r"[1-9][0-9]*", run_id)
safe_run_attempt = re.fullmatch(r"[1-9][0-9]*", run_attempt)
if run_id and run_attempt and not local_nonce:
    expected_signup_email = f"delivered+argus-{run_id}-{run_attempt}@resend.dev"
    mode_is_safe = bool(safe_run_id and safe_run_attempt)
elif not run_id and not run_attempt and safe_local_nonce:
    expected_signup_email = f"delivered+argus-local-{local_nonce}@resend.dev"
    mode_is_safe = True
else:
    expected_signup_email = ""
    mode_is_safe = False
raise SystemExit(
    0
    if mode_is_safe
    and signup_email == expected_signup_email
    and login_email != signup_email.casefold()
    else 1
)
PY
}

collect_signup_auth_user_ids() {
  local page=1
  local page_count
  : > "$SIGNUP_AUTH_USER_IDS"
  while [ "$page" -le 1000 ]; do
    if ! service_role_curl \
      "${SUPABASE_URL}/auth/v1/admin/users?page=${page}&per_page=1000" \
      > "$SIGNUP_AUTH_USERS_RESPONSE"; then
      return 1
    fi
    if ! CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" python3 - "$SIGNUP_AUTH_USERS_RESPONSE" \
      >> "$SIGNUP_AUTH_USER_IDS" <<'PY'; then
import json
import os
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
users = payload.get("users") if isinstance(payload, dict) else payload
if not isinstance(users, list):
    raise SystemExit(1)
target = os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold()
for user in users:
    if not isinstance(user, dict):
        continue
    if str(user.get("email") or "").strip().casefold() != target:
        continue
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise SystemExit(1)
    print(user_id)
PY
      return 1
    fi
    if ! page_count="$(python3 - "$SIGNUP_AUTH_USERS_RESPONSE" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
users = payload.get("users") if isinstance(payload, dict) else payload
if not isinstance(users, list):
    raise SystemExit(1)
print(len(users))
PY
    )"; then
      return 1
    fi
    if [ "$page_count" -lt 1000 ]; then
      return 0
    fi
    page=$((page + 1))
  done
  return 1
}

delete_signup_auth_identity() {
  local user_id
  local delete_failed=0
  if ! collect_signup_auth_user_ids; then
    return 1
  fi
  while IFS= read -r user_id; do
    if [ -z "$user_id" ]; then
      continue
    fi
    if ! service_role_curl -X DELETE \
      "${SUPABASE_URL}/auth/v1/admin/users/${user_id}" >/dev/null; then
      delete_failed=1
    fi
  done < "$SIGNUP_AUTH_USER_IDS"
  if [ "$delete_failed" -ne 0 ]; then
    return 1
  fi
  if ! collect_signup_auth_user_ids; then
    return 1
  fi
  [ ! -s "$SIGNUP_AUTH_USER_IDS" ]
}

encoded_signup_email() {
  CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" python3 - <<'PY'
import os
import urllib.parse

print(urllib.parse.quote(os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold(), safe=""))
PY
}

delete_signup_allowlist() {
  local encoded_email
  if ! encoded_email="$(encoded_signup_email)"; then
    return 1
  fi
  service_role_curl \
    -X DELETE \
    -H "Prefer: return=minimal" \
    "${SUPABASE_URL}/rest/v1/private_alpha_allowlist?email=eq.${encoded_email}" \
    >/dev/null
}

insert_disabled_signup_allowlist() {
  local signup_body
  if ! signup_body="$(CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" CANARY_LANGUAGE="$LANGUAGE" python3 - <<'PY'
from datetime import datetime, timezone
import json
import os

print(
    json.dumps(
        {
            "email": os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold(),
            "role": "user",
            "language": os.environ["CANARY_LANGUAGE"],
            "disabled_at": datetime.now(timezone.utc).isoformat(),
        }
    )
)
PY
  )"; then
    return 1
  fi
  service_role_curl \
    -X POST \
    -H "Content-Type: application/json" \
    -H "Prefer: resolution=ignore-duplicates,return=representation" \
    -d "$signup_body" \
    "${SUPABASE_URL}/rest/v1/private_alpha_allowlist?on_conflict=email" \
    > "$SIGNUP_ALLOWLIST_RESPONSE" &&
    CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" python3 - "$SIGNUP_ALLOWLIST_RESPONSE" <<'PY'
import json
import os
import pathlib
import sys

rows = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
target = os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold()
if (
    not isinstance(rows, list)
    or len(rows) != 1
    or rows[0].get("email") != target
    or rows[0].get("role") != "user"
    or rows[0].get("disabled_at") is None
):
    raise SystemExit("disabled signup identity was not created exactly once")
PY
}

verify_no_signup_auth_identity() {
  collect_signup_auth_user_ids && [ ! -s "$SIGNUP_AUTH_USER_IDS" ]
}

stage_requested_signup_allowlist() {
  local encoded_email
  if ! encoded_email="$(encoded_signup_email)"; then
    return 1
  fi
  service_role_curl \
    -X PATCH \
    -H "Content-Type: application/json" \
    -H "Prefer: return=representation" \
    -d '{"role":"requested","disabled_at":null}' \
    "${SUPABASE_URL}/rest/v1/private_alpha_allowlist?email=eq.${encoded_email}&role=eq.user&disabled_at=not.is.null" \
    > "$SIGNUP_ALLOWLIST_RESPONSE" &&
    CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" python3 - "$SIGNUP_ALLOWLIST_RESPONSE" <<'PY'
import json
import os
import pathlib
import sys

rows = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
target = os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold()
if (
    not isinstance(rows, list)
    or len(rows) != 1
    or rows[0].get("email") != target
    or rows[0].get("role") != "requested"
    or rows[0].get("disabled_at") is not None
):
    raise SystemExit("disabled signup identity was not staged for approval")
PY
}

resolve_approve_path() {
  python3 - <<'PY'
import sys

sys.path.insert(0, "src")
from argus.api.ops_contract import ACCESS_REQUEST_APPROVE_PATH

print(ACCESS_REQUEST_APPROVE_PATH)
PY
}

approve_requested_signup_allowlist() {
  local approve_path
  if ! approve_path="$(resolve_approve_path)" || [ -z "$approve_path" ]; then
    return 1
  fi
  if ! CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" python3 - "$SIGNUP_APPROVAL_REQUEST" <<'PY'
import json
import os
import pathlib
import sys

normalized_email = os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold()
pathlib.Path(sys.argv[1]).write_text(
    json.dumps({"email": normalized_email}, separators=(",", ":")),
    encoding="utf-8",
)
PY
  then
    return 1
  fi
  curl -q -fsS \
    --config "$OPS_CURL_CONFIG" \
    -X POST \
    -H "Content-Type: application/json" \
    --data-binary "@$SIGNUP_APPROVAL_REQUEST" \
    "${API_URL}${approve_path}" \
    > "$SIGNUP_ALLOWLIST_RESPONSE" &&
    python3 - "$SIGNUP_ALLOWLIST_RESPONSE" <<'PY'
import json
import pathlib
import sys

try:
    payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit("requested signup promotion returned an invalid response") from exc
if (
    not isinstance(payload, dict)
    or set(payload) != {"approved"}
    or payload["approved"] is not True
):
    raise SystemExit("requested signup promotion was not approved")
PY
}

verify_welcome_delivery_recorded() {
  local encoded_email
  if ! encoded_email="$(encoded_signup_email)"; then
    return 1
  fi
  service_role_curl \
    "${SUPABASE_URL}/rest/v1/private_alpha_access_welcome_deliveries?recipient_email=eq.${encoded_email}&select=recipient_email,provider_receipt,sent_at" \
    > "$SIGNUP_ALLOWLIST_RESPONSE" &&
    CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" \
      CANARY_RUN_STARTED_AT="$CANARY_RUN_STARTED_AT" \
      python3 - "$SIGNUP_ALLOWLIST_RESPONSE" <<'PY'
import datetime
import json
import os
import pathlib
import sys

rows = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
target = os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold()
started = datetime.datetime.fromisoformat(
    os.environ["CANARY_RUN_STARTED_AT"].replace("Z", "+00:00")
)
if not isinstance(rows, list) or len(rows) != 1:
    raise SystemExit("welcome delivery read-back did not find exactly one row")
row = rows[0]
if row.get("recipient_email") != target:
    raise SystemExit("welcome delivery read-back returned a different recipient")
receipt = row.get("provider_receipt")
if not isinstance(receipt, str) or not receipt.strip():
    raise SystemExit("welcome delivery read-back has no provider receipt")
sent_raw = row.get("sent_at")
if not isinstance(sent_raw, str):
    raise SystemExit("welcome delivery read-back has no sent_at")
sent = datetime.datetime.fromisoformat(sent_raw.replace("Z", "+00:00"))
if sent < started:
    raise SystemExit("welcome delivery read-back predates this canary run")
PY
}

cleanup_welcome_artifacts() {
  CANARY_SIGNUP_EMAIL="$SIGNUP_EMAIL" python3 - "$SIGNUP_APPROVAL_REQUEST" <<'PY'
import json
import os
import pathlib
import sys

normalized_email = os.environ["CANARY_SIGNUP_EMAIL"].strip().casefold()
pathlib.Path(sys.argv[1]).write_text(
    json.dumps({"p_email": normalized_email}, separators=(",", ":")),
    encoding="utf-8",
)
PY
  service_role_curl \
    -X POST \
    -H "Content-Type: application/json" \
    --data-binary "@$SIGNUP_APPROVAL_REQUEST" \
    "${SUPABASE_URL}/rest/v1/rpc/delete_private_alpha_access_welcome_artifacts" \
    > "$SIGNUP_ALLOWLIST_RESPONSE" &&
    python3 - "$SIGNUP_ALLOWLIST_RESPONSE" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload is not True:
    raise SystemExit("welcome artifact cleanup was refused")
PY
}

prepare_signup_identity() {
  SIGNUP_IDENTITY_SETUP_ATTEMPTED="true"
  delete_signup_auth_identity &&
    delete_signup_allowlist &&
    cleanup_welcome_artifacts &&
    insert_disabled_signup_allowlist
}

cleanup_signup_identity() {
  local cleanup_failed=0
  delete_signup_auth_identity || cleanup_failed=1
  delete_signup_allowlist || cleanup_failed=1
  cleanup_welcome_artifacts || cleanup_failed=1
  return "$cleanup_failed"
}

require_supabase_verifier_inputs() {
  if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_SERVICE_ROLE_KEY" ]; then
    fail_canary "canary_harness" "missing_supabase_verifier_credentials"
  fi
}

run_release_coherence_surface() {
  if [ -z "$OPS_TOKEN" ]; then
    fail_canary "canary_harness" "missing_ops_token"
  fi
  if ! SIGNUP_EMAIL="$(resolve_signup_identity)"; then
    fail_canary "canary_harness" "canary_signup_identity_not_safe"
  fi
  if [ -z "$SIGNUP_EMAIL" ]; then
    fail_canary "canary_harness" "missing_canary_signup_email"
  fi
  if ! signup_identity_is_safe; then
    fail_canary "canary_harness" "canary_signup_identity_not_safe"
  fi
  prepare_capture_destination
  validate_canary_harness_contract
  run_same_commit_check
  run_release_config_guard
  if ! prepare_signup_identity; then
    fail_canary "disabled_signup_denial" "canary_signup_identity_setup_failed"
  fi
  if ! run_disabled_signup_denial_canary; then
    fail_canary "disabled_signup_denial" "disabled_signup_was_not_denied"
  fi
  if ! verify_no_signup_auth_identity; then
    fail_canary "disabled_signup_denial" "disabled_signup_has_auth_identity"
  fi
  if ! stage_requested_signup_allowlist; then
    fail_canary "welcome_email" "disabled_signup_approval_staging_failed"
  fi
  if ! approve_requested_signup_allowlist; then
    fail_canary "welcome_email" "requested_signup_approval_failed"
  fi
  if ! verify_welcome_delivery_recorded; then
    fail_canary "welcome_email" "welcome_delivery_not_recorded"
  fi
  CANARY_STATUS="passed"
  CANARY_CAPTURE_WRITE_STATUS="not_written_success"
  write_canary_evidence
  echo "Release coherence passed: one commit on all three services, release config, signup denial, and the welcome email."
}

validate_browser_artifact_probe() {
  case "$ARTIFACT_PROBE" in
    none)
      if [ "$SIMULATE_REDACTION_FAILURE" != "false" ]; then
        fail_canary "canary_harness" "redaction_failure_simulation_without_probe"
      fi
      ;;
    redacted)
      if [ "$SIMULATE_REDACTION_FAILURE" != "false" ] || [ -z "$REDACTION_PROBE_VALUE" ]; then
        fail_canary "canary_harness" "redacted_probe_config_invalid"
      fi
      ;;
    unredacted)
      if [ "$SIMULATE_REDACTION_FAILURE" != "true" ] || [ -z "$REDACTION_PROBE_VALUE" ]; then
        fail_canary "canary_harness" "unredacted_probe_config_invalid"
      fi
      ;;
    *) fail_canary "canary_harness" "browser_artifact_probe_invalid" ;;
  esac
  if [ "$ARTIFACT_PROBE" != "none" ] && [ "${GITHUB_EVENT_NAME:-}" != "workflow_dispatch" ]; then
    fail_canary "canary_harness" "browser_artifact_probe_not_dispatch"
  fi
}

run_authenticated_browser_surface() {
  if [ -z "$EMAIL" ]; then
    fail_canary "canary_harness" "missing_canary_email"
  fi
  validate_browser_artifact_probe
  prepare_capture_destination
  validate_canary_harness_contract
  run_same_commit_check
  if ! mint_browser_session_state; then
    fail_canary "$SIGN_IN_CHECK" "authenticated_session_mint_failed"
  fi
  if ! load_browser_session; then
    fail_canary "$SIGN_IN_CHECK" "authenticated_session_handoff_failed"
  fi
  if ! run_browser_checks; then
    if [ "$ARTIFACT_PROBE" != "none" ]; then
      fail_canary "canary_harness" "browser_artifact_probe_${ARTIFACT_PROBE}"
    fi
    if ! import_browser_check_results; then
      fail_canary "$SIGN_IN_CHECK" "browser_checks_reported_no_result"
    fi
    if [ -z "$BROWSER_FAILED_CHECK" ]; then
      fail_canary "canary_harness" "browser_checks_exited_red"
    fi
    recover_browser_failure_capture_inputs || true
    fail_canary "$BROWSER_FAILED_CHECK" "$BROWSER_FAILURE_REASON"
  fi
  if ! import_browser_check_results; then
    fail_canary "canary_harness" "browser_check_handoff_invalid"
  fi
  if [ -n "$BROWSER_FAILED_CHECK" ]; then
    fail_canary "$BROWSER_FAILED_CHECK" "$BROWSER_FAILURE_REASON"
  fi
  run_same_commit_check
  if ! revoke_browser_session_once; then
    fail_canary "canary_harness" "authenticated_session_revocation_failed"
  fi
  CANARY_STATUS="passed"
  CANARY_CAPTURE_WRITE_STATUS="not_written_success"
  write_canary_evidence
  echo "Authenticated browser checks passed: a signed-in answer, one completed backtest, and a research answer with sources."
}

require_supabase_verifier_inputs
case "$SURFACE" in
  release-coherence)
    run_release_coherence_surface
    ;;
  authenticated-browser-journey)
    run_authenticated_browser_surface
    ;;
  *)
    fail_canary "canary_harness" "canary_surface_invalid"
    ;;
esac
