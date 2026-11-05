#!/bin/bash
# Exact-head, local-only Block 4 guest browser QA.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

mode="${1:-}"
case "$mode" in
  list|preflight|entry|continuation|authoritative) ;;
  *)
    echo "usage: scripts/qa/run-guest-experience-qa.sh list|preflight|entry|continuation|authoritative" >&2
    exit 2
    ;;
esac
shift

actual_root="$(git rev-parse --show-toplevel)"
[ "$actual_root" = "$ROOT_DIR" ] || {
  echo "guest QA refused: script root does not match repository root" >&2
  exit 1
}
candidate_sha="$(git rev-parse HEAD)"
expected_candidate_sha="${ARGUS_EXPECTED_CANDIDATE_SHA:-$candidate_sha}"
[ "$candidate_sha" = "$expected_candidate_sha" ] || {
  echo "guest QA refused: HEAD does not match ARGUS_EXPECTED_CANDIDATE_SHA" >&2
  exit 1
}

status="$(git status --porcelain)"
if [ -n "$status" ]; then
  if [ "$mode" = "authoritative" ]; then
    echo "guest QA refused: authoritative run requires a clean worktree" >&2
    exit 1
  fi
  invalid_path="$(
    git status --porcelain |
      sed -E 's/^.. //' |
      grep -Ev '^(\.github/workflows/ci\.yml$|tests/test_ci_workflow\.py$|scripts/qa/assert_pytest_gate\.py$|scripts/qa/README\.md$|scripts/qa/run-guest-experience-qa\.sh$|web/e2e/|web/lib/guest-session\.ts$|web/__tests__/guest-browser-harness\.test\.ts$|web/__tests__/guest-session\.test\.ts$)' |
      head -1 || true
  )"
  [ -z "$invalid_path" ] || {
    echo "guest QA refused: preflight contains a non-harness change" >&2
    exit 1
  }
  export ARGUS_GUEST_QA_ALLOW_TEST_DIFF=true
else
  unset ARGUS_GUEST_QA_ALLOW_TEST_DIFF || true
fi

# Durable preflight captures write the first language artifact before the
# second language assertion runs. That expected evidence write must not make
# the second assertion reject the otherwise pinned candidate as dirty.
if [ "${ARGUS_GUEST_QA_CAPTURE_DURABLE_EVIDENCE:-}" = "true" ]; then
  export ARGUS_GUEST_QA_ALLOW_TEST_DIFF=true
fi

export ARGUS_CANDIDATE_SHA="$candidate_sha"
unset ARGUS_QA_APPROVED_SUPABASE_REF || true

app_port="${ARGUS_GUEST_QA_APP_PORT:-3000}"
api_port="${ARGUS_GUEST_QA_API_PORT:-8000}"
database_container="${ARGUS_GUEST_QA_DB_CONTAINER:-supabase_db_argus-qa}"
supabase_workdir="${ARGUS_GUEST_QA_SUPABASE_WORKDIR:-$ROOT_DIR}"
for port_name in app_port api_port; do
  port_value="${!port_name}"
  case "$port_value" in
    ''|*[!0-9]*)
      echo "guest QA refused: $port_name must be an integer port" >&2
      exit 1
      ;;
  esac
  if [ "$port_value" -lt 1 ] || [ "$port_value" -gt 65535 ]; then
    echo "guest QA refused: $port_name must be between 1 and 65535" >&2
    exit 1
  fi
done
[ "$app_port" != "$api_port" ] || {
  echo "guest QA refused: app and API ports must be different" >&2
  exit 1
}
case "$database_container" in
  supabase_db_[A-Za-z0-9]*)
    case "$database_container" in *[!A-Za-z0-9_-]*)
      echo "guest QA refused: unsafe database container name" >&2
      exit 1
    esac
    ;;
  *)
    echo "guest QA refused: unsafe database container name" >&2
    exit 1
    ;;
esac
[ -d "$supabase_workdir" ] || {
  echo "guest QA refused: Supabase workdir does not exist" >&2
  exit 1
}
[ -f "$supabase_workdir/supabase/config.toml" ] || {
  echo "guest QA refused: Supabase workdir has no supabase/config.toml" >&2
  exit 1
}
supabase_project_id="$(
  sed -n 's/^project_id = "\([^"]*\)"/\1/p' \
    "$supabase_workdir/supabase/config.toml" |
    head -1
)"
[ -n "$supabase_project_id" ] || {
  echo "guest QA refused: Supabase project_id is missing" >&2
  exit 1
}
[ "$database_container" = "supabase_db_$supabase_project_id" ] || {
  echo "guest QA refused: database container does not match Supabase workdir" >&2
  exit 1
}
container_identity="$(
  docker inspect \
    -f '{{ index .Config.Labels "com.supabase.cli.project" }}|{{.State.Running}}' \
    "$database_container" 2>/dev/null || true
)"
[ "$container_identity" = "$supabase_project_id|true" ] || {
  echo "guest QA refused: selected Supabase database is not the running workdir project" >&2
  exit 1
}
export ARGUS_GUEST_QA_APP_PORT="$app_port"
export ARGUS_GUEST_QA_API_PORT="$api_port"
export ARGUS_GUEST_QA_DB_CONTAINER="$database_container"
export ARGUS_GUEST_QA_SUPABASE_WORKDIR="$supabase_workdir"

# Load live provider/model credentials, then replace every database/Auth target
# with the disposable local Supabase stack before a service or browser starts.
# shellcheck disable=SC1091
source .github/argus-env.sh
argus_load_root_env
export ARGUS_GUEST_QA_APP_PORT="$app_port"
export ARGUS_GUEST_QA_API_PORT="$api_port"
export ARGUS_GUEST_QA_DB_CONTAINER="$database_container"
export ARGUS_GUEST_QA_SUPABASE_WORKDIR="$supabase_workdir"
eval "$(supabase status --workdir "$supabase_workdir" -o env)"

