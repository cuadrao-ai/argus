#!/bin/bash
# Classify changed files for CI job selection. The name predates job selection;
# the local smoke workflow calls it too, and reads only run_heavy.
#
# docs_only: every changed file is under docs/ or is the root README.md. No
#   test reads the root README (tests/test_ci_job_selection.py proves that).
#   Other root-level *.md is not docs-only: backend tests read AGENTS.md and
#   other root markdown.
# run_heavy: backend-checks, frontend-checks and database-checks. Backend
#   tests scan `git ls-files` and web tests `git grep` the whole repository, so
#   any change outside docs/ can affect them.
# run_marketing: marketing-checks. Marketing is its own package; outside
#   marketing/ it reads only supabase/functions/ (tests/test_ci_job_selection.py
#   proves that against the tree). Those two paths select it, and so do
#   .github/workflows/ci.yml (which defines the job and its pins) and this
#   script (which selects it).
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
  [ "$path" = "docs" ] || [ "$path" = "README.md" ] || [ "${path#docs/}" != "$path" ]
}

# marketing-checks reads only marketing/ and supabase/functions/; ci.yml defines
# the job and this script selects it. Everything else, including other .github/
# paths and any new top-level path, skips it.
selects_marketing() {
  local path="${1#./}"
  case "$path" in
    marketing/*|supabase/functions/*|.github/workflows/ci.yml|.github/docs-only-changes.sh) return 0 ;;
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
  # -z prints raw NUL-terminated paths. Without it Git quotes and escapes
  # paths with non-ASCII bytes or control characters ("marketing/app/espa\303\261ol.tsx"),
  # and the quoted string matches no prefix.
  git diff -z --name-only --no-renames --diff-filter=ACDMRTUXB "${base_ref}...HEAD"
}

# The listing goes to a temp file, not a pipe or process substitution, so a git
# failure stays fatal under set -e instead of classifying a partial list.
# Command substitution would drop the NUL separators.
classify_git_files() {
  LISTING="$(mktemp)"
  trap 'rm -f "$LISTING"' EXIT
  collect_git_files "$1" > "$LISTING"
  mapfile -d '' -t FILES < "$LISTING"
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
