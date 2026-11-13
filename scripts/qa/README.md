# Local real-auth QA setup

These scripts prepare a worktree for QA against real Supabase Auth. Everything
here targets the worktree-local Supabase stack (or one approved QA branch) and is
blocked from production by `assert-nonprod-target.sh`.

## Setup

```bash
supabase start -x vector,edge-runtime,imgproxy   # once per machine boot
supabase db reset --local                        # migrations from zero + seed
bash scripts/qa/write-local-env.sh               # untracked .env + web/.env.local
```

New worktrees have no shared env links. For credentials, set
`CUADRAO_LOCAL_ENV_STORE=/absolute/path/local-secrets.env` before setup or a QA
command. The store must be external, owned by you, and mode `0600`. The manifest
owns the required names. Run `python3 scripts/ops/staging_env.py names local api required`
to list them. See [worktree setup](../../.github/WORKTREE_CLEANUP.md) for the literal
value format and replacement rules.

`write-local-env.sh` reads local stack discovery as data and uses the same
manifest resolver. It creates regular private files in this worktree. Existing
user-owned files need `--replace`. Legacy symlinks must be removed by the user
first. Never write into a linked `.env` or `web/.env.local`.

Later setup and QA commands refuse a selected store that conflicts with the
generated database target or credentials. This applies to every generated target,
including ordinary store regeneration. `--replace` does not bypass it, and
`--check` reports the same conflict. Provider and model settings can still change.
Unset `CUADRAO_LOCAL_ENV_STORE` to keep using discovered files, or rerun
`write-local-env.sh` to discover the local target and credentials again. For a
deliberate store target change, first remove the worktree `.env` and
`web/.env.local` files yourself, then rerun setup. Keep or remove the pair together;
a generated web file without its generated root file refuses regeneration.

The browser guard uses the installed web framework environment loader, including
its file precedence, comments, quotes, and variable expansion. Install web
dependencies before QA. Set `NODE_ENV=production` when checking a production
build; otherwise the guard follows development mode (or test mode when selected).

The local stack uses the stable `project_id = "argus-qa"` (containers such as
`supabase_db_argus-qa`) and a same-site topology — app on
`http://localhost:3000`, API on `http://localhost:8000` — so the Argus
HttpOnly cookie transport is real in local QA.

## Identities

`setup-local-identities.sh` creates two disposable users through the real
Argus signup path (allowlist rows come from `supabase/seed.sql`), verifies
login, and writes runtime credentials to untracked `.qa-identities.env`.
It talks only to the stack's HTTP surface (auth admin + PostgREST), so it
needs no Docker access.
`--teardown` removes users, profiles, and the credential file. Passwords are
generated per setup run and never committed.

## Hosted QA branch mode

Export `ARGUS_QA_APPROVED_SUPABASE_REF=<branch project ref>` and point the
generated env files at that branch before running; the guard then admits
exactly that ref and still hard-fails on any production reference.

## Backend tests

The focused backend matrix must run hermetically, per `AGENTS.md`:

```bash
OPENROUTER_API_KEY= ALPACA_API_KEY= ALPACA_SECRET_KEY= \
ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture \
poetry run pytest tests/test_auth_sessions.py tests/test_alpha_api_supabase.py \
  tests/test_alpha_artifacts.py tests/test_environment_scripts.py -q --no-cov
```
