#!/bin/bash
# Package-only PRs skip backend/database work unless a literal outside-package
# reference or Python package metadata makes a changed path shared. Integration
# pushes and other non-PR events run everything. Failed reads fail the gate.
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
  local keys=(docs_only run_heavy run_marketing run_backend run_frontend run_database)
  local index=0
  for value in "$@"; do
    printf '%s=%s\n' "${keys[$index]}" "$value"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
      printf '%s=%s\n' "${keys[$index]}" "$value" >> "$GITHUB_OUTPUT"
    fi
    index=$((index + 1))
  done
}

every_job() { write_result false true true true true true; }

is_shared_path() {
  local path="$1" package_path status=0
  for package_path in "${BACKEND_PACKAGE_PATHS[@]}"; do
    case "$path" in $package_path|$package_path/*) return 0 ;; esac
  done
  # Fixed strings deliberately include prose and tests, not just imports.
  # Exclude the owning top-level package (or the root file itself).
  git grep -F -q -e "$path" -- . ":(exclude)${path%%/*}" || status=$?
  if [ "$status" -gt 1 ]; then exit "$status"; fi
  return "$status"
}

classify_files() {
  local path docs_only=true package_only=true web=false marketing=false
  if [ "$#" -eq 0 ]; then every_job; return; fi
  load_backend_package_paths
  for path in "$@"; do
    path="${path#./}"
    if is_shared_path "$path"; then every_job; return; fi
    case "$path" in
      docs/*|docs|README.md) package_only=false ;;
      web/*) docs_only=false; web=true ;;
      marketing/*) docs_only=false; marketing=true ;;
      *) docs_only=false; package_only=false ;;
    esac
  done
  if [ "$docs_only" = true ]; then
    write_result true false false false false false
  elif [ "$package_only" = true ]; then
    write_result false "$web" "$marketing" false "$web" false
  else
    write_result false true "$marketing" true true true
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
  every_job
  exit 0
fi

if [ -z "${PR_BASE_SHA:-}" ]; then
  echo "PR_BASE_SHA is required for pull_request classification; fail closed." >&2
  every_job
  exit 0
fi

classify_git_files "$PR_BASE_SHA"
