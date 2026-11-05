# Cuadrao overnight integration landing, October 5, 2026

The founder authorized an unattended overnight run on October 4 to implement,
review and land three bounded tracks into `codex/private-alpha-next`, after first
landing documentation PR #835. This record lists what landed, how each PR was
verified, and what remains. It does not mark the app launch-ready, enable any
feature, or claim hosted or physical-phone acceptance.

## What landed

Integration started at `76b6afcb4080c6e639e8c50bdabf51621d862190` and ended at
`19f0dc3af36f2912f0eadec79dbe2adf430b7ac8`. Each PR merged by squash with
`--match-head-commit` on its reviewed head; each integration tree equals that
head.

| Order | PR | Merge SHA | Reviewed head | What it changes |
| --- | --- | --- | --- | --- |
| 1 | [#835](https://github.com/lagarcess/argus/pull/835) | `7e0c0b1d99c71bf121f3891beab56e74087668c2` | `358924d77` | Founder constitution sources reconciled into canonical docs (docs only). |
| 2 | [#837](https://github.com/lagarcess/argus/pull/837) | `f655d131bb10aeb31b02fe062ce78c7600fcd952` | `0f0491197` | #811: explicit client grants on 17 early tables, one grant-matrix test, CI on pinned and latest Supabase CLI. |
| 3 | [#838](https://github.com/lagarcess/argus/pull/838) | `ec666c96c40ba9dce900f5eca9b4cf2a829472d1` | `4db514491` | Set up a recurring payment from a movement; Home Upcoming on its own rolling 30-day window. |
| 4 | [#836](https://github.com/lagarcess/argus/pull/836) | `7ddb9cdbba364f710d7848492c62626aa74199d4` | `2a9c8322f` | Real-API proof of the recurring-to-confirmed-payment contracts; no backend change. |
| 5 | [#839](https://github.com/lagarcess/argus/pull/839) | `19f0dc3af36f2912f0eadec79dbe2adf430b7ac8` | `1f0a393b9` | Home movement taps open detail; account and movement row gestures. |

## Verification

Every PR had an independent review by a model that did not write it, posted on
the PR. Fix commits written after a review, including the coordinator's own,
had a second independent check before landing. Branches absorbed integration
by merge; none was rebased.

- #837: the full real-Postgres suite gave 626 passed and 1 failed on Supabase
  CLI 2.109.0 (postgres 17.6.1.140) and on 2.119.0 (postgres 17.11.0.002). The
  failure is a local macOS scipy import that also fails on the base. Without
  the migration, the latest CLI had 5 grant-related failures. Both CI legs
  passed on the PR head.
- #836: the recurring-plan journey passed 11 checks with 77 assertions against
  local Auth, API and Postgres. The backend Plan suites gave 67 passed on local
  Postgres. Evidence:
  [recurring-plan proof](evidence/overnight-2026-10-05-recurring-plan/README.md).
- #838: on the iPhone 18 Pro simulator (iOS 27.0) with a local connected stack,
  at its exact head: the recurring journey and Spanish copy each ran 1 test
  with 0 failures. At the head before the final error-routing fix:
  response-loss retry saved once, the Plan baseline test passed,
  ReleaseUIJourneyTests ran 13/0, and ArgusSession ran 111 tests with
  0 failures.
- #839: the same simulator at its exact head: three gesture journeys 1/0 each
  and ReleaseUIJourneyTests 13/0. The reviewer also ran CuadraoCollectionUITests
  6/0 and the account-swipe fallback on an iOS 26.5 simulator.
- Native screenshots:
  [overnight native evidence](evidence/overnight-2026-10-05-native/README.md).
- Integration CI passed at `7e0c0b1d9`, `f655d131b`, `ec666c96c` and
  `7ddb9cdbb`, each with Private Alpha Local Smoke.

Review findings fixed before landing included a Home occurrence sheet closing on
refresh, Plan and Home reads failing together, a failed shared read showing no
error on Home, and a movement swipe that could do nothing.

## Limitations kept explicit

- A recurring expectation does not carry the movement's category; the
  expectation contract has no category field.
- No stored link from an expectation back to its source movement. Link
  candidates also offer that movement; it is never auto-selected.
- Personal Plan only. The space migration (#819) was not started.
- Connected Home has no account reorder and no order field. None was invented.
- Native evidence is simulator only. There is no iOS CI.

## Remaining gates

- #811 stays open for hosted application after the pending migrations, the
  before and after hosted grant readback, and the production migration gate's
  maintenance review (it classifies `revoke` as contract-replacing). New hosted
  functions remain executable by `PUBLIC` by default; per-function revokes stay
  the guard.
- #822, #824 and #829 stay open; only bounded slices landed.
- Physical-phone and hosted acceptance were not attempted. The phone was
  unavailable.
- New findings: #840 (dark appearance makes primary text near-invisible),
  #841 (flaky canary session test), #842 (pre-existing native suite failures).

No environment variable was added to the application. The CI workflow gained a
workflow-level `ARGUS_CI_SUPABASE_CLI_VERSION` pin. No `main` promotion,
deployment, hosted database change, flag change, secret change, paid model call
or build distribution was performed.
