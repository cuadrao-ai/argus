# Argus Worktree Cleanup

Use `.github/cleanup-worktree.sh` before deleting a disposable Argus worktree
to reclaim dependency, build, and test-cache disk space.

Create disposable Argus worktrees as siblings of the repo, never nested inside
another Argus checkout. Nested worktrees can inherit the parent `.env` through
dotenv upward search, which can silently turn mocked runs into live LLM/provider
calls.

Run `.github/setup.sh` once in each new sibling worktree. With no selected
store, setup creates no environment files and fast dev can start without secrets.

For QA credentials, select an environment-specific external file. The store
must be a regular file owned by you, with mode `0600`. No staging or production
store is selected by default. Setup reads it as data and never changes it.

```bash
export CUADRAO_LOCAL_ENV_STORE=/absolute/path/local-secrets.env
bash .github/setup-worktree-env.sh "$PWD"
bash .github/setup-worktree-env.sh --check "$PWD"
```

The manifest in `scripts/ops/staging_env_manifest.json` owns local names and
rules. List the required store names without reading any values:

```bash
python3 scripts/ops/staging_env.py names local api required
```

Use one unquoted `NAME=value` per line. Blank lines and comment lines are allowed.
Values use letters, digits, and `_ . / : @ % + , = -`, with no spaces.
Dollar signs, backticks, quotes, backslashes, `#`, and multiline values are
rejected. This common literal subset has the same value in Bash, Python dotenv,
and the web loader. Unknown names and duplicate names fail before any write.

Setup writes private, gitignored `.env` and `web/.env.local` files in the target
worktree. It validates both destinations before it replaces either file. Each
worktree has its own files. A generated file can be regenerated. An existing
user-owned file requires `--replace`, unless its content already matches.
`--check` validates a selected store without writing files. Without a selected
store, it requires both regular worktree files.

Legacy env symlinks fail before loading or writing. Remove each link yourself
and rerun setup. Do not redirect into a linked file. The old canonical checkout
lookup and `ARGUS_CANONICAL_WORKTREE_ROOT` override have been removed.

For a disposable local database stack, `scripts/qa/write-local-env.sh` feeds
local discovery data to the same manifest resolver. It uses explicit disabled
provider defaults from the manifest unless the selected store supplies those
values. It refuses symlink destinations too.

Safe mode removes known generated bloat and keeps local untracked files such as
`.env` and `web/.env.local` intact:

```bash
.github/cleanup-worktree.sh /path/to/worktree
```

For a worktree that is definitely disposable, wipe all ignored and untracked
files too:

```bash
.github/cleanup-worktree.sh /path/to/worktree --wipe-untracked
```

Then remove the worktree:

```bash
git worktree remove /path/to/worktree
git worktree prune
```

Do not use `--wipe-untracked` in a worktree that may contain unsaved source,
notes, screenshots, or local environment files that need to be preserved.
