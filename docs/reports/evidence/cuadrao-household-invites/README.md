# Cuadrao iPhone: Household and beta invitation journeys

**Code head this folder describes:** `3c7d7f2710b01a3a799714b1e7f8d6bec8e6e41a` on
`claude/cuadrao-household-invites-ios` (review fixes for `R-household-6fb15a01`, plus a plain merge of
`origin/codex/cuadrao-release-ui` at `e9195b587`). The commit that updates this folder changes only
files under it.

**Which screenshots vouch for which head:**

| Screenshots | Captured at | Status at `3c7d7f27` |
| --- | --- | --- |
| `gate-ready-*`, `gate-invalid-*`, `gate-rate-limited-*`, `link-saved-signed-out-*`, `invitations-hub-*`, `admitted-link-return-es-light` | `031ad3cd` | Still stand. The screens they show did not change, and the tests that produce them passed again at `3c7d7f27`. They were not re-exported. |
| `personal-invitation-created-*` | `031ad3cd` | Stand only for a server with `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED` on, which returns a link. The default server returns `link: null`; see `personal-invitation-code-only-es-light`. |
| `access-unanswered-es-light`, `personal-invitation-code-only-es-light` | `3c7d7f27` | New. |

The older branch history: `031ad3cd018a77e1672366e9cde044d4087dadf9` was the plain merge of
`origin/codex/cuadrao-release-ui` (`c82f093d5`) into the lane's first code head
`1051c7f829890ca4c29396f407499efc5ba8cfbd`. The branch started at
`ad0532f11a6c3c199c9c6d82a01329dd0bddafcc` (W1's merge of integration `a8c37d3a`).

**Simulator:** iPhone 17e, iOS 27 simulator, UDID `8B7975F1-1338-4966-90E2-770416CAF174`, Xcode 27.0.

## Final pass at `a10f6b5c4`

Code head `a10f6b5c46b21d7c6dd21a8c63fb71e1ba5a38d5` closes the five P3s in `R-household-3c7d7f27`
and plainly merges `origin/codex/cuadrao-release-ui` at `3370ba509`.

- **Household-scoped not-found.** The synchronous handler that ended membership is private. Every
  Household-scoped failure goes through `resolveAccessFailure`, and a `household_not_found` ends
  membership only when the membership read (`GET /households/{id}`) agrees. The plan path shares the
  same read. Detail, history, Search, the Search reload after a plan write, the activity editor's load
  and review, and activity writes are each covered by `run_household.py`, plus a membership read with
  no answer. Before the fix, the editor load, editor review and Search reload cases ended membership.
- **Handed-over invitation.** The hand-off from the gate or a link now previews the invitation in
  `HouseholdModel.beginJoin`, and a model test covers it. The view only shows the handed-over text.
  The earlier "covered by model tests" claim was not true when it was made, because the preview was
  triggered from view code.
- **Screens.** No screenshot was re-exported. The #790 merge gives prominent invitation labels the
  on-accent ink, so the Share and Create buttons in `personal-invitation-created-*` and the gate's
  Continue button in `gate-*` now render lighter than these files show.
- **Runs at `a10f6b5c4`.** `run_household.py` 46 of 46, `run_invitations.py` 21 of 21, ArgusSession
  package 104 tests with 4 skipped and 0 failures, Debug and Release builds succeeded, and the focused
  `InvitationsUITests` run passed 18 of 18 under the Mac lock.

## Last fix pass at `a02e7d3ec`

Code head `a02e7d3ec294d9dbac7e49c8a38c3f5efaa24985` closes scope A of `R-candidate-4af8fced` and
plainly merges `origin/codex/cuadrao-release-ui` at `cc68b341e` (no conflict).

- **Unshare message (A-1).** An unshare bumps the Household version, so the reload inside
  `open(_:)` started a new access generation and dropped "household.changed". The message now
  depends on the same session, the same selection, an available surface and no message already set.
  `testAnUnsharedAccountLeavesTheListAndSaysPermissionsChanged` failed before the fix with
  `errorKey == nil`. A reload that turns Households off now keeps no message, and the existing
  reload test covers that case.
- **Join step review (A-3, A-6).** Closing management cancels the invitation review. A preview
  answer that lands after a cancel or a newer preview is dropped. `beginJoin` returns false when its
  own preview turned Households off. Both new tests failed before the fix.
- **Link over the introduction (A-4).** The introduction adopts a handed-over code on change as
  well as on appear. This is view code with no host test; the UI tests below cover the join step.
- **Harness kind (A-5).** The DEBUG harness answers `group_link` only for `FULL` secrets, so
  `beta-link-…` previews and redeems as `beta`. No client branch reads it.
- **`accessEnded()` (A-2)** is private.
- **Runs at `a02e7d3ec`.** `run_household.py` 49 of 49, `run_invitations.py` 21 of 21, ArgusSession
  package 104 tests with 4 skipped and 0 failures, Debug and Release simulator builds succeeded. UI tests
  were not run in this pass, because the simulators were reserved for another agent.

## What these screenshots are, and what they are not

They come from `ios/ArgusFoundationUITests/InvitationsUITests.swift`. The tests launch the Debug app
with `--invitations-harness`, which shows the connected invitation screens and the real
`InvitationsModel` over `InvitationsStubServer`. The stub answers `/api/v1/invites` only in shapes the
real routes produce, checked against the live local run recorded in
`~/.claude/orchestrate/cuadrao-iphone-candidate/reports/W7-live-invites.md`: redeem of an expired,
used, revoked or full secret is a `409`, preview of the same secret is `200` with `available: false`,
a new beta invitation has `link: null` unless the harness is launched with `--harness-server-links`,
and a server failure is the transport's codeless "no answer". A typed code picks the outcome, for
example `EXPD-…`.

They are simulated acceptance. They do not prove a round trip against a local or hosted API. No
local backend was started for this lane, because worker W4 holds the local Supabase stack. The
request list for a live round trip is in the lane report.

The sign-in screen in the signed-out shots is a stand-in inside the harness. The real sign-in flow
is `ConnectedCuadraoAuthFlow`, which shows the same saved-invitation notice above it.

Connected Cuadrao keeps light welcome tokens in every appearance (`WelcomePalette.adaptsToAppearance`),
so the gate pages look the same in the dark shots. System screens, such as the Invitations list,
follow dark mode.

## Screens

Every name ends in `-es-light`, `-es-dark`, `-en-light` or `-en-dark` (es-419 and en).

| File prefix | State |
| --- | --- |
| `gate-ready` | Signed in, the server gate is on and the account has not been admitted |
| `gate-invalid` | A code that names no invitation (`404 invitation_not_found`) |
| `gate-rate-limited` | Too many lookups (`429 invite_rate_limited`) |
| `link-saved-signed-out` | A cuadrao.ai invitation link opened while signed out. The intent waits for sign-in |
| `invitations-hub` | Sent invitations with server states (accepted, not accepted yet), and the founder's group links (full with waitlist overflow, expired) |
| `personal-invitation-created` | A new beta invitation: quota from the server, code, link and QR, and "sharing is not acceptance" |
| `admitted-link-return-es-light` | An admitted person opens a beta link. Nothing is redeemed and they return to the app |
| `access-unanswered-es-light` | The first `/invites/access` check got no answer. The app stays closed and offers a retry |
| `personal-invitation-code-only-es-light` | A new beta invitation in the default server shape: code only, no link and no QR |

## Rerun

```bash
lockf -k ~/.claude/orchestrate/cuadrao-iphone-candidate/mac-sim.lock env SIMULATOR_ID=<udid> RESULT_DIR=<new dir> \
  ios/scripts/verify.sh test -only-testing:ArgusFoundationUITests/InvitationsUITests
python3 ios/FinancialModelTests/run_invitations.py   # InvitationsModel on the host, no simulator
python3 ios/FinancialModelTests/run_household.py     # HouseholdModel on the host, no simulator
```

`capture.sh` reruns the UI tests and replaces every file in `screens/`. Use it only when all
screenshots should be re-captured at one head.
