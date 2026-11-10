#!/bin/bash
# Sync selected Argus env vars to Render without printing secret values.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/argus-env.sh"
argus_load_root_env >/dev/null || true

API_SERVICE_ID="${ARGUS_RENDER_API_SERVICE_ID:-$ARGUS_PRIVATE_LAUNCH_API_SERVICE_ID}"
WEB_SERVICE_ID="${ARGUS_RENDER_WEB_SERVICE_ID:-$ARGUS_PRIVATE_LAUNCH_WEB_SERVICE_ID}"

usage() {
  cat <<'USAGE'
Usage:
  .github/render-env-sync.sh api-status
  .github/render-env-sync.sh api-deploy-status
  .github/render-env-sync.sh web-deploy-status
  .github/render-env-sync.sh api-safe-off
  .github/render-env-sync.sh api-proof-shadow-on
  .github/render-env-sync.sh api-real-workflow-on
  .github/render-env-sync.sh api-runtime
  .github/render-env-sync.sh release-config-audit --expect-mode <safe-off|proof-shadow>

Commands:
  api-status              Print redacted API workflow env status for cuadrao-api.
  api-deploy-status       Print latest cuadrao-api deploy status and commit.
  web-deploy-status       Print latest cuadrao-marketing deploy status and commit.
  api-safe-off            Retired; exits without changing hosted settings.
  api-proof-shadow-on     Retired; exits without changing hosted settings.
  api-real-workflow-on    Retired; exits without changing hosted settings.
  api-runtime             Sync cuadrao-api build/start commands.
  release-config-audit    Read-only production audit against the settings manifest, with redacted fingerprints.

Compatibility aliases:
  api-dispatch-on   Alias for api-proof-shadow-on.
  api-dispatch-off  Alias for api-safe-off.

Required local env:
  RENDER_API_KEY
USAGE
}

RELEASE_PROFILE_TOOL="$SCRIPT_DIR/private-alpha-release-profile.py"

release_profile_validate() {
  python3 "$RELEASE_PROFILE_TOOL" validate
}

release_profile_hash() {
  python3 "$RELEASE_PROFILE_TOOL" hash
}

manifest_env_pairs() {
  local surface="$1"
  python3 "$ARGUS_SETTINGS_TOOL" print production "$surface"
}

release_profile_auto_deploy_trigger() {
  local surface="$1"
  python3 "$RELEASE_PROFILE_TOOL" auto-deploy-trigger "$surface"
}

manifest_required_present() {
  local surface="$1"
  python3 "$ARGUS_SETTINGS_TOOL" names production "$surface" required
}

manifest_allowed_keys() {
  local surface="$1"
  python3 "$ARGUS_SETTINGS_TOOL" names production "$surface" allowed
}

AUDIT_FAILURES=0
AUDIT_FINGERPRINT_ROWS=()
AUTODEPLOY_AUDIT_FAILURES=0
AUTODEPLOY_AUDIT_FINGERPRINT_ROWS=()

require_local_env() {
  local name="$1"
  argus_require_env "$name"
}

put_render_env() {
  local service_id="$1"
  local key="$2"
  local value="$3"

  curl -fsS \
    --request PUT \
    --url "https://api.render.com/v1/services/${service_id}/env-vars/${key}" \
    --header "Authorization: Bearer ${RENDER_API_KEY}" \
    --header "Accept: application/json" \
    --header "Content-Type: application/json" \
    --data "$(jq -nc --arg value "$value" '{value: $value}')" \
    >/dev/null

  echo "synced ${service_id}:${key}"
}

delete_render_env() {
  local service_id="$1"
  local key="$2"
  local status

  status="$(
    curl -sS \
      -o /dev/null \
      -w "%{http_code}" \
      --request DELETE \
      --url "https://api.render.com/v1/services/${service_id}/env-vars/${key}" \
      --header "Authorization: Bearer ${RENDER_API_KEY}" \
      --header "Accept: application/json"
  )"

  if [ "$status" = "404" ]; then
    echo "already absent ${service_id}:${key}"
    return
  fi

  if [[ "$status" != 2* ]]; then
    echo "failed to delete ${service_id}:${key} (HTTP ${status})"
    exit 1
  fi

  echo "deleted ${service_id}:${key}"
}

