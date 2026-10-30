#!/bin/bash
# Classify changed files for CI job selection. The name predates job selection;
# the local smoke workflow calls it too, and reads only run_heavy.
#
# docs_only: every changed file is under docs/. Root-level *.md is not
#   docs-only: backend tests read AGENTS.md and other root markdown.
# run_heavy: backend-checks, frontend-checks and guest-release-gates. Backend
#   tests scan `git ls-files` and web tests `git grep` the whole repository, so
#   any change outside docs/ can affect them.
# run_marketing: marketing-checks. Marketing is its own package; outside
#   marketing/ it reads only supabase/functions/ (tests/test_ci_job_selection.py
#   proves that against the tree). Only those two paths select it.
#
# Non-pull_request events and an empty file list run every job. Unknown paths
#   run the heavy jobs, not marketing-checks.
# A failed file listing exits non-zero, which fails the aggregate ci check.

set -euo pipefail

write_result() {
  local docs_only="$1"
  local run_heavy="$2"
  local run_marketing="$3"
  printf 'docs_only=%s\n' "$docs_only"
  printf 'run_heavy=%s\n' "$run_heavy"
  printf 'run_marketing=%s\n' "$run_marketing"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
      printf 'docs_only=%s\n' "$docs_only"
      printf 'run_heavy=%s\n' "$run_heavy"
      printf 'run_marketing=%s\n' "$run_marketing"
    } >> "$GITHUB_OUTPUT"
  fi
}

is_docs_path() {
  local path="${1#./}"
  [ -n "$path" ] || return 1
  [ "$path" = "docs" ] || [ "${path#docs/}" != "$path" ]
}

# marketing-checks reads only these paths. Everything else, including
# .github/ and any new top-level path, skips it.
selects_marketing() {
  local path="${1#./}"
  case "$path" in
    marketing/*|supabase/functions/*) return 0 ;;
    *) return 1 ;;
  esac
}

classify_files() {
  local path
  local docs_only="true"
  local run_marketing="false"
  if [ "$#" -eq 0 ]; then
    echo "No changed files given; fail closed to run every job."
    write_result "false" "true" "true"
    return
  fi
  echo "Changed files:"
  for path in "$@"; do
    printf '  %s\n' "$path"
  done
  for path in "$@"; do
    if ! is_docs_path "$path"; then
      docs_only="false"
    fi
    if selects_marketing "$path"; then
      run_marketing="true"
    fi
  done
  if [ "$docs_only" = "true" ]; then
    write_result "true" "false" "false"
  else
    write_result "false" "true" "$run_marketing"
  fi
}

collect_git_files() {
  local base_ref="$1"
  if ! git cat-file -e "${base_ref}^{commit}" 2>/dev/null; then
    git fetch --no-tags --depth=1 origin "$base_ref" >/dev/null
  fi
  git diff --name-only --no-renames --diff-filter=ACDMRTUXB "${base_ref}...HEAD"
}

# Command substitution keeps a git failure fatal; process substitution would
# hide it and classify whatever partial list was printed.
classify_git_files() {
  local listing
  listing="$(collect_git_files "$1")"
  if [ -n "$listing" ]; then
    mapfile -t FILES <<< "$listing"
  else
    FILES=()
  fi
  classify_files "${FILES[@]+"${FILES[@]}"}"
}

MODE=""
FROM_GIT=""
FILES=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --files)
      MODE="files"
      shift
      FILES=("$@")
      break
      ;;
    --from-git)
      MODE="from-git"
      FROM_GIT="${2:-}"
      if [ -z "$FROM_GIT" ]; then
        echo "--from-git requires a base ref or SHA." >&2
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage:
  .github/docs-only-changes.sh --files path [path ...]
  .github/docs-only-changes.sh --from-git <base-ref-or-sha>

On pull_request CI, omit flags and set PR_BASE_SHA. Other events run every job.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ "$MODE" = "files" ]; then
  classify_files "${FILES[@]+"${FILES[@]}"}"
  exit 0
fi

if [ "$MODE" = "from-git" ]; then
  classify_git_files "$FROM_GIT"
  exit 0
fi

if [ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]; then
  echo "Event '${GITHUB_EVENT_NAME:-local}' is not pull_request; run every job."
  write_result "false" "true" "true"
  exit 0
fi

if [ -z "${PR_BASE_SHA:-}" ]; then
  echo "PR_BASE_SHA is required for pull_request classification; fail closed." >&2
  write_result "false" "true" "true"
  exit 0
fi

classify_git_files "$PR_BASE_SHA"
