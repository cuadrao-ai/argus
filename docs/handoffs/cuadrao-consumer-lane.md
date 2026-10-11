# Cuadrao Consumer lane handoff

Updated October 11, 2026. This is the signed-in free-tier checkpoint under
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
- Normal-size core money acceptance now takes priority. The founder deferred
  extreme Dynamic Type acceptance to the final pre-TestFlight pass. Preserve
  the failed English result and the unrun Spanish case.

Accepted branding, navigation, typography, and sheet controls remain in the
native design guide and their linked evidence. This handoff does not reopen
copy approval, Apple enrollment, icon variants, or release enablement.

The [October 11 confirmed-value motion rule](../../.agent/designs/cuadrao/DESIGN.md#confirmed-value-motion--approved-october-11-2026)
is **APPROVED** for assigned native UI work. That design entry owns the rule and
Lucas's decision ID. Physical-phone repeated-use feel and haptic acceptance are
still **PENDING**; this approval does not reopen phone work or authorize a broad
animation sweep.

Apple activation remains pending until verified. Lucas is watching iCloud for
activation. After activation, the planned App Store Connect app uses bundle ID
`ai.cuadrao.app`. The Small Business Program also follows activation. This records
the future sequence only; it does not authorize account or app creation, enrollment,
monitoring automation, or an upload. TestFlight remains blocked until signed-in
staging MVEE acceptance is green. Green CI alone does not satisfy that gate.

## Integration and PR disposition

Repository `lagarcess/argus` uses `codex/private-alpha-next` for integration.
The October 11 fetched snapshot is `e465c2fe4bf7e2749215bc677a1fa225adab384c`.
Core source `40ff4967040c854ca5dd0764115227544011a6e2` is reconciled through
`286c6bc0494be6c858851f0c4037ea6df5bacea5`. The newer reconciliation and draft
publication await the coordinator's final integration-check notice.
Refresh remote state before acting; a dated snapshot is not the current tip.

| PR | Recorded state | Meaning |
| --- | --- | --- |
| [#937](https://github.com/lagarcess/argus/pull/937) | Merged as `43fac94de2672600079f312258908f05747a9d63` | Keyboard and sheet checkpoint accepted with explicit physical-test limits |
| [#940](https://github.com/lagarcess/argus/pull/940) | Merged as `cd14c9883f180876d27c121f0787b25a73529492` | Landing notes and pinned staging setup recorded; merged CI and smoke passed |
| [#916](https://github.com/lagarcess/argus/pull/916) | Merged as `59c695a0e2690f28bd5c5e48b73a66ce07ebc785` | Historical compatibility evidence and local rehearsal tool, with its limits preserved |
| [#952](https://github.com/lagarcess/argus/pull/952) | Merged as `ed0b2b760d00ba021c7f81a000fea05aa4a23d44` from `7e811a63554da6a642765731102321ef314f5deb` | Approved identifier fix, test repairs, and partial staging acceptance evidence |
| [#938](https://github.com/lagarcess/argus/pull/938) | Merged as `35fae200034c51ef27cee64d76adc4a903c19672` | Reconciles the earlier handoff while preserving the original record through its pinned link |

The coordinator merged #916, #952 and #938 into `codex/private-alpha-next`.
#916 preserves independent historical evidence. It adds no runtime prerequisite
for #952. Future Consumer merges remain with the coordinator.

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
owns its detailed results, source identities, screenshots, and failed attempts.
The [October 11 core evidence](../reports/evidence/consumer-core-checkpoint-20261011/README.md)
adds the completed Budget and Goal journeys and the bounded test-helper repairs.

- Four money journeys passed native checks, exact canonical API deltas, and
  relaunch checks. They cover income, spending, refunds, corrections, transfers,
  card credit, reconciliation, and separate currencies with unknown balances.
- Search passed editing, correction, origin preservation, and Spanish relaunch.
  The earlier split Goal evidence is superseded by one complete passing Goal
  execution at `7172fd6ff293cd00e956f255669e0d0b56711f8e` plus its retained
  no-write probe. Allocation, contribution correction, release/relink, target
  edit, archive/restore, Search origin and Spanish relaunch passed.
- Goal → Budget → Goal field identity passed after the approved one-line move
  into `CanvasDecimalInput.updateUIView`. No numeric or persistence code changed.
- The complete Budget journey passed at
  `40ff4967040c854ca5dd0764115227544011a6e2`. Spending, correction, cross-account
  refund, limit edit, removal/restore, Search origin and Spanish relaunch passed.
  The final limit of DOP 160.00, spending of DOP 155.00 and remaining DOP 5.00
  agree. The unknown balance of the refund account stays unknown.
- The account-entry failure came from the test drag starting inside the chart.
  The helper now derives the drag origin from its direction. Native Back waits
  for the existing hittable-button condition; Budget assertions wait for the
  amount and direction together. Three focused regressions passed. No product
  money or gesture code changed. Both later Budget timing failures and their
  canonical readbacks remain preserved.
- Earlier largest-text account and expense entry/cancel assertions passed. The Date
  label wraps one letter per line, so visual acceptance remains open. Software
  keyboard occlusion and every English/Spanish large-text surface are not proven.
- The later English stress case passed account keyboard/cancellation steps but
  failed its full Date-picker visibility assertion. Spanish did not run. The
  Date repair is parked at `55e06e92985fa6f1593fa89938853ddf78750611` on
  `codex/consumer-core-native-repairs`; it is absent from the current core diff.
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
`codex/consumer-free-tier-completion`. Its untracked
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
3. Retain the #952 and October 11 evidence at their original tested sources.
   Budget and Goal now have complete normal-size passes. Publish that evidence
   with the three bounded test-helper repairs. Large-text acceptance stays deferred.
4. Review each new bounded delta and run its applicable checks. Include modularity
   on the combined tree. Retain unaffected native evidence with its original source.
5. After an approved merge, verify the remote result and required integration checks.
   Record the landing through the repository workflow. #877 remains open.

Further product work follows the assigned signed-in free finish line. The
current landing does not authorize changes to hosted state or the parked scopes.
