#!/bin/zsh
# usage: run_suite.sh <worktree-name> <label>
SP=/private/tmp/claude-501/-Users-garces-Documents-projects-repos-argus--claude-worktrees-decision-attachment-refactor-098d43/a87878b8-b98a-412b-99b4-afda86e843b6/scratchpad
W=$1; L=$2
source $SP/compatstack/env.sh
cd /Users/garces/Documents/projects/repos/argus-worktrees/$W
start=$(date +%s)
env -u ANTHROPIC_BASE_URL $PY -m pytest -q -p no:cacheprovider -o addopts="" -rfE $(cat $SP/compat/files_$W.txt) > $SP/compat/run_${W}_${L}.log 2>&1
echo "exit=$? seconds=$(( $(date +%s) - start ))" >> $SP/compat/run_${W}_${L}.log
tail -3 $SP/compat/run_${W}_${L}.log
