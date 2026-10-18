#!/bin/bash
# Resolve the coherent production SHA while preserving branch harness proof.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

: "${RENDER_API_KEY:?RENDER_API_KEY is required}"
: "${GITHUB_ENV:?GITHUB_ENV is required}"

case "${GITHUB_EVENT_NAME:-}" in
  schedule|workflow_dispatch) ;;
  *)
    echo "ERROR: unsupported canary event." >&2
    exit 1
    ;;
esac

same_commit_failure() {
  echo "ERROR: canary failed at services_same_commit: $1" >&2
  exit 1
}

api_status="$(RENDER_API_KEY="$RENDER_API_KEY" "$SCRIPT_DIR/render-env-sync.sh" api-deploy-status)" \
  || same_commit_failure "api_deploy_status_failed"
web_status="$(RENDER_API_KEY="$RENDER_API_KEY" "$SCRIPT_DIR/render-env-sync.sh" web-deploy-status)" \
  || same_commit_failure "web_deploy_status_failed"
workflow_status="$(RENDER_API_KEY="$RENDER_API_KEY" "$SCRIPT_DIR/render-env-sync.sh" workflow-version-status)" \
  || same_commit_failure "workflow_version_status_failed"
# The resolver names services_same_commit and its reason on stderr.
deployed_sha="$(python3 "$SCRIPT_DIR/canary-deployed-sha.py" \
  --api-status "$api_status" \
  --web-status "$web_status" \
  --workflow-status "$workflow_status")"
web_sha="$(printf '%s\n' "$web_status" | sed -n 's/^commit=//p' | head -n 1)"
git cat-file -e "${deployed_sha}^{commit}"

harness_sha="$(git rev-parse HEAD)"
allow_harness_mismatch="false"
if [ "${GITHUB_EVENT_NAME}" = "schedule" ]; then
  git checkout --detach "$deployed_sha"
  harness_sha="$(git rev-parse HEAD)"
else
  allow_harness_mismatch="true"
fi

{
  echo "ARGUS_CANARY_SHA=$deployed_sha"
  echo "ARGUS_CANARY_HARNESS_SHA=$harness_sha"
  echo "ARGUS_CANARY_ALLOW_HARNESS_MISMATCH=$allow_harness_mismatch"
} >> "$GITHUB_ENV"

echo "canary_deployed_sha=$deployed_sha"
echo "canary_web_deploy_sha=$web_sha"
echo "canary_harness_sha=$harness_sha"
echo "canary_allow_harness_mismatch=$allow_harness_mismatch"
