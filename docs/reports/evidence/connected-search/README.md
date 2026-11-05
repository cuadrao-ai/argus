# Connected Search local iPhone demonstration

The [execution manifest](../../../specs/argus-execution-board.md#connected-search-on-iphone-lane)
owns scope, delivery status and remaining MVEE work. This demonstration uses
synthetic identities with real local Auth, API and Postgres. It does not verify
physical-iPhone internet delivery.

## Retained environment

Use `/Users/garces/.codex/worktrees/connected-search/private-alpha-next` on
`codex/connected-search`. The dedicated simulator is **Argus Connected Search**,
iPhone 17e with iOS 27, `01CBA853-5183-41AF-B1B8-024EF6DB8FFB`.
The installed bundle identifier is `local.argus.foundation`.

Search owns API 58800, Supabase 58801, Postgres 58802 and CAPTCHA bridge 58805.
The clickable simulator mirror uses loopback-only port 58913. Optional recovery
acceptance uses proxy 58812. The ignored
`ios/.build/accounts-local-58800/client.json` contains local synthetic credentials.
Do not publish that file or raw authentication logs.

The physical-phone testing owner uses ports 58700–58749. This demonstration
never operates that environment. Existing 584xx, 585xx and 586xx demos are
preserved, along with their separate simulators and records.

## Restart while preserving records

Do not run `configure`, `seed`, `reset` or delete Docker volumes. Skip a service
command if that service already runs for this Search demo. In separate terminals:

```sh
cd /Users/garces/.codex/worktrees/connected-search/private-alpha-next
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 58800
python3 ios/scripts/auth/local_stack.py api --accounts --port-base 58800 \
  --accounts-enabled on \
  --python /Users/garces/.codex/worktrees/5a42/private-alpha-next/.venv/bin/python
```

```sh
cd /Users/garces/.codex/worktrees/connected-search/private-alpha-next
python3 ios/scripts/auth/bridge.py --accounts --port-base 58800
```

Launch only the owned simulator:

```sh
xcrun simctl boot 01CBA853-5183-41AF-B1B8-024EF6DB8FFB # only if shut down
xcrun simctl launch 01CBA853-5183-41AF-B1B8-024EF6DB8FFB local.argus.foundation
```

Open [the live simulator](http://localhost:58913) on this Mac. This is a clickable
mirror of the installed native app, connected to the real local API and database.
The current Xcode installation uses DeviceHub instead of `Simulator.app`; the
verified browser mirror avoids depending on a missing app launcher.

If the mirror is not running, start it in its own terminal and keep that terminal
open. Stop the previous mirror terminal before replacing it on the same port.
Cleanup targets only the Search simulator:

```sh
SEARCH_SIM=01CBA853-5183-41AF-B1B8-024EF6DB8FFB
cleanup_search_mirror() {
  npx --yes serve-sim@0.1.47 --kill "$SEARCH_SIM" >/dev/null 2>&1 || true
}
trap cleanup_search_mirror EXIT INT TERM HUP
cleanup_search_mirror
npx --yes serve-sim@0.1.47 --port 58913 --host 127.0.0.1 --codec mjpeg --fit "$SEARCH_SIM"
```

Use only **Argus Connected Search** in the mirror; other listed simulators belong
to preserved demos or other owners. The mirror does not expose the app publicly.

## Try the connected journey

The retained simulator is signed into a synthetic local user after acceptance.
Open the Search tab (magnifying glass), enter `Search`, and choose Accounts,
Activity or Plan. Use the currency selector to narrow results.

- An account result opens the real account detail. Edit its name, return to
  Search, and see the changed matching result.
- An activity result opens the real activity detail and correction flow. Correct
  the amount or note, return, and inspect the current canonical revision.
- A Plan result opens its existing expectation editor. Save a change and see
  Search refresh; this does not change actual balances.
- Search `Search 0e0f30`, select Accounts and DOP, then load the next page.
  Open a result, return, and reopen the app to check the retained search origin.

Records created by acceptance remain available. Search `F476FC` to find the
final three-editor fixture: `Revised bank F476FC`, `Search income F476FC`
(DOP 27), and `Search bill F476FC` (DOP 35).

[Watch the 49-second demonstration](search-demo.mp4): correct a receipt in the
existing editor, return to its refreshed Search result, search/edit the Plan
expectation, and reopen in Spanish. The account rename is covered by the same
successful native test and its [empty old-match result](search-account-edit-removes-old-match.png).
The clip is continuous simulator footage, trimmed only to remove idle footage;
setup/login and the earlier account rename are outside the recorded excerpt.

[English activity result](search-activity-correction-return.png) ·
[Plan after edit](search-plan-expectation-editor-return.png) ·
[Spanish after reopening](search-spanish-light-relaunch.png) ·
[Exact scroll return](search-second-page-exact-return.png) ·
[Second reopening](search-second-page-relaunch-2.png).

## Verification record

| Surface | Evidence | Status |
| --- | --- | --- |
| Financial/Search backend | 205 focused tests against real local Postgres, zero skips | Passed |
| Search HTTP and ownership | [15-check real Auth/API proof](api-proof.json) | Passed |
| Required database discovery | Nine shared Search cases via `tests/test_financial_search_postgres.py` | Passed |
| Generated API artifact | 23 compatibility tests | Passed |
| Native state/model behavior | 22 tests; session package 48 passed, four opt-in live skips | Passed |
| Existing detail editors | `ui-20260929T220326Z.xcresult`, English/dark and Spanish/light | Passed at `c775b0c` |
| Accounts/Search independence | `ui-20260929T214541Z.xcresult` | Passed |
| Owner switch and isolation | `ui-20260929T214915Z.xcresult` | Passed |
| Exact multi-page return/relaunch | `ui-20260929T221133Z.xcresult`, Back plus two relaunches, <3-point difference | Passed at published `144322568` |
| Loading, retry and missing destination | `ui-20260929T215321Z.xcresult`, delayed read / 503 / retry / detail 404 | Passed |
| Independent review | [Full pass and affected deltas](independent-review.md) | Clean through `c775b0cdd1e05f4088fd9eb5d0ccf798d50882a4` |
| CI | [PR #751](https://github.com/lagarcess/argus/pull/751) | Terminal status and exact published head are recorded in the PR readiness comment |

The `.xcresult` bundles and raw logs are ignored local diagnostics; committed
screenshots and the final recording are the durable demonstration evidence.
The API proof was captured at `78e65a026`; later changes do not alter its backend
runtime. The account-tab and owner-switch runs used `5333b3304` and `397bd075`;
the recovery run used `93accb1d`. Subsequent native changes are limited to Search
scroll restoration. Its successful `89747bb51` run retained temporary numeric
geometry logs; `c775b0c` removes those logs without changing behavior, and passes
the full editor/relaunch journey. Final documentation/media commits do not alter
that reviewed implementation. Published `144322568` additionally passed the exact
multi-page Back/two-relaunch test and 34 Search database/API/OpenAPI tests. The
mirror-guide correction changes documentation only. The final PR readiness comment records exact-head
revalidation, current integration and terminal CI; earlier screenshots are
retained evidence, not claimed to have been captured at a future commit.

The scroll defect was confirmed in native traces: lazy content bounds clamped a
valid saved offset, then a competing SwiftUI scroll-to-row operation undid the
UIKit correction. Loaded pages now have measured row heights and one offset
owner. No diagnostic runtime logging remains.

## Remaining limitations

- This proves the assigned Search journey on a local simulator with synthetic
  users and real local Auth/API/Postgres. It does not prove physical-phone
  internet delivery, signing or deployment.
- Search covers accounts, current canonical activity and Plan expectations.
  Documents, household and other MVEE retrieval types remain in the existing
  execution manifest, outside this assignment.
- Response pages are bounded; the canonical financial snapshot still reads the
  owner's full record set. This is not a new indexed or semantic search engine.
- Edits use the existing financial controls and their existing limitations. Search
  does not create new money rules or a second transaction ledger.
