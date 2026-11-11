#!/usr/bin/env bash
set -euo pipefail
root=$(git rev-parse --show-toplevel)
cd "$root"
evidence=docs/reports/evidence/production-reset
url=postgresql://postgres:postgres@127.0.0.1:59612/postgres
excluded=studio,postgres-meta,realtime,imgproxy,edge-runtime,mailpit,logflare,vector,supavisor

start() {
  python3 - <<'PY'
from pathlib import Path
import re
root = Path.cwd()
for name, prefix, source in [('history', '5961', 'migrations_archive'), ('baseline', '5962', 'migrations')]:
    stack = root / 'temp' / name / 'supabase'
    if stack.exists():
        raise SystemExit(f'Refusing existing scratch: {stack}')
    (stack / 'migrations').mkdir(parents=True)
    config = (root / 'supabase/config.toml').read_text()
    config = re.sub(r'^project_id = .*$', f'project_id = "cuadrao-reset-{name}"', config, flags=re.M)
    config = re.sub(r'= 5433([0-9])$', rf'= {prefix}\1', config, flags=re.M)
    config = re.sub(r'^inspector_port = .*$', f'inspector_port = {prefix}8', config, flags=re.M)
    (stack / 'config.toml').write_text(config)
    for sql in (root / 'supabase' / source).glob('*.sql'):
        (stack / 'migrations' / sql.name).write_bytes(sql.read_bytes())
    (stack / 'seed.sql').write_bytes((root / 'supabase/seed.sql').read_bytes())
PY
  for name in history baseline; do
    supabase start --workdir "temp/$name" -x "$excluded" > "temp/$name/start.log" 2>&1
  done
  poetry run python "$evidence/fixtures.py" seed > "$evidence/fixtures.log" 2>&1
}

apply() {
  ARGUS_APPLY_DATABASE_URL=$url poetry run python scripts/ops/apply_approved_migrations.py \
    --candidate-sha "$(git rev-parse HEAD)" \
    --approved-file docs/release-manifests/2026-11-10-production-baseline-versions.json \
    --allow-host 127.0.0.1 --allow-database postgres "$@"
}

proof() {
  poetry run python "$evidence/reference.py" > "$evidence/reference.log" 2>&1
  psql "$url" -X -v ON_ERROR_STOP=1 -f scripts/ops/production_reset/inventory.sql > "$evidence/inventory.log" 2>&1
  poetry run python "$evidence/controls.py" > "$evidence/controls.log" 2>&1
  poetry run python "$evidence/fixtures.py" empty >> "$evidence/fixtures.log" 2>&1
  poetry run python "$evidence/dependencies.py" >> "$evidence/controls.log" 2>&1
  psql "$url" -X -v ON_ERROR_STOP=1 -f scripts/ops/production_reset/reset.sql > "$evidence/reset.log" 2>&1
  apply > "$evidence/dry-run.log" 2>&1
  apply --execute > "$evidence/apply.log" 2>&1
  psql "$url" -X -v ON_ERROR_STOP=1 -f scripts/ops/production_reset/verify.sql > "$evidence/verify.log" 2>&1
  psql "$url" -Xq -v ON_ERROR_STOP=1 -f supabase/seed.sql
  poetry run python docs/reports/evidence/1890-baseline/gate_on_reset.py "$url" > "$evidence/gate.log" 2>&1
  poetry run python docs/reports/evidence/1890-baseline/schema_diff.py \
    supabase_db_cuadrao-reset-history supabase_db_cuadrao-reset-baseline temp/reset-diff > "$evidence/diff.log" 2>&1
  cp temp/reset-diff/schema.diff "$evidence/schema.diff"
}

suite() {
  psql "$url" -X -v ON_ERROR_STOP=1 -f supabase/tests/net-client-grants.sql > "$evidence/net-client-grants.log" 2>&1
  ARGUS_DISPOSABLE_DATABASE_URL=$url OPENROUTER_API_KEY= ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture \
    poetry run python "$evidence/postgres_suite.py" > "$evidence/postgres-tests.log" 2>&1
}

stop() {
  for name in history baseline; do
    supabase stop --workdir "temp/$name" --no-backup
  done
}

case "${1:-all}" in
  start) start ;;
  proof) proof ;;
  test) suite ;;
  stop) stop ;;
  all) trap stop EXIT; start; proof; suite ;;
  *) exit 2 ;;
esac
