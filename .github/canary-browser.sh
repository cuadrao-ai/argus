#!/bin/bash
# Authenticated browser checks for the private-alpha canary.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/argus-env.sh"
argus_load_root_env >/dev/null || true

RELEASE_PROFILE_TOOL="$SCRIPT_DIR/private-alpha-release-profile.py"
APP_URL="${ARGUS_CANARY_APP_URL:-$ARGUS_PRIVATE_LAUNCH_APP_URL}"
CHECKS_HANDOFF="${ARGUS_CANARY_BROWSER_CHECKS_HANDOFF:-}"
BROWSER_CHECKS="${ARGUS_CANARY_BROWSER_CHECKS:-}"
STORAGE_STATE="${ARGUS_CANARY_BROWSER_STORAGE_STATE:-}"
USER_ID="${ARGUS_CANARY_BROWSER_USER_ID:-}"
ARTIFACT_PROBE="${ARGUS_CANARY_BROWSER_ARTIFACT_PROBE:-none}"
REDACTION_PROBE_VALUE="${ARGUS_CANARY_BROWSER_REDACTION_PROBE_VALUE:-}"

if ! python3 "$RELEASE_PROFILE_TOOL" validate >/dev/null; then
  echo "ERROR: checked-in release profile is invalid."
  exit 1
fi
if [ -z "$STORAGE_STATE" ] || [ ! -f "$STORAGE_STATE" ]; then
  echo "ERROR: private authenticated browser storage state is required."
  exit 1
fi
if [ -z "$CHECKS_HANDOFF" ] || [ ! -f "$CHECKS_HANDOFF" ]; then
  echo "ERROR: private browser check handoff file is required."
  exit 1
fi
if [ -z "$USER_ID" ]; then
  echo "ERROR: expected canary user identity is required."
  exit 1
fi
if [ -z "$BROWSER_CHECKS" ]; then
  echo "ERROR: the browser checks from the release profile are required."
  exit 1
fi
case "$ARTIFACT_PROBE" in
  none|redacted|unredacted) ;;
  *)
    echo "ERROR: browser artifact probe is invalid."
    exit 1
    ;;
esac
if [ "$ARTIFACT_PROBE" != "none" ] && [ -z "$REDACTION_PROBE_VALUE" ]; then
  echo "ERROR: browser artifact probe value is required."
  exit 1
fi
if [ ! -d web/node_modules/@playwright ]; then
  echo "ERROR: Playwright dependencies are missing; run bun install in web first."
  exit 1
fi

CANARY_LANGUAGE="$(python3 "$RELEASE_PROFILE_TOOL" canary-value language)"
CANARY_STATIC_LABELS="$(python3 "$RELEASE_PROFILE_TOOL" static-key-values "$CANARY_LANGUAGE")"
CANARY_CHAT_PROMPT="$(python3 "$RELEASE_PROFILE_TOOL" canary-value chat_prompt)"
CANARY_BACKTEST_PROMPT="$(python3 "$RELEASE_PROFILE_TOOL" canary-value backtest_prompt)"
CANARY_RESEARCH_PROMPT="$(python3 "$RELEASE_PROFILE_TOOL" canary-value research_prompt)"

echo "Running authenticated browser canary checks"
cd web
env -u CUADRAO_OPS_TOKEN \
  -u ARGUS_WORKFLOW_DATABASE_URL \
  -u RENDER_API_KEY \
  -u SUPABASE_SERVICE_ROLE_KEY \
  -u ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY \
  ARGUS_CANARY_BROWSER_STORAGE_STATE="$STORAGE_STATE" \
  ARGUS_CANARY_BROWSER_USER_ID="$USER_ID" \
  ARGUS_CANARY_BROWSER_CHECKS="$BROWSER_CHECKS" \
  ARGUS_CANARY_BROWSER_CHECKS_HANDOFF="$CHECKS_HANDOFF" \
  ARGUS_CANARY_STATIC_LABELS_JSON="$CANARY_STATIC_LABELS" \
  ARGUS_CANARY_BROWSER_CHAT_PROMPT="$CANARY_CHAT_PROMPT" \
  ARGUS_CANARY_BROWSER_BACKTEST_PROMPT="$CANARY_BACKTEST_PROMPT" \
  ARGUS_CANARY_BROWSER_RESEARCH_PROMPT="$CANARY_RESEARCH_PROMPT" \
  ARGUS_CANARY_BROWSER_ARTIFACT_PROBE="$ARTIFACT_PROBE" \
  ARGUS_CANARY_BROWSER_REDACTION_PROBE_VALUE="$REDACTION_PROBE_VALUE" \
  PLAYWRIGHT_BASE_URL="$APP_URL" \
  bunx playwright test e2e/private-alpha-release-canary.spec.ts --project=chromium
