#!/bin/bash
# Shared Argus environment contract for local mode scripts and Render drift tests.

ARGUS_PRIVATE_LAUNCH_APP_URL="https://arguschat.ai"
ARGUS_PRIVATE_LAUNCH_API_URL="https://api.arguschat.ai"
ARGUS_PRIVATE_LAUNCH_API_SERVICE_ID="srv-d78tanmuk2gs73e17nn0"
ARGUS_PRIVATE_LAUNCH_WEB_SERVICE_ID="srv-d7ap6bmslomc73eqp8m0"
ARGUS_RENDER_BACKTESTS_WORKFLOW_ID="wfl-d8hpsmuq1p3s73duv3q0"
ARGUS_BACKTEST_WORKFLOW_TASK_DEFAULT="argus-backtests/workflow_proof"
ARGUS_BACKTEST_REAL_WORKFLOW_TASK_DEFAULT="argus-backtests/run_backtest_job"
ARGUS_RENDER_POETRY_VERSION="2.1.3"
ARGUS_RENDER_API_BUILD_COMMAND="poetry config virtualenvs.create false && poetry install --only main --no-interaction"
ARGUS_RENDER_API_START_COMMAND="poetry run uvicorn argus.api.main:app --host 0.0.0.0 --port \$PORT"
ARGUS_RENDER_WORKFLOW_BUILD_COMMAND="poetry config virtualenvs.create false && poetry install --only main,workflows --no-interaction"
ARGUS_RENDER_WORKFLOW_START_COMMAND="poetry run python workflows/main.py"

ARGUS_QA_REQUIRED_ENV=(
  SUPABASE_PROJECT_URL
  SUPABASE_ANON_PUBLIC_KEY
  SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_JWT_SECRET
  SUPABASE_POSTGRES_SESSION_POOLER_URL
  ALPACA_API_KEY
  ALPACA_SECRET_KEY
  OPENROUTER_API_KEY
  CUADRAO_UTILITY_MODEL
  CUADRAO_UTILITY_FALLBACK_MODEL
  CUADRAO_CHAT_MODEL
  CUADRAO_CHAT_FALLBACK_MODEL
  CUADRAO_STRUCTURED_MODEL
  CUADRAO_STRUCTURED_FALLBACK_MODEL
  CUADRAO_CONTEXT_MODEL
  CUADRAO_CONTEXT_FALLBACK_MODEL
  CUADRAO_READOUT_MODEL
  CUADRAO_READOUT_FALLBACK_MODEL
)

