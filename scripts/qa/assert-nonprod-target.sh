#!/bin/bash
# Parse effective targets and require exact loopback or approved host names.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$ROOT_DIR/scripts/ops/staging_env.py" guard-local "$ROOT_DIR"
