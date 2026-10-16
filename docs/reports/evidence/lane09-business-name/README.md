# Business owner naming

The owner sees the approved naming question on the first default-name Business visit. The server claims that visit once per Business. Skipping keeps the default name and stops automatic repeat prompts. Ajustes can still change the name. The shared required check precedes owner invitations and owner exports while the name is default.

The direct October 16, 08:45 CT lock supplies all new Spanish copy. The coordinator confirmed that both asks apply only to owner actions: accountants keep their existing export flow and never receive a naming prompt. Existing locale catalogs are unchanged. The approved Spanish copy has one local UI owner; no English translation was added.

## Candidate and evidence scope

- Original fetched integration: `2e30fe8979b384361d73093b7ac5cd2f497ce85d`.
- Reconciled integration: `d547945ea51ecb08dc3f7a6d160256da3a3cb770`.
- One-way merge: `466caa014444a6f02ffb8c79b19fddaa68de3f0c`.
- Frozen implementation: `9d94355d25ad1978fe8888a650423db9059dd570`.
- Worktree: `/private/tmp/cuadrao-lane09-business-name-20261016`.
- Branch: `codex/lane09-business-name-prompt`.

The evidence commit changes only this report and screenshots. Root must reconcile subsequent navigation and Personal work, run independent Eval, verify the recorded staging migration, and run terminal CI after marking the PR ready. Draft skips do not satisfy CI. No hosted change, user login, provider call, production action, or merge was performed by this worker.

Before images used the reconciled integration `BusinessApp` mount with the naming wrapper absent. Other working-tree naming files were present but unreachable in that view. The mount was restored before after captures. After images use the frozen implementation. All browser requests outside localhost were blocked; fixtures represent saved synthetic server state. This proves the rendered owner flow, not hosted persistence or real login.

| View | 1280px | 390px |
| --- | --- | --- |
| Before first visit | [Before](business-name-before-1280.png) | [Before](business-name-before-390.png) |
| Optional first visit | [After](business-name-after-1280.png) | [After](business-name-after-390.png) |
| Required invite step | [Required](business-name-required-1280.png) | [Required](business-name-required-390.png) |
| Saved name | [Saved](business-name-saved-1280.png) | [Saved](business-name-saved-390.png) |
| Editable Ajustes | [Settings](business-name-settings-1280.png) | [Settings](business-name-settings-390.png) |