ARGUS_RENDER_API_ENV_KEYS="$(python3 "${BASH_SOURCE[0]%/*}/private-alpha-release-profile.py" allowed-keys api)" || exit 1
ARGUS_RENDER_API_ENV=()
while IFS= read -r argus_api_env_key; do
  ARGUS_RENDER_API_ENV+=("$argus_api_env_key")
done <<< "$ARGUS_RENDER_API_ENV_KEYS"
unset ARGUS_RENDER_API_ENV_KEYS argus_api_env_key

if ! _argus_web_env_keys="$(python3 "$(dirname "${BASH_SOURCE[0]}")/private-alpha-release-profile.py" allowed-keys web)" || [ -z "$_argus_web_env_keys" ]; then
  echo "Cannot load web environment keys from the release profile." >&2
  exit 1
fi
ARGUS_RENDER_WEB_ENV=()
while IFS= read -r _argus_web_env_key; do
  ARGUS_RENDER_WEB_ENV+=("$_argus_web_env_key")
done <<< "$_argus_web_env_keys"
unset _argus_web_env_keys _argus_web_env_key

if ! _workflow_keys="$(python3 "${BASH_SOURCE[0]%/*}/private-alpha-release-profile.py" allowed-keys workflow)"; then
  exit 1
fi
ARGUS_RENDER_WORKFLOW_PROOF_ENV=()
while IFS= read -r key; do
  [ -n "$key" ] && ARGUS_RENDER_WORKFLOW_PROOF_ENV+=("$key")
done <<< "$_workflow_keys"
unset _workflow_keys key

ARGUS_FORBIDDEN_LEGACY_ENV=(
  NEXT_PUBLIC_API_URL
  NEXT_PUBLIC_MOCK_API
  AGENT_MODEL
  AGENT_FALLBACK_MODEL
)

argus_load_root_env() {
  if [ -f .env ]; then
    set -a
    set +u
    # shellcheck disable=SC1091
    source .env
    set -u
    set +a
    return 0
  fi
  return 1
}

argus_require_env() {
  local name="$1"
  local value
  local had_nounset=0

  case "$-" in
    *u*)
      had_nounset=1
      set +u
      ;;
  esac
  value="${!name}"
  if [ "$had_nounset" -eq 1 ]; then
    set -u
  fi

  if [ -z "$value" ] || [[ "$value" == YOUR_* ]] || [[ "$value" == your_* ]]; then
    echo "❌ $name is required."
    exit 1
  fi
}

argus_require_qa_env() {
  local name
  for name in "${ARGUS_QA_REQUIRED_ENV[@]}"; do
    argus_require_env "$name"
  done
}

argus_export_dev_mode() {
  export CUADRAO_PERSISTENCE_MODE=memory
  export ARGUS_DEV_MEMORY_FALLBACK=true
  export ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture
  export CUADRAO_CHECKPOINTER_MODE=memory
  export CUADRAO_MOCK_AUTH=true
  export ENABLE_MARKET_DATA_CACHE=false
  export ARGUS_BACKTEST_JOBS_SHADOW_ENABLED=false
  export ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED=false
  export ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=false
  export ARGUS_BACKTEST_WORKFLOW_TASK="$ARGUS_BACKTEST_WORKFLOW_TASK_DEFAULT"
  export ARGUS_BACKTEST_REAL_WORKFLOW_TASK="$ARGUS_BACKTEST_REAL_WORKFLOW_TASK_DEFAULT"
  export ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT=1
  export ARGUS_BACKTEST_JOBS_USER_QUEUED_LIMIT=2
  export ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT=5
  export ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT=10
  export ARGUS_CONTEXT_PACKETS_ENABLED=false
  unset DATABASE_URL
}

argus_export_qa_mode() {
  export CUADRAO_PERSISTENCE_MODE=supabase
  export ARGUS_DEV_MEMORY_FALLBACK=false
  export ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider
  export CUADRAO_CHECKPOINTER_MODE=postgres
  export CUADRAO_MOCK_AUTH=false
  export ARGUS_BACKTEST_JOBS_SHADOW_ENABLED="${ARGUS_BACKTEST_JOBS_SHADOW_ENABLED:-false}"
  export ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED="${ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED:-false}"
  export ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED="${ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED:-false}"
  export ARGUS_BACKTEST_WORKFLOW_TASK="${ARGUS_BACKTEST_WORKFLOW_TASK:-$ARGUS_BACKTEST_WORKFLOW_TASK_DEFAULT}"
  export ARGUS_BACKTEST_REAL_WORKFLOW_TASK="${ARGUS_BACKTEST_REAL_WORKFLOW_TASK:-$ARGUS_BACKTEST_REAL_WORKFLOW_TASK_DEFAULT}"
  export ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT="${ARGUS_BACKTEST_JOBS_USER_RUNNING_LIMIT:-1}"
  export ARGUS_BACKTEST_JOBS_USER_QUEUED_LIMIT="${ARGUS_BACKTEST_JOBS_USER_QUEUED_LIMIT:-2}"
  export ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT="${ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT:-5}"
  export ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT="${ARGUS_BACKTEST_JOBS_GLOBAL_QUEUED_LIMIT:-10}"
  export ARGUS_CONTEXT_PACKETS_ENABLED="${ARGUS_CONTEXT_PACKETS_ENABLED:-true}"
  export DATABASE_URL="$SUPABASE_POSTGRES_SESSION_POOLER_URL"
}
