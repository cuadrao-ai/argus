#!/bin/bash
# Use the manifest resolver for a disposable local stack. Never source discovery.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
supabase status -o env | python3 "$ROOT_DIR/scripts/ops/staging_env.py" local "$ROOT_DIR" --stack "$@"
bash "$ROOT_DIR/scripts/qa/assert-nonprod-target.sh"