render_env_json() {
  local service_id="$1"

  curl -fsS \
    --request GET \
    --url "https://api.render.com/v1/services/${service_id}/env-vars?limit=100" \
    --header "Authorization: Bearer ${RENDER_API_KEY}" \
    --header "Accept: application/json"
}

render_service_json() {
  local service_id="$1"

  curl -fsS \
    --request GET \
    --url "https://api.render.com/v1/services/${service_id}" \
    --header "Authorization: Bearer ${RENDER_API_KEY}" \
    --header "Accept: application/json"
}

render_service_deploy_json() {
  local service_id="$1"

  curl -fsS \
    --request GET \
    --url "https://api.render.com/v1/services/${service_id}/deploys?limit=1" \
    --header "Authorization: Bearer ${RENDER_API_KEY}" \
    --header "Accept: application/json"
}

print_api_status() {
  require_local_env RENDER_API_KEY
  render_env_json "$API_SERVICE_ID" | jq -r '
    [
      "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED",
      "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED",
      "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED",
      "ARGUS_BACKTEST_WORKFLOW_TASK",
      "ARGUS_BACKTEST_REAL_WORKFLOW_TASK",
      "ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT",
      "ARGUS_BACKTEST_JOBS_USER_QUEUED_LIMIT",
      "ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT",
      "ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT",
      "RENDER_API_KEY"
    ] as $keys
    | [ .[]?.envVar? ] as $vars
    | $keys[]
    | . as $key
    | ($vars | map(select(.key == $key)) | .[0].value // null) as $value
    | if $key == "RENDER_API_KEY" then
        "\($key)=\(if ($value // "") == "" then "<missing-or-empty>" else "<redacted-present>" end)"
      else
        "\($key)=\($value // "<missing>")"
      end
  ' | sort
}

print_deploy_status() {
  local service_id="$1"
  local service_name="$2"

  render_service_deploy_json "$service_id" | jq -r --arg service_name "$service_name" '
    .[0].deploy as $deploy
    | if $deploy == null then
        "service=\($service_name)",
        "deploy_id=<missing>",
        "status=<missing>",
        "commit=<missing>",
        "commit_short=<missing>"
      else
        ($deploy.commit.id // "") as $commit
        | "service=\($service_name)",
          "deploy_id=\($deploy.id // "<missing>")",
          "status=\($deploy.status // "<missing>")",
          "commit=\(if $commit == "" then "<missing>" else $commit end)",
          "commit_short=\(if $commit == "" then "<missing>" else $commit[0:7] end)",
          "created_at=\($deploy.createdAt // "<missing>")",
          "finished_at=\($deploy.finishedAt // "<missing>")"
      end
  '
}

print_api_deploy_status() {
  require_local_env RENDER_API_KEY
  print_deploy_status "$API_SERVICE_ID" "cuadrao-api"
}

print_web_deploy_status() {
  require_local_env RENDER_API_KEY
  print_deploy_status "$WEB_SERVICE_ID" "cuadrao-marketing"
}

is_secret_render_env_key() {
  local key="$1"
  case "$key" in
    CUADRAO_OPS_TOKEN|CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD|DATABASE_URL|ARGUS_WORKFLOW_DATABASE_URL|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_JWT_SECRET|RENDER_API_KEY|OPENROUTER_API_KEY|CUADRAO_OPENROUTER_API_KEY_DEV|CUADRAO_OPENROUTER_API_KEY_STG|CUADRAO_OPENROUTER_API_KEY_PROD|CUADRAO_PROD_OPENROUTER_API_KEY|CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY|ALPACA_API_KEY|ALPACA_SECRET_KEY|NEXT_PUBLIC_POSTHOG_KEY|RESEND_API_KEY|CUADRAO_WAITLIST_TURNSTILE_SECRET)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

render_env_raw_value() {
  local env_json="$1"
  local key="$2"

  jq -r --arg key "$key" '
    [ .[]?.envVar? ] as $vars
    | ($vars | map(select(.key == $key)) | .[0].value // "")
  ' <<< "$env_json"
}

render_env_keys() {
  local env_json="$1"

  jq -r '
    [ .[]?.envVar? ] as $vars
    | $vars[]
    | .key // empty
  ' <<< "$env_json"
}

render_env_has_key() {
  local env_json="$1"
  local key="$2"

  jq -e --arg key "$key" '
    [ .[]?.envVar? ] as $vars
    | any($vars[]; .key == $key)
  ' <<< "$env_json" >/dev/null
}

list_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    if [ "$item" = "$needle" ]; then
      return 0
    fi
  done
  return 1
}

record_audit_row() {
  local service="$1"
  local row="$2"

  AUDIT_FINGERPRINT_ROWS+=("${service}:${row}")
}

record_audit_failure() {
  AUDIT_FAILURES=$((AUDIT_FAILURES + 1))
}

render_env_status_value() {
  local env_json="$1"
  local key="$2"
  local value

  value="$(render_env_raw_value "$env_json" "$key")"
  if is_secret_render_env_key "$key"; then
    if [ -z "$value" ]; then
      echo "<missing-or-empty>"
    else
      echo "<redacted-present>"
    fi
    return
  fi
  if [ -z "$value" ]; then
    echo "<missing>"
    return
  fi
  echo "$value"
}

audit_expected_value() {
  local env_json="$1"
  local service="$2"
  local key="$3"
  local expected="$4"
  local actual

  if [ "$expected" = "<present>" ]; then
    actual="$(render_env_raw_value "$env_json" "$key")"
    record_audit_row "$service" "${key}=<present>"
    if [ -n "$actual" ]; then
      echo "ok ${service}:${key}=<present>"
      return
    fi
    echo "drift ${service}:${key} expected=<present> actual=<missing-or-empty>"
    record_audit_failure "$service"
    return
  fi

  actual="$(render_env_status_value "$env_json" "$key")"
  record_audit_row "$service" "${key}=${actual}"
  if [ "$actual" = "$expected" ]; then
    echo "ok ${service}:${key}=${actual}"
    return
  fi

  echo "drift ${service}:${key} expected=${expected} actual=${actual}"
  record_audit_failure "$service"
}

audit_render_service_config() {
  local env_json="$1"
  local service="$2"
  shift 2

  local pair key expected
  for pair in "$@"; do
    key="${pair%%=*}"
    expected="${pair#*=}"
    audit_expected_value "$env_json" "$service" "$key" "$expected"
  done
}

audit_forbidden_render_env_keys() {
  local env_json="$1"
  local service="$2"
  shift 2

  local key
  for key in "$@"; do
    if render_env_has_key "$env_json" "$key"; then
      record_audit_row "$service" "${key}=<forbidden>"
      echo "forbidden ${service}:${key} forbidden_legacy_env"
      record_audit_failure "$service"
    fi
  done
}

audit_unexpected_render_env_keys() {
  local env_json="$1"
  local service="$2"
  shift 2

  local key
  while IFS= read -r key; do
    if [ -z "$key" ]; then
      continue
    fi
    if list_contains "$key" "${ARGUS_FORBIDDEN_LEGACY_ENV[@]}"; then
      continue
    fi
    if list_contains "$key" "$@"; then
      continue
    fi
    record_audit_row "$service" "${key}=<unexpected>"
    echo "forbidden ${service}:${key} unexpected_live_env"
    record_audit_failure "$service"
  done < <(render_env_keys "$env_json")
}

manifest_expected_pairs() {
  local surface="$1"
  local key

  manifest_env_pairs "$surface"

  while IFS= read -r key; do
    [ -n "$key" ] || continue
    if is_secret_render_env_key "$key"; then
      printf '%s=<redacted-present>\n' "$key"
    else
      printf '%s=<present>\n' "$key"
    fi
  done < <(manifest_required_present "$surface")
}

fingerprint_rows() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf "%s\n" "$@" | LC_ALL=C sort | sha256sum | awk '{print $1}'
    return
  fi
  printf "%s\n" "$@" | LC_ALL=C sort | shasum -a 256 | awk '{print $1}'
}

render_env_fingerprint() {
  fingerprint_rows "${AUDIT_FINGERPRINT_ROWS[@]}"
}

autodeploy_fingerprint() {
  fingerprint_rows "${AUTODEPLOY_AUDIT_FINGERPRINT_ROWS[@]}"
}

audit_render_auto_deploy_trigger() {
  local config_json="$1"
  local service_name="$2"
  local expected="$3"
  local actual

  actual="$(
    jq -r \
      '.autoDeployTrigger // .service.autoDeployTrigger // "<missing>"' \
      <<< "$config_json"
  )"
  AUTODEPLOY_AUDIT_FINGERPRINT_ROWS+=(
    "${service_name}:autoDeployTrigger=${actual}"
  )
  if [ "$actual" = "$expected" ]; then
    echo "ok ${service_name}:autoDeployTrigger=${actual}"
    return 0
  fi
  echo "drift ${service_name}:autoDeployTrigger expected=${expected} actual=${actual}"
  AUDIT_FAILURES=$((AUDIT_FAILURES + 1))
  AUTODEPLOY_AUDIT_FAILURES=$((AUTODEPLOY_AUDIT_FAILURES + 1))
}

