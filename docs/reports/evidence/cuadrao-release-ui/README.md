# Cuadrao release UI checkpoint

UI handoff, October 2, 2026. This checkpoint implements the founder's 17-item
presentation scope and the subsequent avatar correction. It does not establish
external TestFlight readiness or connected service acceptance.

## Integration reconciliation, October 3, 2026

Merge commit `ad0532f1` brings integration `a8c37d3a` into this branch with a plain
merge. The guide's conflict and the board and MVEE duplicates that the auto-merge
created were resolved toward the October 2 locks and the six-lane handoff. Later
commits finish the handoff's ten pickup items. Code head for this run: `c82f093d`.
Simulator: iPhone 18 Pro Max, Xcode 27. This run does not certify connected or
physical-device journeys, TestFlight readiness or any service behaviour.

- `CuadraoFirstRelease` hides the unfinished Profile rows, the avatar-editing entry
  ([decision of October 3, 2026](../../../specs/argus-decision-log.md#october-3-2026-avatar-editing-in-release)) and
  conversation bulk actions only in release builds. DEBUG builds show all of them,
  and `--cuadrao-release-gates` previews the release set in DEBUG.
- Temporary-chat memory copy follows `CuadraoFirstRelease.shows(.memory)`.
- The deletion fixture uses Iris's locked shared-plans copy verbatim. In progress
  (`202`, or `503 account_deletion_incomplete`) is a signed-out confirmation that
  never becomes the finished state. It stays a DEBUG fixture; nothing calls
  `POST /account/delete` from iOS yet.
- A Release build for the simulator compiles. Its binary contains no
  `--cuadrao-release-gates` string, and the default and `--cuadrao-design` launches
  show no Apple or Google button:
  [default](2026-10-03-w1/release-default-launch-light.png),
  [design welcome](2026-10-03-w1/release-design-launch-light.png).

Results, all on the simulator above:

| Run | Head | Result |
| --- | --- | --- |
| `verify.sh build` (Debug) | `860a6044` | Build succeeded |
| Release build for the simulator | `860a6044` working tree | Build succeeded |
| Preview state checks (`cuadrao-design-mac-pass.sh checks`) | `860a6044` | All six runners passed: 80 Home balance, 58 Plan, 50 group, 44 receipt, 213 avatar crop, 10 temporary chat. [Log](2026-10-03-w1/design-preview-checks.txt) |
| Full `verify.sh test` | `860a6044` | 146 tests: 88 passed, 47 skipped, 11 failed. [Per test](2026-10-03-w1/full-suite-860a6044.txt) |
| Focused pickup runs | pre-commit tree, then `860a6044` | [Items 1 to 4 and 7](2026-10-03-w1/focused-pickup-items.txt), [feedback reveal](2026-10-03-w1/focused-feedback.txt), [auth-on sign-in](2026-10-03-w1/focused-auth-signin.txt) |
| Focused rerun of full-suite failures | `c82f093d` | [Results](2026-10-03-w1/focused-c82f093d.txt) |

Of the 11 full-suite failures, `CuadraoHomeChartUITests.testFirstObservationAndFirstExpense`
still expected a dash for first use; `c82f093d` asserts Sin datos and the focused rerun
passes. `CuadraoReceiptPermissionUITests.testAllowedLocationCanBeRemoved` needed the
checklist's simulator location and passes once it is set. Two are in #790's area and
still fail in the focused rerun: `ReleaseUIJourneyTests.testUpdatesNoDataAndReadOnlyHistory`
(the back step after opening the first notice lands on the review root, so the Data link
is gone) and `CuadraoSupportUITests.testHomeActivityReturnsToSameRow` (the returned row
sits under the floating tab bar and is not hittable). The other seven touch code #790 does
not change (#785 planning, groups, receipts and scan, and a connected fixture test that
needs its environment) and were not investigated here.

The Mac pass `screens` step and its auth-on sign-in rerun were not run as a whole: the
shared-Mac lock order arrived first. The auth-on sign-in check passed on its own.

## Combined preview update for build 3420

PR #786 is included through integration `0ea81a208668e0391aaf008412716f6cae38826c`.
Reconciliation commit `a73c331f` includes the full Home, Search, Updates, Profile
and Settings preview, alongside #790's release views. Source/test checkpoint
`519cfa5f` passed the [combined native journeys](combined-preview-tests.json).

The preview and connected Profile now use one avatar selection/renderer and one
photo decoding/crop implementation. Photos are available in the full preview;
none keeps the tab icon, while settings show the camera circle. The full profile
editor retains name and preferred-name editing. Hold Home's greeting →
**Revisión de lanzamiento / Release UI review** to inspect pending release flows.

The confirmed-zero rule is reconciled across hero, comparison and averages.
Explicit continuous coverage with no expenses means zero, even with no expense
rows; missing coverage cannot manufacture zero. Comparisons report an amount,
never a percentage. All 80 Home projection checks passed on the combined source.
The 25 Updates and identity checks retain their unchanged-source evidence.
Modularity and whitespace checks passed after reconciliation.

- [Full Profile empty state](full-profile-empty-es.png)
- [Full Profile selected avatar](full-profile-theme-es.png)
- [Home with selected avatar](full-home-theme-es.png)
- [Shared photo crop](combined-photo-crop-dark-en.png)
- [Shared photo tab](combined-photo-tab-dark-en.png)

Cuadrao Preview **3420 is installed on the physical iPhone 15**. The device
readback confirmed name, bundle and build after installation. The signed build
uses the existing bundle `local.cuadrao.design.47R3855RTJ`, auth disabled and
`CUADRAO_DESIGN_PREVIEW=true`. A device-only copy of the canonical Info.plist sets
`CFBundleDisplayName` to Cuadrao Preview; no production configuration was changed.

The initial wireless RSD failure recovered after the user made the phone ready.
Remote launch was subsequently denied because the device locked. Installation
is confirmed; opening and interacting with this build on the physical phone is
not claimed. The user can tap the installed app. See [delivery record](device-3420.json).
No provisioning or trust settings were changed.

## Review entry

Build ArgusFoundation in Debug with `CUADRAO_DESIGN_PREVIEW=true`, then launch
`--cuadrao-release-ui`. Add `--release-dark` for dark appearance; use system
language and Dynamic Type settings for localization/accessibility review.
The DEBUG-only host has explicit fixture outcomes. Choosing an outcome does not
modify authentication, admission, Household membership or financial records.

The connected Profile uses the shared avatar editor and signed-in legal links.
Its pushed settings hide the tab bar. The connected Household admin invitation
uses the shared QR/link presentation and retains existing model commands.
Connected Updates explicitly shows unavailable until an inbox source is supplied.

## Delivered and graft boundaries

| Items | UI supplied | Service facts/actions required at graft |
| --- | --- | --- |
| 1 | Deletion consequences, code/typed confirmation, resend, pending, retry, finish | Verified deletion result, admin succession, history removal, revocation and actual sign-out; shared-plan retention follows six-lane contract |
| 2 | Signed-in legal destinations | Links derive from the existing configured web URL; live page content is not certified here |
| 3 | Apple and Google, loading/cancel/error/name recovery | Provider authentication, name persistence and pending invitation continuation; connected auth remains email until graft |
| 4–8 | Admission gate/waitlist, quota, share/code/QR, capped/expiring founder links, real Household invitation presentation | Server admission, quota, group capacity, authoritative link/code and expiry; Household membership alone does not expose accounts |
| 6, 9, 11 | Accepted/admin/history/closed notices, bill reminder and push opt-in states | Durable inbox, bill occurrence scheduler, paid/cancelled suppression, notification permission/registration and source authorization |
| 10 | Missing month distinct from recorded zero; amount delta and honest comparison availability | Existing financial history must supply coverage; missing records cannot certify zero spending |
| 12 | Muted, labelled read-only moved history | Explicit move provenance/cutoff; view-only permission does not imply an account move |
| 13–14 | No email notification toggle or unsupported settings rows; shared avatar selection | Initials/themes/photo are local session state. Hosted photo storage, profile persistence and cross-device sync remain pending |
| 15 | Disclosure, scoped data/provider facts, allow/decline and recovery | Consent version and enforcement before every model-dispatch entry; fixture provider text is not production configuration |
| 16–17 | Source disconnect and memory off/reset states | Feature availability, actual connections/memory and acknowledged mutation callbacks |

An unset Profile tab keeps its existing glyph. Selected initials/themes have no
added circle, and photos have only their circular crop. Settings/editor keep a
circular frame; the empty circle contains a camera with an add badge. Save commits
the editor draft; Cancel leaves the selection unchanged. One typed selection owns
both surfaces, applying Model the Domain rather than competing optional fields.

## Review fixes, October 3, 2026

Second worker on this branch, after the independent review of `e9195b58`. Simulator:
iPhone 18 Pro Max, every UI run focused (`-only-testing`) and under the shared-Mac lock.
Summaries of the runs are in [2026-10-03-w1b](2026-10-03-w1b/).

- `26055a28`: one release rule, `CuadraoFirstRelease.editsAvatar`, hides the avatar
  editor and with it photo selection and Reposition in release builds (review F1, and
  the founder's F2 decision). The connected Profile, the review host and the preview
  picker read it. Release keeps the profile display and the default icon. DEBUG keeps
  the full editor. `testReleaseGatesHideUnfinishedRowsAndPhotos` and the new
  `testReleaseGatesHideAvatarEditingAndPhotos` pass. A signed-in connected Profile run
  was not possible here (it needs a session), so the connected entry is covered by
  code reading only: it reads the same rule.
- `8bd88ae6` (F3), `36cafb10` (F6), `69f5ebef` (F7), `26b3e1ab` (F8 code items) and
  `5130c02d` (F5): month comparison shows Sin datos only for missing coverage; the
  covered-zero average check is back (81 Home checks pass); `--cuadrao-release-ui` is
  read only in DEBUG and the Release binary contains neither preview argument; the
  English deletion copy is pinned verbatim; the Mac pass runs `ReleaseUIJourneyTests`,
  the Updates checks (25 pass) and the new identity runner (passes).
- `6bd93b85` and `00b5be65` fix defects present on integration `a8c37d3a`: the design
  gallery's empty month read Sin datos, and money fields dropped keystrokes that
  arrived during a SwiftUI update (typing 1250.5 in one burst left 125, 150.5 or 1).
  The money journey and a one-burst typing check pass after the fix.
- Updates back navigation (`testUpdatesNoDataAndReadOnlyHistory`) still lands on the
  review root. `a488a1c6` tried value routing; it did not fix it and `81076e6e` reverts it.
  Tapping a notice row does not open the notice (the bar still reads Novedades), with or
  without marking it read; root cause open.
- `300abf54` (E8): invitation prominent labels use `WelcomePalette.onAccent`, light and
  dark: [create light](2026-10-03-w1b/invitation-create-light-es.png),
  [create dark](2026-10-03-w1b/invitation-create-dark-es.png).

## Swallowed taps, October 4, 2026

Third worker on this branch. Simulator: iPhone 18 Pro Max, every UI run focused and
under the shared-Mac lock. Summaries are in [2026-10-04-w1c](2026-10-04-w1c/).

- Cause of the three taps that did nothing: the tappable area was only the drawn
  content. A plain-style link or button ignores taps on the empty part of its label,
  and a Menu in a form row is only as wide as its text. A tap at the row's centre
  missed; a tap on the text opened it ([positions](2026-10-04-w1c/diag1-tap-position.txt)).
  This is an app defect a thumb hits too, not a test defect.
- `80a01d1b` (Updates notice rows), `74ec455c` (Home activity rows) and `fc327b03`
  (receipt Choose currency menu) give each label a rectangular content shape.
  `testUpdatesNoDataAndReadOnlyHistory`, `testHomeActivityReturnsToSameRow` and
  `testPhotoImportKeepsOriginalWithoutInventedItems` pass unchanged
  ([run](2026-10-04-w1c/focused-taps-after-fc327b03.txt)). The Home and receipt defects
  exist on integration `a8c37d3a`.
- `feaca9bf` applies the same shape to eight more rows found by
  [plain_audit.py](2026-10-04-w1c/plain_audit.py) and read by hand. They compile in Debug
  and Release; only the group entry row has a UI run.
- Group repayment: the app's cap is right. Ana owes 3,300 (3,000 house share plus 300
  of the dinner) and the sheet opens with 3,300.00
  ([values](2026-10-04-w1c/group-repayment-cap.txt)). The journey asserted in the same
  instant as its input. `3842099a` and `92fa37bc` assert the cap, that 3,301 cannot be
  recorded, and wait for Save and for the sheet to close
  ([run](2026-10-04-w1c/focused-group-final.txt)).
- `2351ea3b` picks Ana from the payer menu rather than the participant row
  ([matches](2026-10-04-w1c/receipt-payer-ana-matches.txt)); `0083a7c8` skips the shared
  planning four-kinds journey without its seeded backend
  ([run](2026-10-04-w1c/focused-tests456-0083a7c8.txt)).
- Recents rename never-idle: three fresh launches reached the alert in 1.15 s each
  ([times](2026-10-04-w1c/recents-rename-three-launches.txt)). It did not reproduce, so
  no change shipped.
- One run of the six fixed tests on the sweep tree
  ([run](2026-10-04-w1c/focused-final-sweep-tree.txt)) failed the group journey at the
  split Save, read in the instant after typing; `92fa37bc` waits for it.

## Tap-target class closed by a check, October 4, 2026

Fourth worker on this branch. No simulator and no UI test ran in this pass; another
worker held the simulators. Files are in [2026-10-04-w1d](2026-10-04-w1d/).

- The October 4 audit found 69 plain-style statements without a content shape at
  `cc68b341` ([before](2026-10-04-w1d/plain-audit-before-cc68b341.txt)). 27 took no
  taps on part of their frame: the split member toggle, the Manage spaces link, the
  outlined Sign in buttons, text links, stroke-only chips and tabs, icon buttons and
  header links. Each label now carries the rectangular content shape used in
  `feaca9bf`. The other 42 are labels that already fill or shape their frame
  ([after](2026-10-04-w1d/plain-audit-after.txt)).
- `ios/DesignPreviewTests/run_tap_targets.py` now fails the design checks when a
  plain-style statement has neither a content shape nor a reviewed reason in
  `tap_targets_reviewed.txt` ([output](2026-10-04-w1d/tap-target-check.txt),
  [checks run](2026-10-04-w1d/design-preview-checks.txt)). It reads one statement per
  `buttonStyle(.plain)` line, so a style set on a container of several buttons is
  read once. Invitations and Household are not read.
- The repayment journey waits for the field to read `3,301` before it reads the
  refusal. The Debug app compile passed
  ([tail](2026-10-04-w1d/debug-compile-tail.txt)). The Release compile and the UI
  test target compile did not run in this pass, and none of these controls has a
  focused UI run yet.

## Tap-target check corrected after review, October 4, 2026

Fifth worker on this branch, applying the delta review of `cc68b341..c45e1eb7`. No
simulator and no UI test ran. Files are in [2026-10-04-w1e](2026-10-04-w1e/).

- The voice message Cancel button kept its 80x48 frame outside a plain-style button,
  so only its text took taps. The check missed it because the style sat on the
  enclosing stack and the check read only the last button under it. The frame and a
  content shape are now inside Cancel's label, and the four container sites set the
  style on each button. Nothing visible changes.
- `run_tap_targets.py` now follows each plain style through its modifier chain to the
  statement it styles. A style on a container of controls fails and cannot be reviewed
  away. A reviewed reason of the form "X carries the shape" is checked against the body
  of X. Removing the shape from the voice bar mute button, the ordered-collection Edit
  label, Cancel, `FinancialActivityRow` or `CuadraoChoiceLabel` on a scratch copy now
  fails the check, as does moving the style back to a container
  ([script](2026-10-04-w1e/tap-target-mutations.sh),
  [output](2026-10-04-w1e/tap-target-mutations.txt),
  [check](2026-10-04-w1e/tap-target-check.txt)). The check does not judge a free-text
  reason such as "filled capsule", and identical statements still share one digest.
- The split member row is laid out as at `cc68b341` again: label, Spacer, trailing
  column. The row stays tappable through a tap area in an overlay on the Spacer, which
  takes no part in layout and stops 32 pt before the amount. A macOS SwiftUI probe
  measured the icon, avatar, name and trailing frames of the old row, the `c45e1eb7`
  row and this row over six widths, five names and both split modes: this row matched
  the old one in 60 of 60 cases and `c45e1eb7` differed in 22. Trailing padding on a
  full-width button, the smaller fix the review suggested, differed in 5 of 60, all at
  280 pt in exact mode, where the share field came out 6 to 10 pt off. Synthesized
  clicks landed in the tap area from the name's edge to 32 pt before the field and not
  after ([probe](2026-10-04-w1e/member-row-layout-probe.swift),
  [output](2026-10-04-w1e/member-row-layout-probe.txt)). The probe runs on macOS with
  stand-in children, so an off-centre tap on the iPhone simulator is still owed.
- Debug, Release and test-target compiles passed for the simulator
  ([commands and results](2026-10-04-w1e/compiles.txt)), and the design checks passed
  ([output](2026-10-04-w1e/design-preview-checks.txt)).

## Feedback Save under the keyboard and the Release preview argument, October 4, 2026

Sources `3ed8dae0a`. Simulator: iPhone 18 Pro Max only. Files are in
[2026-10-04-w1f](2026-10-04-w1f/).

- `CuadraoProfileFollowupUITests/testFeedbackPreservesKindsAndPartialDrafts` failed on
  the combined candidate `4af8fced` on iPhone 18 Pro because of the test's `reveal`
  helper, not the app. The helper reads the keyboard element's frame as the top of the
  keyboard. That frame begins below the 44 pt Typing Predictions bar, and a drag that
  starts on the bar does not scroll the form. On iPhone 18 Pro the helper's drag began
  at y 551 with the bar's top at y 550
  ([candidate frame](2026-10-04-w1f/candidate-4af8fced-pro-save-under-keyboard.png)).
  On iPhone 18 Pro Max it began 7 pt above the bar, so it passed there.
- The [probe](2026-10-04-w1f/feedback-keyboard-geometry.txt) measures it: drags that
  start 10, 30 and 43 pt above the keyboard frame move nothing, and a drag that starts
  51 pt above scrolls the form and leaves Save
  [above the keyboard and tappable](2026-10-04-w1f/save-above-keyboard-pro-max.png).
  A person can reach Save with the keyboard up.
- The keyboard-aware helper arrived in `fd408c62c`. The integration baseline passed
  with no software keyboard on screen, so it never exercised this path.
- Fix `620d6a39a`: the helper's floor is the top of the prediction bar. The test body is
  unchanged. [Focused runs](2026-10-04-w1f/focused-runs.txt): the feedback test passed
  twice alone and once in its class (6 of 6). **Not rerun on iPhone 18 Pro**, the
  device where it failed; with the fix the drag there starts at y 506, 44 pt above the bar.
- Never-idle waits: `CuadraoContextUITests/testGroupContextPreservesDraftAttachmentsAndReturn`
  ran alone with none (52.8 s). The feedback test logged 5 in one of four runs, starting
  after text entry with the software keyboard up. No cause established and nothing changed.
- `3ed8dae0a`: only DEBUG builds read `--cuadrao-design`. A Release build launched with
  the argument now opens exactly as a default launch
  ([screenshot](2026-10-04-w1f/release-design-argument-launch.png), byte-identical to the
  default launch), and its binary no longer contains the string
  ([compiles](2026-10-04-w1f/compiles.txt)). This supersedes the October 3
  `release-design-launch-light.png` reading above. A standalone preview build still uses
  `CUADRAO_DESIGN_PREVIEW=true`; `--design-gallery` and `--home-populated` remain in the
  binary and are read only inside that preview.
- Debug, Release and build-for-testing compile;
  [design preview checks](2026-10-04-w1f/design-preview-checks.txt) pass.

## Correction: split member row tap area, October 4, 2026

Sources: `9493ea575` with the overlay removed. Simulator: iPhone 18 Pro only. Files are in
[2026-10-04-w1g](2026-10-04-w1g/).

- Correction to the October 4 tap-target entry above. The claim that the split member
  row's overlay "stops 32 pt before the amount" was wrong on iOS. It came from a macOS
  mouse probe with stand-in children. On the iPhone 18 Pro simulator the candidate
  `2520da49` probe toggled the member with taps up to 16 pt before the amount or share
  field, and stopped toggling at 12 pt. A tap just short of a share field could take that
  person out of a money split.
- The overlay from `567f59819` is removed. The row is again identical to `cc68b341` and
  integration `a8c37d3a`, and only the drawn member label toggles. Next to money fields, a
  near-miss must not change who is in the split. The row is listed in
  `tap_targets_reviewed.txt` as deliberately label-only. A wider row would be a design
  decision. The tap-target check passes with 44 of 44 reviewed.
- The [probe](2026-10-04-w1g/split-row-boundary-probe.swift.txt) ran on the simulator
  in both split modes ([output](2026-10-04-w1g/split-row-boundary-probe.txt)). Taps on
  the icon, avatar and name toggle. Taps up to 20 pt past the label's edge also toggle
  (system touch tolerance). Taps at 22 pt and beyond do not. No tap from 44 pt before
  the field up to the field toggled. The closest toggling tap is now about 85 pt before
  the share field (exact) and 153 pt before the amount (equal). With the overlay these
  distances were 16 pt.
- `CuadraoGroupDesignUITests/testSharedJourneySpanish` passed three runs in a row, and
  `CuadraoReceiptUITests/testExpenseEditsSurviveReceiptCapture` passed once
  ([runs](2026-10-04-w1g/focused-runs.txt)). One link to the earlier in-suite failure at
  line 48 is possible but not proven. That test's `reveal` swipes up from the screen
  centre. On an exact-split row that point lies between the label and the share field,
  where the removed overlay took taps.
- Debug, Release and build-for-testing compile ([compiles](2026-10-04-w1g/compiles.txt)).
  The [design preview checks](2026-10-04-w1g/design-preview-checks.txt) pass.

## Two in-suite UI failures diagnosed, October 4, 2026

Sources: `4bb1696a3` (reproduction), `a72c3033b` and `211b3d732` (test changes). Simulator:
iPhone 18 Pro only. Every simulator run held the shared lock with
`-collect-test-diagnostics never`. Files are in [2026-10-04-w1h](2026-10-04-w1h/). The
evidence came from the two candidate suite result bundles (`4af8fced`, `2520da49`):
synthesized-event records, the UI hierarchy at failure, and the screen recordings.

- `CuadraoVoiceDesignUITests/testLockedRecordingAndCleanAttachments`, line 155. Test
  defect, fixed in `a72c3033b`. The test closed the attachment tray and at once pressed
  `chat-composer-entry`. In both suite failures the press landed at y 509.8 or 527.6, the
  entry's tray-open position. In every passing run it landed at y 662
  ([coordinates](2026-10-04-w1h/voice-press-coordinates.txt)). The recordings show why.
  In the failing run the tray was still open 0.37 s after the close tap and the press
  coordinate was read then. In the passing run the tray was already closing when the
  coordinate was read, 0.30 s after the tap
  ([failing](2026-10-04-w1h/voice-close-tap-failing-pair.png),
  [passing](2026-10-04-w1h/voice-close-tap-passing-alone.png)). XCUITest's idle wait
  returned before the app applied the close. The press hit empty space and no recording
  started.
- Reproduced with the suite predecessor `testHoldComposerAndWaveformWithoutStartingLiveVoice`
  in the same run: 1 failure in 5 pairs (2 unloaded, 3 under 14 busy processes), with the
  same y 509.8. Alone it passed 2 of 2. After an unrelated predecessor it passed. Hold and
  Locked as two separate runs passed. The in-run state that slows the close after Hold is
  not identified. The fix does not depend on it.
- The fix waits for the tray's Escanear row to leave, waits for the press target to stop
  moving before each lock gesture, and waits for the review panel to leave after
  Descartar. No assertion changed. The predecessor pair then passed 3 of 3, with the first
  press at y 662 each time. (The run helper also started two busy processes during those
  three runs by mistake; it was corrected afterwards.) The Escanear wait adds about 1 s,
  because XCUITest polls non-existence about once a second.
- `CuadraoGroupDesignUITests/testSharedJourneySpanish`, line 48, `2520da49` suite only.
  Not reproduced; cause narrowed. At failure, Ana's share was DOP 40,300.00, the editor
  said "Hay DOP 40,000 de más.", all five members were included and Save was correctly
  disabled. The recording shows the six deletes typed at 60 characters per second turned
  "400.00" into "40", not empty, and the typed 300 made 40300
  ([frames](2026-10-04-w1h/group-ana-share-suite-failure.png)). Two deletes had no net
  effect. This rules out the removed overlay (no member was dropped) and a late Save
  enablement (the split was over).
- Two mechanisms remain: a SwiftUI update rewrote the field from a stale binding during
  the burst (the `CanvasMoneyValueInput` re-sync class; by reading, its re-sync writes two
  decimals, which does not explain a plain "40"), or two synthesized deletes were not
  delivered under load. Tries that did not reproduce it: the predecessor pair
  (`testSampleCardSaveImage`, then the journey) twice under 14 busy processes, the whole
  Group class once, and a throwaway probe that replaced and read back Tú's and Ana's
  shares 48 times, half under load, with 0 mismatches
  ([probe](2026-10-04-w1h/W1hSplitDiagnosticUITests.swift.txt)).
- `211b3d732` makes the group journeys read back every money field they replace, so a
  recurrence fails at the field with the value it holds. To tell the two mechanisms apart
  next time, log each keystroke and each field rewrite in `CanvasDecimalInput` during a
  full suite. That needs an app change and was not made without a reproduction.
- Pending checks at `211b3d732`: `ReleaseUIJourneyTests` 13 of 13 passed; the Mac pass
  auth-on welcome check (`testDefaultLaunchOffersNoAppleSignIn`, auth-on loopback build,
  social flags off) passed; build-for-testing (Debug) succeeded for each change. CI on
  `4bb1696a3` was green. `git diff --check a8c37d3a...HEAD` is clean. Raw results are in
  [runs](2026-10-04-w1h/runs-raw.txt).

## Money keystroke probe under a stalled main thread, October 4, 2026

Source: `c2b47c661`, with throwaway DEBUG instrumentation that was never committed. Simulator:
iPhone 18 Pro only, every run under the shared lock with `-collect-test-diagnostics never`.
Files are in [2026-10-04-w1i](2026-10-04-w1i/). This follows the `testSharedJourneySpanish`
entry in the section above.

- Question. Can money entry undo a keystroke? Two candidates were open: the
  `CanvasMoneyValueInput` re-sync rewriting the field from a stale value when the main
  thread stalls, and the silent refusal in `CanvasDecimalInput` when a keystroke's range
  does not fit the field's text.
- Not reproduced. The [probe](2026-10-04-w1i/W1iMoneyStallProbeUITests.swift.txt) replaced
  and read back a split share and the expense amount, and Tú's and Ana's shares in a freshly
  opened editor, 344 times in four runs. Three runs had a repeating main-thread stall of 60
  to 150 ms or 250 to 600 ms. The app handled 3,180 keystrokes, 2,224 of them stalled, and
  582 while earlier writes were still queued. Every keystroke was accepted, none was refused
  at the range guard, none was sent without being handled, no update rewrote a non-empty
  field and no re-sync was requested ([results](2026-10-04-w1i/probe-results.txt)).
- The re-sync window did not open. Of 1,571 value writes that changed the value, 80 had a
  later keystroke already handled and its write queued. In all 80 the change report ran
  before that queued write, 2 to 8 ms after the value write, with nothing but view updates
  between them. The re-sync needs the queued write to land first.
- The heavy run logged one mismatch. It was the probe's own read timing out under 250 to
  600 ms stalls. The app's log for that burst shows six deletes handled and an empty field.
- Still open: two synthesized deletes not being delivered under whole-machine load. The
  stall slows the app only, so it does not test that.
- To settle a recurrence, apply the
  [instrumentation](2026-10-04-w1i/stall-and-log-instrumentation.diff.txt) to a throwaway
  build, add `-W1iLog` to the UI tests' launch arguments, run the suite, and run
  [summarize](2026-10-04-w1i/summarize.sh.txt) on the app log. A burst with fewer handled
  keystrokes than sent means an undelivered key. A `REWRITE` onto a non-empty field or a
  `REFUSED` line means the app.
- No app change. Both Swift files equal `c2b47c661`, so no build was rerun.

## Verification and evidence

- Initial acceptance used iPhone 18 Pro simulator, iOS 27. The combined update above records the later physical installation.
- Nine distinct native journeys have passing evidence. The integrated run passed
  eight and missed the photo picker with a fixed-coordinate tap. The test now
  waits for the native photo image accessibility element. All three avatar journeys
  then passed, including photo selection → crop → Save → tab → reopen.
- Native coverage includes Spanish, English, large Dynamic Type, dark photos,
  deletion resend/cancel/pending/finish, social cancellation/name recovery,
  invitation full/quota presentation, Updates/no-data/read-only and AI decline.
  Correction, October 3, 2026: `testUpdatesNoDataAndReadOnlyHistory` does not pass.
  It failed in the full suite at `860a6044`, in the focused reruns at `c82f093d` and
  `e9195b58`, and on the review-fix tree; see "Review fixes, October 3, 2026" above.
  The avatar journeys above predate the release rule in `26055a28`, which hides avatar
  editing and photos in release builds.
- 25 Updates checks, 79 Home projection checks and identity-state checks passed.
  Swift macro compilation required running outside the nested process sandbox.
- Modularity budget passed on the reconciled tree. Diff whitespace checks passed.
- QR decoding was checked by the invitation worker with Vision for custom-scheme
  and universal URLs. No external acceptance or short-code service was invoked.
- Independent deletion delta review returned clean after the resend and cancellation
  repairs. Final avatar review inspected actual screenshots, catching and fixing an
  unsupported camera symbol before these final captures.

[Integrated test summary](integrated-tests.json) records the original selector
failure; [avatar retest](avatar-tests.json) records its resolution. Passing evidence
for the six unaffected journeys is retained. Screenshots below are committed,
not temporary-only evidence. This applies Prove It Works to the native result.

| Evidence | What it shows |
| --- | --- |
| [Empty profile](profile-empty-circle-es.png) | Settings camera circle beside unchanged Profile tab |
| [Theme avatar](theme-tab-unframed-es.png) | Framed settings avatar and unframed tab artwork |
| [Default restored](avatar-default-restored-es.png) | Circular empty editor and native trailing selection check |
| [Large text](avatar-initials-large-en.png) | English initials and accessibility text size |
| [Photo crop](photo-crop-dark-en.png) / [photo tab](photo-tab-dark-en.png) | Native picker/crop and selected photo in dark appearance |
| [Deletion pending](deletion-pending-es.png) / [cancelled verification](verification-cancelled-en.png) | Recovery controls and cancellation return |
| [Social name](social-name-en.png) | Missing-name recovery without fake authentication |
| [Invitation full](invitation-full-es.png) / [quota](personal-invitation-es.png) | Waitlist and personal-invitation presentation |
| [Bill notice](bill-notice-es.png) / [data truth](no-data-moved-history-es.png) | Reminder detail and no-data/read-only specimens |
| [AI consent](ai-consent-en.png) | Scoped sharing explanation and decline action |

## Initial integration and review disposition

- Original integration base: `58ace0f74d81df41f23244a82ad98ad1c736f061`.
- Current fetched integration: `900178b32df1b25a08f8d15bdbbe82485ae61c80`.
- One-way reconciliation merge: `e893bacac47ffdacf34d403a2a855f5e0bb9d093`.
- Final runtime/test source: `cda15b03c7702428e27a5d47028af6ec5f71cf97`. Following evidence/roadmap changes are
  documentation-only and do not change the verified source.
- Semantic overlap: integration added Plan, receipts, contextual chat and preview
  activation. The palette conflict preserves `CuadraoDesignPreview.isActive` and
  the DEBUG review appearance. No API, migration, permission, environment contract,
  analytics or model instruction changed in this lane. The full nine-journey run
  followed reconciliation; the final avatar delta reran its three affected journeys.
- No merge to integration, deployment, hosted operation, live OAuth/deletion/AI,
  physical-phone journey or external TestFlight submission was performed.
- GitHub CI status belongs to the PR. This is a UI handoff, not a READY report.

The [main execution board](../../../specs/argus-execution-board.md#cuadrao-release-ui-landing-order)
owns remaining delivery work. The [design guide](../../../../.agent/designs/cuadrao/DESIGN.md)
owns stable patterns and the visually inspected Mobbin references.
