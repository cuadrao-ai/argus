# Supabase CLI release resolution

Captured on 2026-10-05. Integration base is `875de09ac2115acec42e09060b92878aa5f18eff`.

PR #844's [latest CLI job](https://github.com/lagarcess/argus/actions/runs/37340157835/job/111866183195) failed before database startup or tests. The action emitted `Failed to resolve latest Supabase CLI release: rate limit exceeded`.

The job resolved `supabase/setup-cli@v1` to `1dedf2c611547ede7232d26866dd3c56ab903bbb`. Its [public action contract](https://github.com/supabase/setup-cli/blob/1dedf2c611547ede7232d26866dd3c56ab903bbb/action.yml) documents `github-token` specifically for avoiding unauthenticated latest-release API limits. `vendor-action.yml` preserves that public contract.

The workflow now passes the existing job token through that input. Permissions remain `contents: read`. Both pinned and latest CLI checks remain enabled. This fixes CI infrastructure and makes no runtime or hosted configuration change.

The baseline and changed checkout each passed all 26 tests in `tests/test_ci_workflow.py`, with zero failures or skips. The command was `/Users/garces/.codex/worktrees/05f0/private-alpha-next/.venv/bin/python -m pytest tests/test_ci_workflow.py -q --no-cov`. `git diff --check` also passed.

Local tests validate the workflow structure. Actual authenticated release resolution and the full CI result require the new PR's exact-head run. No provider calls or hosted data access were performed locally.

Independent read-only review approved the changed line with no findings. It checked the exact vendor revision, failed-job log, permissions and matrix. Comment review found zero added comments and required no deletions. The infrastructure failure is tracked in [issue #850](https://github.com/lagarcess/argus/issues/850).
