#!/bin/bash
# Classify changed files for CI job selection. The name predates job selection;
# the local smoke workflow calls it too, and reads only run_heavy.
#
# docs_only: every changed file is under docs/ or is the root README.md, and
#   none of those files is a shared contract. No test reads the root README
#   (tests/test_ci_job_selection.py proves that). Other root-level *.md is not
#   docs-only: backend tests read AGENTS.md and other root markdown.
# run_backend / run_database: the API, worker and Postgres jobs. A diff that
#   stays inside web/ or inside marketing/ skips both. A shared path runs them.
# run_frontend: frontend-checks. Marketing-only and docs-only skip it.
# run_heavy: true when backend, frontend or database work runs. Smoke reads it.
# run_marketing: marketing-checks. Marketing is its own package; outside
#   marketing/ it reads only supabase/functions/ (tests/test_ci_job_selection.py
#   proves that against the tree). Those two paths select it, and so do
#   .github/workflows/ci.yml (which defines the job and its pins) and this
#   script (which selects it). A shared path selects it too.
#
# Non-pull_request events and an empty file list run every job. Unknown paths
#   run the backend, frontend and database jobs, not marketing-checks.
# A failed file listing exits non-zero, which fails the aggregate ci check.

set -euo pipefail

BACKEND_PACKAGE_PATHS=()

load_backend_package_paths() {
  local paths
  paths="$(python3 - "$(dirname "${BASH_SOURCE[0]}")/../pyproject.toml" <<'PY'
import posixpath
import sys

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

with open(sys.argv[1], "rb") as source:
    packages = tomllib.load(source)["tool"]["poetry"]["packages"]
for package in packages:
    path = posixpath.normpath(posixpath.join(package.get("from", "."), package["include"]))
    patterns = [""]
    for segment in path.split("/"):
        expanded = [posixpath.join(prefix, segment) for prefix in patterns]
        patterns = patterns + expanded if segment == "**" else expanded
    sys.stdout.write("".join(pattern + "\n" for pattern in patterns))
PY
)"
  mapfile -t BACKEND_PACKAGE_PATHS <<< "$paths"
}

write_result() {
  local docs_only="$1"
  local run_heavy="$2"
  local run_marketing="$3"
  local run_backend="$4"
  local run_frontend="$5"
  local run_database="$6"
  printf 'docs_only=%s\n' "$docs_only"
  printf 'run_heavy=%s\n' "$run_heavy"
  printf 'run_marketing=%s\n' "$run_marketing"
  printf 'run_backend=%s\n' "$run_backend"
  printf 'run_frontend=%s\n' "$run_frontend"
  printf 'run_database=%s\n' "$run_database"
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    {
      printf 'docs_only=%s\n' "$docs_only"
      printf 'run_heavy=%s\n' "$run_heavy"
      printf 'run_marketing=%s\n' "$run_marketing"
      printf 'run_backend=%s\n' "$run_backend"
      printf 'run_frontend=%s\n' "$run_frontend"
      printf 'run_database=%s\n' "$run_database"
    } >> "$GITHUB_OUTPUT"
  fi
}

every_job() {
  write_result "false" "true" "true" "true" "true" "true"
}

is_docs_path() {
  local path="${1#./}"
  [ -n "$path" ] || return 1
  [ "$path" = "docs" ] || [ "$path" = "README.md" ] || [ "${path#docs/}" != "$path" ]
}

# marketing-checks reads only marketing/ and supabase/functions/; ci.yml defines
# the job and this script selects it. Everything else, including other .github/
# paths and any new top-level path, skips it unless the path is shared.
selects_marketing() {
  local path="${1#./}"
  case "$path" in
    marketing/*|supabase/functions/*|.github/workflows/*|.github/docs-only-changes.sh) return 0 ;;
    *) return 1 ;;
  esac
}

# A package file or a contract the API and the web both read. These run every job.
is_shared_path() {
  local path="${1#./}"
  local package_path
  case "$path" in
    web/*|marketing/*)
      for package_path in "${BACKEND_PACKAGE_PATHS[@]}"; do
        case "$path" in
          $package_path|$package_path/*) return 0 ;;
        esac
      done
      ;;
  esac
  case "$path" in
    poetry.lock|pyproject.toml|.python-version|render.yaml) return 0 ;;
    .github/workflows/*|.github/docs-only-changes.sh) return 0 ;;
    docs/api/openapi.yaml|docs/API_CONTRACT.md) return 0 ;;
    web/package.json|web/bun.lock|web/bun.lockb) return 0 ;;
    marketing/package.json|marketing/bun.lock|marketing/bun.lockb) return 0 ;;
    *) return 1 ;;
  esac
}

is_web_package_path() {
  local path="${1#./}"
  case "$path" in
    web/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_marketing_package_path() {
  local path="${1#./}"
  case "$path" in
    marketing/*) return 0 ;;
    *) return 1 ;;
  esac
}

classify_files() {
  local path
  local docs_only="true"
  local shared="false"
  local package_only="true"
  local saw_web="false"
  local saw_marketing="false"
  local run_marketing="false"
  if [ "$#" -eq 0 ]; then
    echo "No changed files given; fail closed to run every job."
    every_job
    return
  fi
  load_backend_package_paths
  echo "Changed files:"
  for path in "$@"; do
    printf '  %s\n' "$path"
  done
  for path in "$@"; do
    if is_shared_path "$path"; then
      shared="true"
    fi
    if ! is_docs_path "$path" || is_shared_path "$path"; then
      docs_only="false"
    fi
    if is_web_package_path "$path" && ! is_shared_path "$path"; then
      saw_web="true"
    elif is_marketing_package_path "$path" && ! is_shared_path "$path"; then
      saw_marketing="true"
    else
      package_only="false"
    fi
    if selects_marketing "$path" || is_shared_path "$path"; then
      run_marketing="true"
    fi
  done
  if [ "$shared" = "true" ]; then
    every_job
    return
  fi
  if [ "$docs_only" = "true" ]; then
    write_result "true" "false" "false" "false" "false" "false"
    return
  fi
  if [ "$package_only" = "true" ]; then
    local run_frontend="false"
    if [ "$saw_web" = "true" ]; then
      run_frontend="true"
    fi
    if [ "$saw_marketing" = "true" ]; then
      run_marketing="true"
    else
      run_marketing="false"
    fi
    local run_heavy="false"
    if [ "$run_frontend" = "true" ]; then
      run_heavy="true"
    fi
    write_result "false" "$run_heavy" "$run_marketing" "false" "$run_frontend" "false"
    return
  fi
  local run_heavy="true"
  write_result "false" "$run_heavy" "$run_marketing" "true" "true" "true"
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
  every_job
  exit 0
fi

if [ -z "${PR_BASE_SHA:-}" ]; then
  echo "PR_BASE_SHA is required for pull_request classification; fail closed." >&2
  every_job
  exit 0
fi

classify_git_files "$PR_BASE_SHA"
