#!/bin/zsh
# usage: probe.sh <worktree> <probe.py> <subcommand> <label>
SP=/private/tmp/claude-501/-Users-garces-Documents-projects-repos-argus--claude-worktrees-decision-attachment-refactor-098d43/a87878b8-b98a-412b-99b4-afda86e843b6/scratchpad
source $SP/compatstack/env.sh
cd /Users/garces/Documents/projects/repos/argus-worktrees/$1
export PYTHONPATH=src:. COMPAT_HANDOFF=${COMPAT_HANDOFF:-$SP/compat/handoff_${2%.py}.json}
env -u ANTHROPIC_BASE_URL $PY $SP/compat/$2 $3 2>&1 | grep -vE "^\s*$" > $SP/compat/probe_${2%.py}_$3_$4.log
echo "exit=$pipestatus[1]" >> $SP/compat/probe_${2%.py}_$3_$4.log
grep -E "^[A-Za-z_0-9]+: |exit=|Error|Traceback" $SP/compat/probe_${2%.py}_$3_$4.log | cut -c1-400