audit_release_config() {
  local expected_mode=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --expect-mode)
        expected_mode="${2:-}"
        if [ -z "$expected_mode" ]; then
          echo "--expect-mode requires a value."
          return 2
        fi
        shift 2
        ;;
      *)
        echo "Unknown release-config-audit argument: $1"
        return 2
        ;;
    esac
  done
  if [ -z "$expected_mode" ]; then
    echo "release-config-audit requires --expect-mode <safe-off|proof-shadow>."
    return 2
  fi
  case "$expected_mode" in
    safe-off|proof-shadow)
      ;;
    *)
      echo "Unknown expected API mode: $expected_mode"
      return 2
      ;;
  esac

  require_local_env RENDER_API_KEY
  local profile_status
  if ! profile_status="$(release_profile_validate)"; then
    echo "release_profile_status=drift"
    echo "release_profile_error=${profile_status:-validation_failed}"
    return 1
  fi
  RELEASE_PROFILE_HASH="$(release_profile_hash)"
  AUDIT_FAILURES=0
  AUDIT_FINGERPRINT_ROWS=()
  AUTODEPLOY_AUDIT_FAILURES=0
  AUTODEPLOY_AUDIT_FINGERPRINT_ROWS=()

  local api_env_json web_env_json fingerprint
  local api_service_json web_service_json autodeploy_fingerprint_value
  local api_autodeploy_trigger web_autodeploy_trigger
  local mode_pair
  local api_profile_pairs=()
  local web_profile_pairs=()
  local api_allowed_keys=()
  local web_allowed_keys=()
  while IFS= read -r mode_pair; do
    api_profile_pairs+=("$mode_pair")
  done < <(manifest_expected_pairs api "$expected_mode")
  while IFS= read -r mode_pair; do
    web_profile_pairs+=("$mode_pair")
  done < <(manifest_expected_pairs marketing "$expected_mode")
  while IFS= read -r mode_pair; do
    api_allowed_keys+=("$mode_pair")
  done < <(manifest_allowed_keys api)
  while IFS= read -r mode_pair; do
    web_allowed_keys+=("$mode_pair")
  done < <(manifest_allowed_keys marketing)
  api_env_json="$(render_env_json "$API_SERVICE_ID")"
  web_env_json="$(render_env_json "$WEB_SERVICE_ID")"
  api_service_json="$(render_service_json "$API_SERVICE_ID")"
  web_service_json="$(render_service_json "$WEB_SERVICE_ID")"
  api_autodeploy_trigger="$(release_profile_auto_deploy_trigger api)"
  web_autodeploy_trigger="$(release_profile_auto_deploy_trigger marketing)"
  echo "Argus release config audit"
  echo "expected_mode=$expected_mode"
  echo "release_profile_status=ready"
  echo "release_profile_hash=$RELEASE_PROFILE_HASH"
  audit_forbidden_render_env_keys "$api_env_json" "cuadrao-api" "${ARGUS_FORBIDDEN_LEGACY_ENV[@]}"
  audit_forbidden_render_env_keys "$web_env_json" "cuadrao-marketing" "${ARGUS_FORBIDDEN_LEGACY_ENV[@]}"
  audit_unexpected_render_env_keys "$api_env_json" "cuadrao-api" "${api_allowed_keys[@]}"
  audit_unexpected_render_env_keys "$web_env_json" "cuadrao-marketing" "${web_allowed_keys[@]}"
  audit_render_service_config "$api_env_json" "cuadrao-api" "${api_profile_pairs[@]}"
  audit_render_service_config "$web_env_json" "cuadrao-marketing" "${web_profile_pairs[@]}"
  audit_render_auto_deploy_trigger \
    "$api_service_json" \
    "cuadrao-api" \
    "$api_autodeploy_trigger"
  audit_render_auto_deploy_trigger \
    "$web_service_json" \
    "cuadrao-marketing" \
    "$web_autodeploy_trigger"
  fingerprint="$(render_env_fingerprint)"
  autodeploy_fingerprint_value="$(autodeploy_fingerprint)"
  echo "env_fingerprint=$fingerprint"
  echo "autodeploy_fingerprint=$autodeploy_fingerprint_value"
  if [ "$AUTODEPLOY_AUDIT_FAILURES" -eq 0 ]; then
    echo "autodeploy_status=ready"
  else
    echo "autodeploy_status=drift"
  fi
  if [ "$AUDIT_FAILURES" -eq 0 ]; then
    echo "status=ready"
    return 0
  fi
  echo "status=drift"
  return 1
}

