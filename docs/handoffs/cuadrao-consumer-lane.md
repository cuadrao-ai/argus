# Cuadrao Consumer lane handoff

Updated October 10, 2026. This is the signed-in free-tier checkpoint under
[#877](https://github.com/lagarcess/argus/issues/877), not full app acceptance.
The [October 9 handoff](https://github.com/lagarcess/argus/blob/95720e014ee35fedb39bbb44d8c19ea8faece8b7/docs/handoffs/cuadrao-consumer-lane.md)
retains the earlier build, design, service, and branch history. Its old next steps
and acceptance gates are superseded by this checkpoint and the later founder
instructions recorded below.

## Scope and authority

Read [documentation authority](../DOCUMENTATION_AUTHORITY.md), the
[execution manifest](../specs/argus-execution-board.md), the
[native design guide](../../.agent/designs/cuadrao/DESIGN.md), and
[iOS instructions](../../ios/README.md) within their declared scope.

The founder's assigned finish line is a signed-in free account with manual
accounts, transactions, budgets, goals, Search, separate currency totals,
corrections, finding records later, and correct balances after relaunch.
English, Spanish, and large text are included. This assignment does not redefine
the full Consumer launch scope or the future paid tier.

The following decisions supersede the original handoff:

- Guest mode, saved receipts, shared plans, and RevenueCat are outside the active
  assignment. The transaction redesign stays parked. Preserve those branches.
- The founder stopped VoiceOver and Switch Control work and accepted simulator
  evidence plus green CI for #937. No further accessibility tooling or phone
  work is assigned. Physical acceptance is not implied by simulator results.
- Signed-in money acceptance uses `https://cuadrao-api-staging.onrender.com` only.
  The backend stays pinned to `cad1cbe1ec27ff89c08eadbec31718a0e627383c`.
- The earlier staging-only account flag activation and same-code restart were
  approved and completed. No further hosted changes, migrations, deployments,
  phone installation, TestFlight upload, or paid/live-AI tests are authorized.
- The one-line amount identifier fix and draft PR publication were explicitly
  approved. Later coordination permits bounded integration reconciliation and
  landing in the assigned merge slot. It does not expand product scope.

Accepted branding, navigation, typography, and sheet controls remain in the
native design guide and their linked evidence. This handoff does not reopen
copy approval, Apple enrollment, icon variants, or release enablement.

Apple activation remains pending until verified. Lucas is watching iCloud for
activation. After activation, the planned App Store Connect app uses bundle ID
`ai.cuadrao.app`. The Small Business Program also follows activation. This records
the future sequence only; it does not authorize account or app creation, enrollment,
monitoring automation, or an upload. TestFlight remains blocked until signed-in
staging MVEE acceptance is green. Green CI alone does not satisfy that gate.

## Integration and PR disposition

Repository `lagarcess/argus` uses `codex/private-alpha-next` for integration.
The October 10 landing snapshot is `ed0b2b760d00ba021c7f81a000fea05aa4a23d44`.
Refresh remote state before acting; a dated snapshot is not the current tip.

| PR | Recorded state | Meaning |
| --- | --- | --- |
| [#937](https://github.com/lagarcess/argus/pull/937) | Merged as `43fac94de2672600079f312258908f05747a9d63` | Keyboard and sheet checkpoint accepted with explicit physical-test limits |
| [#940](https://github.com/lagarcess/argus/pull/940) | Merged as `cd14c9883f180876d27c121f0787b25a73529492` | Landing notes and pinned staging setup recorded; merged CI and smoke passed |
| [#916](https://github.com/lagarcess/argus/pull/916) | Merged as `59c695a0e2690f28bd5c5e48b73a66ce07ebc785` | Historical compatibility evidence and local rehearsal tool, with its limits preserved |
| [#952](https://github.com/lagarcess/argus/pull/952) | Merged as `ed0b2b760d00ba021c7f81a000fea05aa4a23d44` from `7e811a63554da6a642765731102321ef314f5deb` | Approved identifier fix, test repairs, and partial staging acceptance evidence |
| [#938](https://github.com/lagarcess/argus/pull/938) | This handoff reconciliation | Replaces stale instructions while preserving the original record through its pinned link |

The coordinator merged #916, then #952. The coordinator owns the final #938
merge after #952 integration verification and #938 review and CI are complete.
#916 preserves independent historical evidence; it adds no runtime prerequisite
for #952.

The [#916 terminal landing record](https://github.com/lagarcess/argus/pull/916#issuecomment-6101642318)
confirms identical reviewed and landed trees, successful merge CI, and actual
local smoke. #952 also has an identical reviewed and landed tree. Its merge
checks are [full CI](https://github.com/lagarcess/argus/actions/runs/38082813475)
and [local smoke](https://github.com/lagarcess/argus/actions/runs/38082813551).
Use the merged PR and these runs to verify their terminal results. These checks
do not establish complete native, staging, or phone acceptance.

The [#937 landing record](https://github.com/lagarcess/argus/blob/cd14c9883f180876d27c121f0787b25a73529492/docs/reports/2026-10-09-pr-937-integration-landing.md)
owns the accepted source, four simulator journeys, and physical-test limits.
Earlier evidence that says #937 was unmerged is a dated record, not an active gate.

## Acceptance evidence and remaining gaps

The [#952 evidence](https://github.com/lagarcess/argus/blob/7e811a63554da6a642765731102321ef314f5deb/docs/reports/evidence/consumer-signed-in-free-staging-20261009/README.md)
owns the detailed results, source identities, screenshots, and failed attempts.

- Four money journeys passed native checks, exact canonical API deltas, and
  relaunch checks. They cover income, spending, refunds, corrections, transfers,
  card credit, reconciliation, and separate currencies with unknown balances.
- Search passed editing, correction, origin preservation, and Spanish relaunch.
  Goal data operations and the later Search/relaunch replay have split evidence;
  the original full Goal test did not pass in one execution.
- Goal → Budget → Goal field identity passed after the approved one-line move
  into `CanvasDecimalInput.updateUIView`. No numeric or persistence code changed.
- The full budget rerun failed during account-entry setup at `accounts.add`,
  before budget assertions. The cause and full budget acceptance remain open.
- Largest-text account and expense entry/cancel assertions passed. The Date
  label wraps one letter per line, so visual acceptance remains open. Software
  keyboard occlusion and every English/Spanish large-text surface are not proven.
- Earlier passing journeys retain their own tested sources. They were not all
  rerun after the identifier-only change. CI does not replace native acceptance.
- Native staging sign-in used a local CAPTCHA fixture with real staging identity
  and money APIs. This does not prove hosted CAPTCHA or production sign-in.

The identifier regression and Release simulator build passed. Five readback
unit tests, configured Python lint, and modularity checks passed. Full local
pytest stopped at collection on the existing SciPy binary load error. The six
native model-test baseline failures remain tracked in #898. Neither limitation
is a green test result.

The compatibility matrix in #916 is an October 8 local database rehearsal.
Its failures and skips remain evidence, not a current full-suite pass. The
Storage test-interference finding was closed by the founder's acceptance of
Business's evidence. Hosted receipt storage/deletion acceptance remains separate
and outside this assignment.

## Preserved work and ownership

Current Consumer implementation worktree:
`/Users/garces/.codex/worktrees/4a54/private-alpha-next`, branch
`codex/consumer-staging-free-acceptance`. Its untracked
`docs/reports/2026-10-09-consumer-free-tier-finish-line.md` is an older working
report. Do not publish it as current evidence without reconciling its claims.
Private credentials, generated configs, and local test bundles stay outside Git.

The following worktrees remain under
`/Users/garces/Documents/projects/repos/argus/.claude/worktrees/`:

| Worktree | Branch and original preserved head | State |
| --- | --- | --- |
| `cuadrao-applier` | `codex/cuadrao-compat-matrix`, `70c8eb9c4` | #916 owns the evidence. The supposedly unfinished runbook heading edit was already committed in `cad1cbe1e`; its interrupted validation is not promoted to a pass |
| `cuadrao-release-surface` | `codex/cuadrao-consumer-handoff`, `95720e014` | #938 owns this documentation reconciliation |
| `agent-a3ea4bb6855947c8f` | `codex/cuadrao-guest-book`, `245703206` | Parked, no PR. Untracked `.venv` and `guest-mode-evidence/`; unfinished Search work and verification remain |
| `agent-accef4746fb45a304` | `codex/cuadrao-transaction-sheet`, `3dfaa1691` | Parked, local only, no PR. Twenty staged paths plus `.venv` and untracked `transaction-sheet-mock/` remain intact |

Do not reset, clean, publish, or reconcile the parked branches as part of this
landing. The original handoff retains their detailed historical verification.
Later reconciliation will need to account for shared native amount, toolbar,
transaction-sheet, and test files. It needs its own assignment.

Business owns the shared ingestion implementation. Consumer reuses the existing
financial-documents services. Shared auth, API contracts, schemas, runtime, and
migration/release work require coordination with their owners before changes.
The [Business handoff](cuadrao-business-lane.md) and
[Marketing handoff](cuadrao-marketing-launch-lane.md) retain their lane boundaries.
No separate mobile ingestion system is assigned. Do not edit their worktrees or
stop their services. The founder's local phone API and forwarder also stay untouched.

## Resume the assigned Consumer work

1. Refresh the assigned PR and integration heads. The coordinator owns final
   merges in this landing queue.
2. Use a dedicated Consumer worktree. Merge current integration into the owning
   branch without rebasing published or evidenced history. Inspect semantic overlap.
3. Use the retained #952 evidence to distinguish tested behavior from open gaps.
   Budget completion, the large-text Date layout, and full Goal acceptance remain open.
4. Review each new bounded delta and run its applicable checks. Include modularity
   on the combined tree. Retain unaffected native evidence with its original source.
5. After an approved merge, verify the remote result and required integration checks.
   Record the landing through the repository workflow. #877 remains open.

Further product work follows the assigned signed-in free finish line. The
current landing does not authorize changes to hosted state or the parked scopes.
