#!/bin/zsh
# usage: apply.sh <version> <label>  (applies one approved version with the repo tool)
SP=/private/tmp/claude-501/-Users-garces-Documents-projects-repos-argus--claude-worktrees-decision-attachment-refactor-098d43/a87878b8-b98a-412b-99b4-afda86e843b6/scratchpad
source $SP/compatstack/env.sh
cd /Users/garces/Documents/projects/repos/argus-worktrees/compat-activation
ARGUS_APPLY_DATABASE_URL=$DB_URL $PY scripts/ops/apply_approved_migrations.py --candidate-sha 1d3e814b1a3faf0b683b814d3a527c40386cda66 --approved-file $SP/compat/approved_$1.json --allow-host 127.0.0.1 --allow-database postgres --execute > $SP/compat/apply_$2.log 2>&1
echo "exit=$?" >> $SP/compat/apply_$2.log
cat $SP/compat/apply_$2.log
