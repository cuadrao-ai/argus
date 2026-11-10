#!/usr/bin/env bash
# Build three throwaway local Supabase databases and compare them (#1890).
#   A: every file in supabase/migrations_archive/, inventoried, then the staging alignment through
#      scripts/ops/apply_approved_migrations.py (baseline recorded without running,
#      drop migration run).
#   B: supabase/migrations/ alone, the way every fresh database is built.
#   C: the production reset (#1789): no migrations, the empty ledger table recreated by hand,
#      then both files from the committed tree through the apply tool, then the production gate.
# Usage: docs/reports/evidence/1890-baseline/prove.sh <scratch-dir> [--keep]
# Local only: own project ids and ports 5981x, 5982x and 5983x, never a hosted database.
set -euo pipefail
root=$(git rev-parse --show-toplevel)
scratch=$(mkdir -p "$1" && cd "$1" && pwd)
evidence="$root/docs/reports/evidence/1890-baseline"
excluded=studio,postgres-meta,realtime,imgproxy,edge-runtime,mailpit,logflare,vector,supavisor
a=supabase_db_cuadrao-1890-a
b=supabase_db_cuadrao-1890-b
c=supabase_db_cuadrao-1890-c
c_url=postgresql://postgres:postgres@127.0.0.1:59832/postgres

stack() {  # name port-prefix migration-files...
  local dir="$scratch/$1" prefix=$2
  shift 2
  rm -rf "$dir" && mkdir -p "$dir/supabase/migrations"
  sed -e "s/^project_id = .*/project_id = \"cuadrao-1890-$(basename "$dir")\"/" \
      -e "s/= 5433\([0-9]\)\$/= $prefix\1/" -e "s/^inspector_port = .*/inspector_port = ${prefix}8/" \
      "$root/supabase/config.toml" > "$dir/supabase/config.toml"
  # C has no migrations at start, so its seed waits until the apply tool built the tables.
  if [ $# -gt 0 ]; then cp "$@" "$dir/supabase/migrations/" && cp "$root/supabase/seed.sql" "$dir/supabase/seed.sql"; fi
  supabase start --workdir "$dir" -x "$excluded" > "$dir/start.log" 2>&1
}

apply() {  # database-url extra-args...
  local url=$1
  shift
  (cd "$root" && ARGUS_APPLY_DATABASE_URL=$url \
    poetry run python scripts/ops/apply_approved_migrations.py --candidate-sha "$(git rev-parse HEAD)" \
    --approved-file "$scratch/approved.json" --allow-host 127.0.0.1 --allow-database postgres "$@")
}

stack a 5981 "$root"/supabase/migrations_archive/*.sql
stack b 5982 "$root"/supabase/migrations/*_cuadrao_baseline.sql
stack c 5983

# Inventory of the history, before alignment; git diff shows any drift from the committed one.
python3 "$evidence/inventory.py" postgresql://postgres:postgres@127.0.0.1:59812/postgres

versions=$(cd "$root/supabase/migrations" && ls ./*.sql | sed -E 's|^\./([0-9]{14})_.*|"\1"|' | paste -sd, -)
echo "[$versions]" > "$scratch/approved.json"
baseline=$(cd "$root/supabase/migrations" && ls ./*_cuadrao_baseline.sql | sed -E 's|^\./([0-9]{14})_.*|\1|')
apply postgresql://postgres:postgres@127.0.0.1:59812/postgres --record-only "$baseline" --execute

# The diff must be exactly the committed one, whose every line explain_checks.py accounts for.
python3 "$evidence/schema_diff.py" "$a" "$b" "$scratch/diff" || true
status=0
cmp "$scratch/diff/schema.diff" "$evidence/schema.diff" || status=1
python3 "$evidence/explain_checks.py" "$b" "$scratch/diff/schema.diff" || status=1
for container in "$a" "$b"; do
  if docker exec -i "$container" psql -U postgres -d postgres -Xq -v ON_ERROR_STOP=1 \
    < "$root/supabase/tests/net-client-grants.sql" > /dev/null 2>&1; then
    echo "$container: net-client-grants probe passed"
  else
    echo "$container: net-client-grants probe FAILED" && status=1
  fi
done

# Production reset rehearsal on C: without the ledger table the tool must say so, not fail raw.
docker exec -i "$c" psql -U supabase_admin -d postgres -Xq -v ON_ERROR_STOP=1 \
  -c "drop table if exists supabase_migrations.schema_migrations" > /dev/null
if apply "$c_url" > "$scratch/c-no-ledger.log" 2>&1; then
  echo "C: the apply tool ran without a ledger table" && status=1
elif grep -q "supabase_migrations.schema_migrations is missing" "$scratch/c-no-ledger.log"; then
  echo "C: missing ledger table named plainly"
else
  echo "C: missing ledger table not named plainly" && cat "$scratch/c-no-ledger.log" && status=1
fi
# As postgres, the user the apply tool connects with, so it owns the ledger it writes.
psql "$c_url" -Xq -v ON_ERROR_STOP=1 -f "$evidence/reset_ledger.sql" > /dev/null
apply "$c_url" --execute
psql "$c_url" -Xq -v ON_ERROR_STOP=1 -f "$root/supabase/seed.sql" > /dev/null
(cd "$root" && poetry run python "$evidence/gate_on_reset.py" "$c_url") || status=1
python3 "$evidence/schema_diff.py" "$a" "$c" "$scratch/diff-c" || true
cmp "$scratch/diff-c/schema.diff" "$evidence/schema.diff" || status=1

# Known-bad changes on C must each show in the diff, including one that differs only by a carriage
# return. C takes them so B stays as built for the Postgres suite under --keep.
docker exec -i "$c" psql -U supabase_admin -d postgres -Xq -v ON_ERROR_STOP=1 \
  < "$evidence/diff_controls.sql" > /dev/null
python3 "$evidence/schema_diff.py" "$a" "$c" "$scratch/controls" || true
while IFS= read -r marker; do
  grep -qF -- "$marker" "$scratch/controls/schema.diff" || { echo "control not caught: $marker"; status=1; }
done < "$evidence/diff_controls.expected"
echo "controls: $(wc -l < "$evidence/diff_controls.expected" | tr -d ' ') markers checked"

if [ "${2:-}" != "--keep" ]; then
  for name in a b c; do supabase stop --workdir "$scratch/$name" --no-backup > /dev/null; done
fi
exit "$status"
