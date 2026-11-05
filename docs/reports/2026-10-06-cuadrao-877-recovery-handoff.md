# Cuadrao recovery handoff for #877, October 6, 2026

This is the starting record for the engineering lead who owns
[#877](https://github.com/lagarcess/argus/issues/877). That issue already holds
the execution map R0 to R7, the acceptance journeys A1 to A12, source entry
points, commands, rollback and resource rules. Read it first. This record adds
the state verified on October 6, the order of first actions, and the boundaries
that apply to the lead. It does not replace #877, change its acceptance or open a
second roadmap.

The documentation reconciliation that produced this record is in the
[launch reconciliation](2026-10-06-cuadrao-launch-reconciliation.md). It changed
no runtime file.

## The deliverable

One combined **Cuadrao Check** build. It uses the approved Preview interface,
keeps the useful connected money actions, and carries the final Trust safety
behavior. **Cuadrao Preview** stays installed and untouched as the visual
reference until Lucas accepts the replacement. Do not rebuild the approved
interface and do not start a new design pass. Connect the existing data owners to
the preserved presentation. Do not show sample records as live financial truth.

The lead may delegate bounded work and owns the combined result. One writer owns
each branch and each shared runtime owner (the recovered shell, the session
controller, the receipt store). One scheduler owns conflicting simulator and
phone work.

## Verified state

| Item | State |
| --- | --- |
| Integration | `codex/private-alpha-next` was `df3882668413e7978d3983adfe1f054cb83595c4` when this reconciliation started. This documentation change lands on top of it. Fetch again; record the new tip as the R0 starting point. |
| Recovery branch | `codex/cuadrao-connected-preview` at `1eca92329c62c012fc789beb3b9c973c49aaaef2`, pushed. Worktree `/Users/garces/.codex/worktrees/cuadrao-connected-preview/private-alpha-next`, clean at that head when read on October 6. No recovery PR exists. |
| Integration already inside recovery | `70b0cd3891937f026900aceb96ce5f556c76b0b3` through merge `0a512315142c8d59b71146b0e24e1848072634e2`. Original base `875de09ac2115acec42e09060b92878aa5f18eff`. |
| Not yet inside recovery | Every integration commit after `70b0cd389`, including #864 session validation `5d46a73d4`, #874 first Apple name `a2c65549b`, #875 journaled deletion `8146d16e9`, #876 atomic cleanup `184d2614e`, #854 paired transfers `7d037b07d`, #845 privacy evidence `dd04130e8`, #871, #865, #860 and #873 housekeeping. |
| Approved Preview source | `5753b5d7cb3e4a13b4bac58a87fa32127b6fcf37`. Installed Preview build 3427, `local.cuadrao.design.47R3855RTJ`. |
| Last installed Check | Build 3433, `local.argus.founder.47R3855RTJ`, source `2a1d911b3993b208a25b51ecd156af8a31b6121c`. Predates the final recovery source and later Trust changes. Both build statements are recorded history, not a fresh device readback. |
| Candidate branches | `codex/cuadrao-primary-home-bindings-20261005` at `87a616ef09ef2e8f746f7a5db29b03bd6d40a31e` (Home summaries ordered by primary currency). `codex/cuadrao-primary-forecast-binding-20261005` at `27dc03711ab93b5a6273da6ab1394ab4d97f6f78` (Plan forecast bound to the selected currency). Both sit on integration `70b0cd389`. Reviewed candidates, not accepted runtime. Check each branch head and owner again before reuse, and never copy stale presentation into the recovered views. |
| Personal observation reader | Source `5aa369d9ef4aee5d1b0fcf55ba2a8280eef04cac`. Seven focused tests passed, the app compiled, and a scoped source review was clean. No production view calls it. It is not a chart. |
| Trial merge | A read-only trial merge of `1eca92329` with `df3882668` overlapped in `FinancialLoopModel.swift`, `ConnectedCuadraoAuth.swift` and `FinancialModelTests.swift`. Only the test file conflicted textually. Files under `ios/ArgusFoundation/Cuadrao/` were unchanged. It was not an actual reconciliation or a passing build. Rerun it, because both heads can move. |
| Visual result | Ten of fourteen comparison captures were pixel-identical inside the comparison region. Four differ and are documented. This is not full visual parity. |
| Phone | Lucas confirmed sign-in worked after the replacement certificate and that the contrast fix worked. He reported sparse Home data. That does not accept the recovery. |

Recorded evidence to read: the
[recovery evidence](https://github.com/lagarcess/argus/blob/1eca92329c62c012fc789beb3b9c973c49aaaef2/docs/reports/evidence/cuadrao-connected-preview/full-recovery/README.md)
with its dated corrections, and the Trust
[status](evidence/cuadrao-trust-20261005/orchestration/status.md) and
[gates](evidence/cuadrao-trust-20261005/orchestration/gates.md).

## Execution order

R0 to R7 and A1 to A12 are defined in #877 and are carried forward unchanged. The
points below are what to do first and what the lead must not skip.

1. **R0.** Fetch both remotes. Record integration, recovery and candidate-branch
   SHAs, which worktree is clean, and who is writing. Read back the installed
   Check and Preview identities from the device or its records before any
   install. Use the local resources below only after confirming their owner and
   health.
2. **R1.** Merge current integration one way into the recovery branch. Do not
   rebase published history and do not merge the worker into the canonical
   integration checkout. Resolve semantic overlap in the three files above by
   behavior. Keep both the financial assertions and the newer session,
   Apple-name and deletion protections. Run the merged-tree modularity check,
   compile Debug and Release, and run the affected model checks before expanding
   verification.
3. **R2 and R3** can run in parallel only when file and runtime ownership are
   separate.
   - R2 binds Home balance history, Actividad insights and primary-currency Home
     and Forecast to canonical records and coverage. Use the existing
     `FinancialLoopModel.observations(accountID:period:)` (on the recovery branch) and
     `FinancialObservationRead.swift`; do not add another transport or balance
     cache. The reader has a 64-page bound and returns incomplete, not false
     completion.
   - R3 connects `ReleaseDeleteAccountView` to the landed deletion command and
     journal, the bilingual locked copy, and the actual feature-off fallback. A
     202 or pending response is not confirmed deletion. Use the session owner for
     cleanup and signed-out completion. Register the existing
     `CuadraoReceiptStore` with the session-owned confirmed-deletion cleanup;
     do not create a second store or session state machine.
4. **R4.** Run the A1 to A12 matrix on the combined candidate. Label fixture
   comparisons and real local API journeys separately. A zero-test run is a
   failed setup. Do not weaken money, privacy or persistence assertions to get a
   pass.
5. **R5.** Ask Lucas for explicit authorization (see Publication gate below) and open the recovery PR only after his yes.
6. **R6.** Install one reviewed candidate over Check, preserve Preview, and run
   the applicable phone checks with Lucas.
7. **R7.** Land only after R6 acceptance and recorded landing authority.

**Final phone acceptance comes before authorized runtime landing.** The launch
roadmap then continues from the accepted candidate where dependencies and owners
are clear. Accepting the recovery is not TestFlight exit and not submission
approval.

## History rules for R2

Recorded-position observations with real dates and gaps are the approved first
meaning (`.agent/designs/cuadrao/DESIGN.md`, lines 257 to 267 and 390 to 404; the known-zero and `Sin datos` wording is near lines 440 to 442). One observation
has no comparison. Partial accounts are named. A confirmed zero is 0. Missing or
unknown coverage is `Sin datos`. Compare against zero with an amount difference.
Never invent a flat history, never apply today's account type or ownership share
backward, and never present future Plan projections as recorded history. Full
historical attribution is not yet a contract: the smallest proposed next contract
captures immutable attribution provenance through the existing observation
writers and leaves older intervals unknown. It needs review before any migration
or backfill and is owned by the foundations owner under #820 and #824. Escalate
that specific contract if it blocks a binding; continue the rest.

## Publication gate

An earlier automatic approval review rejected creating the recovery PR for
missing explicit permission. That rejection is still recorded. The
documentation-only grant used for this reconciliation does not cover the runtime
PR and does not authorize landing it. Do not route around the rejection through
another tool or agent. Continue independent local work, record the blocked action,
and ask Lucas for explicit authorization when R1 to R4 are complete. Do not
promote to `main` or deploy as part of this issue.

## Boundaries that stay in force

- No hosted change, migration, feature flag, paid provider call, deployment, main
  promotion or App Store submission.
- Social sign-in and account deletion stay default off. Release builds force
  Apple and Google off.
- Keep the approved details: chosen avatar in the tab bar without an added circle
  and the default icon until a choice; designed Profile rows in development;
  `Por correo` stays removed; recurring setup prepares an expected payment and
  only explicit confirmation records it as paid; receipt capture opens directly
  and Later never posts money; es-419 and English copy.
- Do not remove artwork or animation to claim performance. Compare measured frame
  hitches and time to usable content under matched device, build and fixture
  conditions. XCTest never-idle counts are not frame measurements.
- #842 owns known native test debt. #840 and #856 own the contrast and Dynamic
  Type findings, which are still unfixed on integration. Revalidate them on the
  combined build and link fixes with evidence.

## Local resources

The old chat checkout `/Users/garces/.codex/worktrees/baaf/private-alpha-next` is on `codex/native-interface-decision`, whose upstream no longer exists, and holds unrelated dirty documentation. Do not write from it, treat its files as authority, discard them or commit them into this work.

The October 5 cleanup stopped 76 containers in 15 unused projects and deleted
nothing. Retained allocations were `ios-accounts-59650` (phone),
`ios-accounts-59850` (recovery simulator) and `argus-qa` (shared QA). The
installed local CA is `Cuadrao Local Test CA October 2026` with profile
`Cuadrao Check Local Test`; verify the service and certificate before asking
Lucas to sign in again, and keep normal TLS validation. Recheck live ownership
and health before use. Keep fixtures, credentials and signing material private.
No broad prune, reset or restart. Release temporary allocations when the run
finishes. The cleanup manifest and merge preview are held in the local resume
checkpoint and are not durable evidence until committed or attached.

## What does not block the recovery

The six open product decisions in the
[reconciliation](2026-10-06-cuadrao-launch-reconciliation.md#open-product-decisions)
do not block accepted UI recovery. They gate downstream work: the scope matrix
#818, the space migration #819, consent #828, the frozen balance #805 and the
chat jobs #826, plus #798 identity policy and #803 late revocation. Business and fiscal features, Gmail, a broad Liquid Glass
redesign and advanced Profile backends are not consumer-launch requirements.

## Restart prompt

```text
You are the engineering lead for #877 in lagarcess/argus: one combined Cuadrao Check build that uses the approved Cuadrao Preview design, keeps the useful connected money actions, and carries the final Trust safety changes. Use pstack:poteto-mode.

Read first: issue #877 (execution map R0-R7, acceptance A1-A12, entry points), docs/reports/2026-10-06-cuadrao-877-recovery-handoff.md, and docs/reports/2026-10-06-cuadrao-launch-reconciliation.md on codex/private-alpha-next. Then AGENTS.md and docs/DOCUMENTATION_AUTHORITY.md.

Start at R0. Run git fetch origin. Record the current integration SHA, the recovery branch codex/cuadrao-connected-preview (1eca92329c62c012fc789beb3b9c973c49aaaef2 when last verified), and the two candidate branches codex/cuadrao-primary-home-bindings-20261005 (87a616ef0) and codex/cuadrao-primary-forecast-binding-20261005 (27dc03711). Confirm one writer per branch and shared state. Preserve Preview 3427 (local.cuadrao.design.47R3855RTJ) and all unrelated worktrees, Docker allocations and local credentials. Do not write from the old checkout /Users/garces/.codex/worktrees/baaf/private-alpha-next (branch codex/native-interface-decision, unrelated dirty documentation) and do not discard its files.

Then R1: merge current integration one way into the recovery branch, keeping the newer Apple session, first-name, journaled deletion and atomic cleanup protections (#864, #874, #875, #876). Do not rebase published history. Then R2 and R3 (separate file ownership), R4 verification, and R5 publication.

Authority: you may delegate bounded work and own the combined result. You may NOT publish the recovery PR, land runtime code, change a flag, apply a migration, call a paid provider, deploy, promote to main or submit to the App Store without explicit authorization from Lucas. An earlier automatic approval review rejected recovery PR creation; do not bypass it through another tool or agent. Continue independent local work and record the blocked action.

Final phone acceptance with Lucas (R6) comes before authorized runtime landing (R7). Keep simulator, local API, CI and phone evidence distinct. Never weaken money, privacy or persistence assertions. Report in customer terms: what Lucas can use in the Check build, what remains, what is blocked, and the next action, always naming the source, build and environment.
```
