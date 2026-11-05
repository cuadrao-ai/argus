# Native buffered chat local verification

The native implementation is local at
`255bba8b4e732c0e9ee4e4444a2159afef6c7d6a` on `codex/consumer-buffered-chat`.
Its dedicated checkout is
`/Users/garces/.codex/worktrees/consumer-buffered-chat/private-alpha-next`.
The original saved-conversation donor remains at
`906b1612da25c0770410140e2535253300877a42` in its separate preserved checkout.

The implementation requires a fresh owner-bound capability before sending.
Missing, false, malformed or wrong-owner data denies access. It uses the
existing session request helper and canonical chat endpoint. Buffered replies
require a complete terminal response and DONE. Connected entry points cannot
use Preview answers. The existing Release gate is unchanged.

Drafts and known conversation IDs survive navigation. Known pre-POST failures
release the attempt. Uncertain writes keep their recovery data and block
another send. They never replay automatically. Recovery remains in memory;
this slice does not add a durable or definitely-unsaved resolver.

## Verification

| Source | Check | Result |
| --- | --- | --- |
| `cb61bebf0` | Complete offline ArgusSession suite | 201 tests executed, including four explicit live-test skips, zero failures |
| `cb61bebf0` | Selected chat/history/presentation models | 40 passed, zero failures |
| `cb61bebf0` | Generic Simulator Release compile | Passed, no install or launch |
| `cb61bebf0` | Full model suite | 159 tests, six failed assertions in four untouched financial tests |
| Unchanged donor `906b1612d` | Same four financial cases | Same six failed assertions reproduced |
| `255bba8b4` | Selected package transport/parser/conversation tests | 22 passed, zero failures |
| `255bba8b4` | Selected chat/history/presentation models | 42 passed, zero failures |
| `255bba8b4` | Generic Simulator Release compile | Passed, no install or launch |

The four skipped package cases require `ARGUS_SESSION_LIVE_CONFIG` for the
isolated local auth stack. They cover durable financial accounts, concurrent
refresh, invalid login/confirmation-required signup, and registered
relaunch/revocation/account switching. These are skips, not hosted acceptance.

The six baseline assertions are in `testEmptyPlanSelectionIsAnExplicitJournaledPut`
(line 772), `testPlanConfirmationSurvivesRelaunchAndDifferentOwnerCannotReplay`
(lines 721 and 723), `testPostSaveHomeWinsOverEarlierRead` (lines 357 and 359),
and `testSearchAccountNavigationAndAcceptedEditsPreserveAccountsSelection`
(line 1098). Their source did not change in this lane. The existing handoff
tracks this baseline under #898.

## Review and evidence

Initial independent review found three issues. The repair rejects data between
a terminal frame and DONE, releases known pre-POST outcomes without losing
drafts, and keeps raw terminal metadata private to ArgusSession. Failing
reproductions and the subsequent passing results remain in separate logs.
The six-file repair received a CLEAR independent review at `255bba8b4`.
Parent inspection found no additional reachable defect. The comments review
found zero added comments or deletion recommendations across the original
14-file delta. The repair adds no comments. Diff checks passed.

`initial-verification.json` and `repair-verification.json` preserve source and
local log hashes. Parent checked both sets against the retained files. The
original logs and verification record were not overwritten. Full logs remain
in the chat checkout's ignored `temp/` directory. One intermediate repair model
attempt failed to compile because of a test-fixture type annotation; that log
is retained and is not counted as passing evidence.

## Remaining delivery gates

Simulator rendering and interaction of this new chat wiring remain unverified.
No actual Full grant, provider call or hosted chat acceptance occurred. There
was no phone install, TestFlight action, Release activation or hosted change.
Integration reconciliation, publication and exact-head CI remain pending.
The latest observed integration ref is
`53d2a234bf9e73537537c24a8d35ba1e537827c1`; it was not merged into this chat lane.