sync_api_proof_shadow_on() {
  echo "This mode has no app-managed hosted settings in the approved profile." >&2
  return 2
}

sync_api_real_workflow_on() {
  echo "This mode has no app-managed hosted settings in the approved profile." >&2
  return 2
}

sync_api_safe_off() {
  echo "This mode has no app-managed hosted settings in the approved profile." >&2
  return 2
}

sync_api_runtime() {
  require_local_env RENDER_API_KEY
  local update_payload

  update_payload="$(
    jq -nc \
      --arg build_command "$ARGUS_RENDER_API_BUILD_COMMAND" \
      --arg start_command "$ARGUS_RENDER_API_START_COMMAND" \
      '{
        serviceDetails: {
          envSpecificDetails: {
            buildCommand: $build_command,
            startCommand: $start_command
          },
          healthCheckPath: "/health"
        }
      }'
  )"

  curl -fsS \
    --request PATCH \
    --url "https://api.render.com/v1/services/${API_SERVICE_ID}" \
    --header "Authorization: Bearer ${RENDER_API_KEY}" \
    --header "Accept: application/json" \
    --header "Content-Type: application/json" \
    --data "$update_payload" \
    >/dev/null
  echo "synced ${API_SERVICE_ID}:api-runtime"
}

command="${1:-}"
case "$command" in
  api-status)
    print_api_status
    ;;
  api-deploy-status)
    print_api_deploy_status
    ;;
  web-deploy-status)
    print_web_deploy_status
    ;;
  api-safe-off)
    sync_api_safe_off
    ;;
  api-proof-shadow-on)
    sync_api_proof_shadow_on
    ;;
  api-real-workflow-on)
    sync_api_real_workflow_on
    ;;
  api-runtime)
    sync_api_runtime
    ;;
  release-config-audit)
    shift
    audit_release_config "$@"
    ;;
  api-dispatch-on)
    echo "api-dispatch-on is an alias for api-proof-shadow-on"
    sync_api_proof_shadow_on
    ;;
  api-dispatch-off)
    echo "api-dispatch-off is an alias for api-safe-off"
    sync_api_safe_off
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
