#!/bin/bash
# Select documentation readers. Helpers select their folder; pytest owns its
# recursive collection rules and never receives a helper as an explicit test.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

list_matches() {
  local status=0
  if command -v rg >/dev/null 2>&1; then
    rg -l --glob '*.py' -e 'docs/' -e "['\"]docs['\"]" tests || status=$?
  else
    git grep -l -e 'docs/' -e '"docs"' -e "'docs'" -- 'tests/*.py' || status=$?
  fi
  # Search tools use 1 for no matches, and >1 for an actual failure.
  if [ "$status" -gt 1 ]; then
    return "$status"
  fi
}

# Command substitution preserves the exit status, unlike process substitution.
matches="$(list_matches)"
while IFS= read -r path; do
  [ -n "$path" ] || continue
  case "${path##*/}" in
    test_*.py|*_test.py) printf '%s\n' "$path" ;;
    *) dirname "$path" ;;
  esac
done <<< "$matches" | sort -u | awk '
  !parent || index($0, parent "/") != 1 { print; parent = $0 }
'
