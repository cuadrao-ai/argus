#!/usr/bin/env bash
set -u
base="codex/private-alpha-next"
root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$root" || exit 0

fetched="no"
if timeout 15 git fetch --quiet --no-tags origin "$base" 2>/dev/null; then
  fetched="yes"
fi
tip="$(git rev-parse --verify --quiet "origin/$base" || echo unknown)"
branch="$(git branch --show-current 2>/dev/null)"
head="$(git rev-parse HEAD 2>/dev/null || echo unknown)"

echo "Session facts (generated at session start):"
echo "- Integration tip origin/$base: $tip (fetched this session: $fetched)"
echo "- Checkout: ${branch:-detached HEAD} at $head"
if [ "$tip" != "unknown" ] && [ "$head" != "unknown" ]; then
  echo "- Commits on integration not in this checkout: $(git rev-list --count HEAD.."origin/$base" 2>/dev/null || echo unknown)"
fi

claim="$(python3 - "${branch:-}" <<'PY' 2>/dev/null
import json, sys
branch = sys.argv[1]
try:
    data = json.load(open(".agent/ownership/branch_ownership.json"))
except Exception:
    sys.exit(0)
entry = data.get("branches", {}).get(branch)
if entry:
    allow = entry.get("allow", [])
    print(f"- Ownership gate entry for {branch}: {len(allow)} allowed paths")
    for path in allow[:25]:
        print(f"  - {path}")
    if len(allow) > 25:
        print(f"  - ... {len(allow) - 25} more in .agent/ownership/branch_ownership.json")
PY
)"
if [ -n "$claim" ]; then
  echo "$claim"
else
  echo "- Ownership gate entry for this branch: none. Cross-seat file claims arrive in the launch prompt."
fi

skill=""
for dir in \
  "$root/.agents/skills/poteto-mode" \
  "$HOME/.agents/skills/poteto-mode" \
  "$HOME/.codex/skills/poteto-mode" \
  "$HOME/.cursor/skills/poteto-mode" \
  "$HOME/.claude/skills/poteto-mode"; do
  if [ -f "$dir/SKILL.md" ]; then skill="$dir/SKILL.md"; break; fi
done
if [ -z "$skill" ]; then
  skill="$(ls -d "$HOME"/.claude/plugins/cache/*/pstack/*/skills/poteto-mode/SKILL.md 2>/dev/null | head -n 1)"
fi
if [ -n "$skill" ]; then
  echo "- poteto-mode skill: installed at $skill"
else
  echo "- poteto-mode skill: not installed in this environment."
fi
exit 0
