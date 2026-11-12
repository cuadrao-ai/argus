#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# shellcheck disable=SC1091
source .github/argus-env.sh

run_python() {
  if [ -n "${ARGUS_WORKFLOW_PYTHON:-}" ]; then
    "$ARGUS_WORKFLOW_PYTHON" "$@"
    return
  fi

  poetry run python "$@"
}

usage() {
  cat <<'USAGE'
Usage:
  .github/workflow-proof.sh seed [--user-id <uuid>] [--nonce <value>]
  .github/workflow-proof.sh direct --job-id <uuid> --nonce <value>
  .github/workflow-proof.sh verify --job-id <uuid> [--expect-nonce <value>] [--expect-provider-mode <mode>]

Seed reuses a stable proof auth/profile by default. A proof job carries
operation_scope=workflows.proof and no conversation, so it never reads as
conversation activity.
Use an explicit --user-id only against an isolated local or preview Supabase database.

Local Render validation:
  1. poetry install --only main,workflows --no-interaction
  2. render workflows dev -- poetry run python workflows/main.py

This helper runs workflow Python entry points through `poetry run python` by default.
Set ARGUS_WORKFLOW_PYTHON=/path/to/python only when using a prebuilt workflow venv.

Remote validation requires:
  RENDER_API_KEY
  ARGUS_RENDER_WORKFLOW_PROOF_TASK={workflow-slug}/workflow_proof
  ARGUS_WORKFLOW_DATABASE_URL=<Supabase transaction pooler URL>

Future Render Workflow service settings:
  Root Directory: .
  Build Command: pip install poetry && poetry config virtualenvs.create false && poetry install --only main,workflows --no-interaction
  Start Command: poetry run python workflows/main.py

All modes that touch Supabase require ARGUS_WORKFLOW_DATABASE_URL as a secret.
DATABASE_URL is accepted only as a local/backward-compatible fallback.
USAGE
}

command="${1:-}"
if [ -z "$command" ]; then
  usage
  exit 2
fi
shift

case "$command" in
  seed)
    run_python workflows/proof.py seed "$@"
    ;;
  direct)
    run_python workflows/proof.py direct "$@"
    ;;
  verify)
    run_python workflows/proof.py verify "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
