#!/bin/bash
# Resolve an explicitly selected local store without shared checkout links.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command=(python3 "$SCRIPT_DIR/../scripts/ops/staging_env.py" local)
while [ "$#" -gt 0 ]; do
  case "$1" in
    --check|--replace) command+=("$1"); shift ;;
    *) break ;;
  esac
done
TARGET_ROOT="${1:-$(git rev-parse --show-toplevel)}"
exec "${command[@]}" "$TARGET_ROOT"
