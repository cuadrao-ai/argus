#!/usr/bin/env bash
# Build two throwaway local Supabase databases and compare them (#1890).
#   A: every file in supabase/migrations_archive/, inventoried, then the staging alignment through
#      scripts/ops/apply_approved_migrations.py (baseline recorded without running,
#      drop migration run).
#   B: supabase/migrations/ alone, the way every fresh database is built.
# Usage: docs/reports/evidence/1890-baseline/prove.sh <scratch-dir> [--keep]
# Local only: own project ids and ports 5981x and 5982x, never a hosted database.
set -euo pipefail
root=$(git rev-parse --show-toplevel)
scratch=$(mkdir -p "$1" && cd "$1" && pwd)
evidence="$root/docs/reports/evidence/1890-baseline"
excluded=studio,postgres-meta,realtime,imgproxy,edge-runtime,mailpit,logflare,vector,supavisor

stack() {  # name port-prefix migration-files...
  local dir="$scratch/$1" prefix=$2
  shift 2
  rm -rf "$dir" && mkdir -p "$dir/supabase/migrations"
  sed -e "s/^project_id = .*/project_id = \"cuadrao-1890-$(basename "$dir")\"/" \
      -e "s/= 5433\([0-9]\)\$/= $prefix\1/" -e "s/^inspector_port = .*/inspector_port = ${prefix}8/" \
      "$root/supabase/config.toml" > "$dir/supabase/config.toml"
  cp "$root/supabase/seed.sql" "$dir/supabase/seed.sql"
  cp "$@" "$dir/supabase/migrations/"
  supabase start --workdir "$dir" -x "$excluded" > "$dir/start.log" 2>&1
}

stack a 5981 "$root"/supabase/migrations_archive/*.sql
stack b 5982 "$root"/supabase/migrations/*_cuadrao_baseline.sql

# Inventory of the history, before alignment; git diff shows any drift from the committed one.
python3 "$evidence/inventory.py" postgresql://postgres:postgres@127.0.0.1:59812/postgres

versions=$(cd "$root/supabase/migrations" && ls ./*.sql | sed -E 's|^\./([0-9]{14})_.*|"\1"|' | paste -sd, -)
echo "[$versions]" > "$scratch/approved.json"
baseline=$(cd "$root/supabase/migrations" && ls ./*_cuadrao_baseline.sql | sed -E 's|^\./([0-9]{14})_.*|\1|')
(cd "$root" && ARGUS_APPLY_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:59812/postgres \
  poetry run python scripts/ops/apply_approved_migrations.py --candidate-sha "$(git rev-parse HEAD)" \
  --approved-file "$scratch/approved.json" --record-only "$baseline" \
  --allow-host 127.0.0.1 --allow-database postgres --execute)

# The diff must be exactly the committed one, whose every line explain_checks.py accounts for.
python3 "$evidence/schema_diff.py" supabase_db_cuadrao-1890-a supabase_db_cuadrao-1890-b "$scratch/diff" || true
status=0
cmp "$scratch/diff/schema.diff" "$evidence/schema.diff" || status=1
python3 "$evidence/explain_checks.py" supabase_db_cuadrao-1890-b "$scratch/diff/schema.diff" || status=1
for container in supabase_db_cuadrao-1890-a supabase_db_cuadrao-1890-b; do
  if docker exec -i "$container" psql -U postgres -d postgres -Xq -v ON_ERROR_STOP=1 \
    < "$root/supabase/tests/net-client-grants.sql" > /dev/null 2>&1; then
    echo "$container: net-client-grants probe passed"
  else
    echo "$container: net-client-grants probe FAILED" && status=1
  fi
done

if [ "${2:-}" != "--keep" ]; then
  supabase stop --workdir "$scratch/a" --no-backup > /dev/null
  supabase stop --workdir "$scratch/b" --no-backup > /dev/null
fi
exit "$status"