for required in API_URL ANON_KEY SERVICE_ROLE_KEY DB_URL JWT_SECRET; do
  value="${!required:-}"
  [ -n "$value" ] || {
    echo "guest QA refused: local Supabase did not provide $required" >&2
    exit 1
  }
done

case "$API_URL" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *)
    echo "guest QA refused: Supabase API is not loopback-local" >&2
    exit 1
    ;;
esac
case "$DB_URL" in
  postgresql://*@127.0.0.1:*/*|postgresql://*@localhost:*/*) ;;
  *)
    echo "guest QA refused: Supabase database is not loopback-local" >&2
    exit 1
    ;;
esac

export SUPABASE_PROJECT_URL="$API_URL"
export SUPABASE_URL="$API_URL"
export NEXT_PUBLIC_SUPABASE_URL="$API_URL"
export SUPABASE_ANON_PUBLIC_KEY="$ANON_KEY"
export SUPABASE_ANON_KEY="$ANON_KEY"
export NEXT_PUBLIC_SUPABASE_ANON_KEY="$ANON_KEY"
export SUPABASE_SERVICE_ROLE_KEY="$SERVICE_ROLE_KEY"
export SUPABASE_JWT_SECRET="$JWT_SECRET"
export SUPABASE_POSTGRES_SESSION_POOLER_URL="$DB_URL"
export SUPABASE_POSTGRES_DIRECT_URL="$DB_URL"
export SUPABASE_POSTGRES_TRANSACTION_POOLER_URL="$DB_URL"
export DATABASE_URL="$DB_URL"

export CUADRAO_PERSISTENCE_MODE=supabase
export ARGUS_DEV_MEMORY_FALLBACK=false
export ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider
export CUADRAO_CHECKPOINTER_MODE=postgres
export CUADRAO_MOCK_AUTH=false
export CUADRAO_GUEST_ACCESS_ENABLED=true
export CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=false
export CUADRAO_CORS_ALLOW_ORIGINS="http://localhost:$app_port"
export ARGUS_BACKTEST_JOBS_SHADOW_ENABLED=false
export ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED=false
export ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=false

export ARGUS_APP_ORIGIN="http://localhost:$app_port"
export PLAYWRIGHT_BASE_URL="http://localhost:$app_port"
export NEXT_PUBLIC_ARGUS_API_URL="http://localhost:$api_port/api/v1"
export NEXT_PUBLIC_MOCK_AUTH=false
export NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true
export NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN=argus-local-browser-qa
export NEXT_PUBLIC_ENABLE_SPANISH=true
export NEXT_PUBLIC_OMNISEARCH_ENABLED=true
export NEXT_PUBLIC_POSTHOG_KEY=
unset POSTHOG_PROJECT_TOKEN POSTHOG_REGION POSTHOG_HOST \
  CUADRAO_POSTHOG_TIMEOUT_SECONDS || true

if [ "$mode" != "list" ]; then
  command -v lsof >/dev/null || {
    echo "guest QA refused: lsof is required to prove ports are unused" >&2
    exit 1
  }
  for port_value in "$app_port" "$api_port"; do
    if lsof -nP -iTCP:"$port_value" -sTCP:LISTEN -t | grep -q .; then
      echo "guest QA refused: selected local port $port_value is already listening" >&2
      exit 1
    fi
  done
fi

build_frontend() {
  (cd web && bun run build)
}

if [ "$mode" = "authoritative" ]; then
  argus_require_qa_env
  export ARGUS_GUEST_QA_REQUIRE_ZERO_STATE=true
  unset ARGUS_GUEST_QA_ENTRY || true
  unset ARGUS_GUEST_QA_PREFLIGHT || true
  unset ARGUS_GUEST_QA_EVIDENCE_SEGMENT || true
  build_frontend
elif [ "$mode" = "continuation" ]; then
  export ARGUS_GUEST_QA_REQUIRE_ZERO_STATE=true
  export ARGUS_GUEST_QA_EVIDENCE_SEGMENT=provider-free-11-20
  unset ARGUS_GUEST_QA_ENTRY || true
  unset ARGUS_GUEST_QA_PREFLIGHT || true
  build_frontend
elif [ "$mode" = "entry" ]; then
  export ARGUS_GUEST_QA_ENTRY=true
  export ARGUS_GUEST_QA_REQUIRE_ZERO_STATE=false
  export NEXT_PUBLIC_MOCK_AUTH=true
  unset ARGUS_GUEST_QA_PREFLIGHT || true
  unset ARGUS_GUEST_QA_EVIDENCE_SEGMENT || true
  build_frontend
elif [ "$mode" = "preflight" ]; then
  export ARGUS_GUEST_QA_PREFLIGHT=true
  export ARGUS_GUEST_QA_REQUIRE_ZERO_STATE=false
  unset ARGUS_GUEST_QA_ENTRY || true
  unset ARGUS_GUEST_QA_EVIDENCE_SEGMENT || true
  build_frontend
else
  unset ARGUS_GUEST_QA_ENTRY || true
  unset ARGUS_GUEST_QA_PREFLIGHT || true
  unset ARGUS_GUEST_QA_EVIDENCE_SEGMENT || true
  export ARGUS_GUEST_QA_REQUIRE_ZERO_STATE=false
fi

cd web
exec bunx playwright test \
  --config=e2e/guest-experience.playwright.config.ts \
  --project=chromium \
  --workers=1 \
  "$@"
