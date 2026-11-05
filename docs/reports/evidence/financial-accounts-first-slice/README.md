# Financial accounts first slice: acceptance evidence

Lane spec: [`docs/specs/lanes/financial-accounts-first-slice.md`](../../../specs/lanes/financial-accounts-first-slice.md).
Integration base: `4b84e054a0d8079b21f38784335ad3241809b4cd`
(`origin/codex/private-alpha-next`, fetched 2026-09-28). Before publication
integration had advanced to `c978927e167f57369f27391ac65995a3d6e5520a` (#727,
#728, #695, #713 landed) and was merged one way into the lane. The only shared
file was `render.yaml` (an unrelated hostname policy line); #728 changed the
server's sign-in client, which the real-stack gate exercises, so the lane's
deterministic, Postgres, real-stack, freeze, OpenAPI, release-doc, render
contract and modularity gates were rerun on the merged tree and passed.

## Environment

The VM had no Docker CLI, no Supabase CLI and no Postgres binaries, but a
Docker Engine (29.1.4) answered on `127.0.0.1:2375` with published ports
reachable and no shared bind mounts. `supabase start` needs bind mounts, so
the stack was assembled component by component from the images the CI-pinned
CLI (2.109.0) uses, each configured through environment variables only:

| Component | Image | Port |
| --- | --- | --- |
| Postgres | `supabase/postgres:17.6.1.140` | `127.0.0.1:55432` |
| Auth | `supabase/gotrue:v2.192.0` | via router |
| PostgREST | `postgrest/postgrest:v14.14` | via router |
| Router (`/auth/v1`, `/rest/v1`) | `nginx:alpine`, config baked by `docker build` | `127.0.0.1:55321` |

Credentials were generated with `openssl rand`, held in a `0600` file under
`/tmp`, and never printed or committed. Anonymous and service-role keys were
minted with the generated JWT secret. All 81 checked-in migrations plus
`supabase/seed.sql` were applied with `psql` inside the database container
(`docker cp` streams files without bind mounts), then the new migration on
top, giving 82 rows in `supabase_migrations.schema_migrations`.

Stack validity was checked before this lane's tests ran: the existing
`tests/test_avatar_theme_rls_postgres.py` (role-switch RLS) and
`tests/test_guest_auth_local_supabase.py::test_real_anonymous_identity_survives_reload`
(real GoTrue anonymous session through the API) both passed on it.

Resources created in the VM and removed afterward: containers
`argus-db-b0fe`, `argus-auth-b0fe`, `argus-rest-b0fe`, `argus-router-b0fe`,
network `argus-net-b0fe`, image `argus-router-b0fe:local`, and `/tmp/tooling`.

## Commands and results

Python 3.10.20 (pinned). Provider keys blanked;
`ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture`.

| Gate | Command | Result |
| --- | --- | --- |
| Deterministic routes and reference scenarios | `pytest tests/financial_accounts -q --no-cov` | 38 passed |
| Model-facing text freeze | `pytest tests/test_interpreter_prompt_freeze.py -q --no-cov` | 3 passed; this lane adds no model-facing text |
| Postgres gate | `ARGUS_DISPOSABLE_DATABASE_URL=… pytest tests/test_financial_accounts_postgres.py -q --no-cov` | 7 passed |
| Real-stack API gate | local proof variables set, `pytest tests/test_financial_accounts_api_postgres.py -q --no-cov` | 1 passed |
| OpenAPI compatibility, env scripts, release docs | `pytest tests/test_openapi_compatibility.py tests/test_environment_scripts.py tests/test_private_alpha_release_docs.py -q --no-cov` | 93 passed from a clean worktree (the VM's untracked `.env` placeholder makes 8 render-audit tests fail when run inside it; the same 8 pass at base in a clean worktree) |
| Lint | `ruff check src tests` | clean |
| Modularity budget | `python scripts/check_modularity_budget.py` | no violations |
| Docs links, whitespace | `python scripts/check_docs_links.py --base 4b84e054`; `git diff --check 4b84e054...HEAD` | clean |
| Full backend suite | `pytest tests -q --no-cov` from a clean worktree of the head with the Postgres proof variables exported | 9863 passed, 27 failed, 10 skipped (`full-suite.txt`). The 27 are not this lane: 22 need `web/node_modules` (`test_result_card_gain.py`, `test_canary_check_evidence.py`, `test_public_alpha_render_load.py`; the clean worktree has none), 4 are grant assertions that fail identically at base `4b84e054` on this stack because the `supabase/postgres` image's default ACLs grant `anon`/`authenticated` on older tables (this lane's tables carry `authenticated=r` only), and 1 was the prompt-freeze test, fixed in the head by removing wire-schema `Field(description=)` text from the measured `src/argus/domain` root; it passes on the head. |

## What each acceptance item is proven by

| Acceptance | Deterministic | Postgres | Real stack |
| --- | --- | --- | --- |
| Create then reopen returns the same accepted data | `test_create_then_reopen_returns_the_same_accepted_data` | `test_create_reopen_replay_and_conflict` | yes |
| Known zero differs from unknown | `test_known_zero_differs_from_unknown` | unknown create in the same test | unknown create |
| Currency precision and invalid inputs | `test_invalid_inputs_return_their_documented_code`, `test_currency_precision_follows_cldr`, `test_multiple_precisions` | | |
| Duplicate retries make one account | `test_duplicate_create_retries_make_one_account`, `test_duplicate_submission_create_part` | `test_concurrent_duplicate_creates_make_one_account` (8 threads) | replay and conflict |
| Unauthenticated and guest writes refused | `test_unauthenticated_and_guest_requests_are_refused` | `test_storage_refuses_an_anonymous_owner` (SQL function) | real GoTrue anonymous session → 403 |
| Two users isolated, including RLS | `test_two_users_cannot_read_or_mutate_each_others_accounts` | `test_rls_reads_are_owner_only_and_registered_only_and_writes_have_no_client_path`, `test_another_user_cannot_reach_the_account_through_the_repository` | two real registered sessions |
| Corrections preserve history, stale rules | `test_corrections_keep_history_and_enforce_expected_revision`, `test_opening_write_binds_caller_visible_account_version`, `test_first_slice_create_reopen_edit` | `test_edit_and_opening_compare_and_set_write_nothing_when_stale` | correction and stale edit |
| Default-off exposure | `test_flag_off_hides_the_surface_from_everyone` | | |
| Migration from the integration schema | | `test_migration_objects_exist_on_the_integration_schema`; 81 + 1 migrations applied in order | |

## Reference scenarios from PR #724

`tests/financial_accounts/test_reference_scenarios.py` re-expresses
`clavito_large_opening`, `blank_opening_unknown`,
`first_slice_create_reopen_edit`, `multiple_precisions`, the create part of
`duplicate_submission`, and the account rows of `account_edit_rules` over the
real routes, asserting the literal outcomes the reference tests assert. Rows
that need activity, totals or positions are named in each test and skipped
because nothing in this slice can produce them. The reference model is not
imported: it is not on integration, and its `Scene` reads the in-memory
`store.book` directly, so the scenario functions cannot take another driver.

## Limitations

- The stack is not `supabase start`. Kong, Storage, Realtime, Studio and
  Mailpit were not run; none of them is on this lane's path. GoTrue, PostgREST
  and Postgres are the CLI-pinned images.
- The full backend suite ran from a clean worktree because the VM's untracked
  `.env` overrides several test fakes; CI has no such file.
- No browser or native client exists for this surface yet, so there is no UI
  evidence. The surface is default-off.
