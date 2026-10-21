#!/bin/zsh
SP=/private/tmp/claude-501/-Users-garces-Documents-projects-repos-argus--claude-worktrees-decision-attachment-refactor-098d43/a87878b8-b98a-412b-99b4-afda86e843b6/scratchpad
cd $SP/compat
./apply.sh 20261008110000 B2
for w in compat-build1 compat-build2; do ./probe.sh $w probe_docs.py cycle ${w#compat-}-at-B2 > /dev/null; done
for w in compat-build1 compat-build2 compat-activation; do ./run_suite.sh $w B2; done
./apply.sh 20261008130000 B3
for w in compat-build1 compat-build2; do ./probe.sh $w probe_docs.py cycle ${w#compat-}-at-B3 > /dev/null; done
for w in compat-build1 compat-build2 compat-activation; do ./run_suite.sh $w B3; done
COMPAT_HANDOFF=$SP/compat/handoff_accounts.json ./probe.sh compat-build2 probe_accounts.py create b2-at-B3
echo CHAIN_DONE