The existing adaptive sheet/dialog supplies modal semantics and focus. Browser checks verify initial field focus, the full visible action area, skip then reload without a repeat, one required action, Escape refusal while required, no invite before saving, and editing the saved name in Ajustes. The [current accessibility guidance](https://developer.apple.com/videos/play/wwdc2026/220/) informed the native field, accessible name and explicit action checks. No new visual system was introduced.

## Verification

| Check | Result |
| --- | --- |
| Backend naming, access, spaces, export and OpenAPI compatibility | 120 passed |
| Focused real PostgreSQL naming proof | 5 passed |
| Actual naming-provider race suite | 7 passed |
| Desktop and phone browser flow | 2 passed |
| Existing access acknowledgement after integration merge | 3 passed |
| Full frontend with CI-matching Bun 1.3.14 | 2,657 passed; 0 failed; 19,389 expectations across 275 files |
| Targeted ESLint and application-only TypeScript | Passed |
| Ownership, modularity and whitespace | Passed |

Commands from this worktree:

```sh
PYTHONPATH=src:web .venv/bin/python -m pytest tests/business/test_business_naming.py tests/business/test_business_access_api.py tests/business/test_business_api.py tests/business/test_business_export.py tests/test_openapi_compatibility.py --no-cov -q
PYTHONPATH=src:web .venv/bin/python -m pytest tests/test_business_name_prompt_postgres.py --no-cov -q
cd web
bun test __tests__/business-naming-provider.dom.test.tsx
env -i PATH=/Users/garces/.bun/bin:/opt/homebrew/bin:/usr/bin:/bin /Users/garces/.bun/bin/bun --no-env-file test
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3196 bunx playwright test e2e/business-name-prompt.spec.ts
```

The targeted provider output is `7 pass, 0 fail`. The frozen full frontend output is `2657 pass, 0 fail`, with 19,389 expectations. Application-only TypeScript excludes test files; this is not a claim that the repository-wide test-file typecheck or production build ran locally.

The PostgreSQL command requires a process-only `ARGUS_DISPOSABLE_DATABASE_URL` pointing to an isolated disposable database. The local run used PostgreSQL 17 with exact spaces M1/M2 and M11 DDL from the existing Business migration, minimal local auth/role prerequisites, and the exact new migration. It did not apply the complete integration migration history. CI's existing real-PostgreSQL glob includes the new test file and supplies the same environment variable.

The highest-risk probe is `bun test __tests__/business-naming-provider.dom.test.tsx`. The late first-visit claim test first failed because `Ahora no` replaced an already-required dialog, then passed after the pending-continuation fence. The unmount probe first returned `stranded`, then returned `false` after the layout-effect cleanup cleared the current Business. The final seven cases cover StrictMode effect cancellation and single in-flight claim, account change, current Business change, required continuation cancellation, stale required reads, the actual export component, late optional response, and unmount.

The unchanged auth-boundary fixture adds a naming passthrough beside its existing workspace passthrough. Every account-change, late initial session and logout assertion remains. Separate tests exercise the actual naming provider; the browser exercises the actual application mount. The existing modal registry invariant now follows rendered component imports to the actual managed surface instead of assuming every settings wrapper directly imports it.

The existing period export component remains unmounted from the product UI, as required by its separate lane. Its shared naming guard is tested directly in the actual component and in the backend route. There is no browser claim for an end-to-end export entry point.

## Durable owner and tradeoffs

`public.spaces` owns both name and `business_name_prompt_seen_at`. The store claims a default-name prompt with one conditional update scoped to the authenticated owner's currently open Business and the expected Business ID. Sixteen simultaneous database claims produced one winner. A new store instance read the persisted result. Wrong owner, wrong Business, closed Business and direct client roles were refused. A newly opened Business had independent state.

This is an at-most-once server claim. Once an old Business request is accepted, losing the connection before display does not undo its seen state. Stale UI responses cannot show that prompt in another account/Business or consume the new Business's flag. A browser-only once flag and a separate onboarding table were rejected because they duplicate the canonical owner or fail across devices.

Both owner action routes recheck canonical state, so a stale client read cannot invite after the name becomes default. They do not hold a database lock across the whole invite/export operation; a truly simultaneous rename after that check is not serialized with the action. Existing backend action authorization remains authoritative. Name edits do not use model interpretation.

## Shared method ownership

| Existing owner | Narrow change |
| --- | --- |
| `domain/business/spaces.py` | `Space` derived naming state; `SpaceStore.claim_name_prompt`; both stores' claim, read/create and expected-ID rename |
| `api/business_schemas.py` | Four new naming request/response models |
| `api/routers/business.py` | `_naming`, three naming routes, `give_access` shared check |
| `api/routers/business_export.py` | `download_export` owner-only shared check |
| `BusinessApp.tsx` | Isolated naming wrapper inside the existing owner-keyed workspace |
| `BusinessAccessPanel.tsx` | `give` awaits the shared requirement |
| `ReceiptDossierReview.tsx` | `ReceiptPeriodExport.download` awaits the same requirement and checks cancellation |
| `ProfileMenu.tsx` | Owner-only preference row and quick-jump entry |
| `ProfileSettingsPanels.tsx` | `business_name` registry entry |
| `AdaptivePanel.tsx` | Optional `dismissible`, default true; desktop registry and close/backdrop controls |
| `BottomSheet.tsx` | Same optional prop; registry, close, scrim and drag behavior |
| Existing tests | Access/export fixture naming and resolved actor shape; default/dismiss-disabled sheet assertion; modal composition traversal; auth fixture naming passthrough |

BusinessWorkspace's acknowledgement fence arrives solely from the integration merge. This lane adds no BusinessWorkspace or auth production edit. The new provider, dialog, settings reader, copy module and API helper own naming behavior.

## Migration gate and rollback

The already-applied staging migration is `supabase/migrations/20261016142927_business_name_prompt.sql`, recorded by PR #1185. The unapplied `20261016153000` duplicate is removed. Deploy this application change only after its integration merge. Do not apply another naming migration or alter the applied file. The migration adds nullable `public.spaces.business_name_prompt_seen_at timestamptz`; no existing row, permission or default is changed. Root's staging verification uses:

```sql
select data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and table_name = 'spaces'
  and column_name = 'business_name_prompt_seen_at';
select relrowsecurity from pg_class where oid = 'public.spaces'::regclass;
```

Local results were `timestamp with time zone | YES | NULL` and `true`. Both `anon` and `authenticated` were denied direct select/update of the new state. The original local proof does not establish hosted acceptance. Rollback changes repository files only. Retain the nullable staging column and applied migration history; do not run a down migration, drop data or edit an applied migration.

## Cleanup

The owned server on port 3196 exited. The owned disposable container `cuadrao-lane09-naming-20261016` stopped and was removed, including its temporary in-memory data. No other container or shared image was removed.

| Removed owned cache | Allocated bytes |
| --- | ---: |
| `web/.next` | 170,217,472 |
| `temp/bun-cache` | 596,439,040 |
| `temp/uv-cache` | 22,618,112 |
| Total | 789,274,624 |

Whole-volume `df -k` available space changed from 169,200,000 KiB to 169,600,000 KiB during cleanup. Other processes share that volume; the path measurements identify this worker's scope. The worktree, empty ignored environment files, evidence, installed dependencies and reproduction logs remain available for review.
