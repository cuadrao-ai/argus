# Issue #784 Cuadrao design graft: Mac pass checklist

This is the checklist for the Mac pass over the four-PR graft of design checkpoint
`codex/cuadrao-design-scan-recents` @ `2558f866`. Every PR in the series was written on a
Linux box without Xcode. This pass is the first time the series builds, runs in a simulator
and is compared against integration before the graft. Tracking issue: #784.

| PR | Scope | State |
| --- | --- | --- |
| #783 | Shared foundation | Landed as `5dd2e36d` |
| #785 | Plans, groups, receipts, chat and voice | Landed as `900178b3` |
| #786 | Home, Search, Updates, Profile, Settings | Landed as `0ea81a20` |
| PR 4 | Design tests, launch arguments, this checklist | Open against `codex/private-alpha-next` |

The baseline is `2185aefe`, integration just before #783.

## Before you start

- Xcode 27 with an iOS 27 iPhone simulator. `CuadraoOrderedCollection` uses the iOS 27
  swipe and reorder APIs, so older Xcode releases will not build it.
- Note the simulator UDID: `xcrun simctl list devices available`.
- Two receipt journeys import a photo
  (`CuadraoReceiptUITests.testPhotoImportKeepsOriginalWithoutInventedItems`,
  `testGroupPhotoImportInheritsFixedCurrency`). Seed the simulator with one fictional
  receipt photo first: `xcrun simctl addmedia <UDID> <photo>`.
- Give the simulator a location before the tests run, so
  `CuadraoReceiptPermissionUITests.testAllowedLocationCanBeRemoved` gets a place to attach:
  `xcrun simctl location <UDID> set <lat>,<lon>` (any fictional point, for example
  `18.4861,-69.9312`).
- #790 merged integration `a8c37d3a` (merge `ad0532f1`), so its avatar and zero-month
  behaviour is what the tests now check.
- Optional: `brew install imagemagick` to count differing pixels between screenshots.

## Run

From the repository root, on the PR 4 branch:

```bash
SIMULATOR_ID=<UDID> ios/scripts/cuadrao-design-mac-pass.sh all
```

The steps can also run separately as `checks`, `tests` or `screens`. Output goes to
`ios/.build/mac-pass/<UTC stamp>/`, which git ignores. The
script (removed; see tag `archive/ios-personal-2026-10-30`) only builds, runs tests and
takes screenshots. It doesn't sign, upload or call a backend. A failing step doesn't stop the
later ones: `all` always runs `checks`, `tests` and `screens`, prints `FAILED <runner>` or
`<step>: FAILED` for each failure, and exits non-zero at the end if anything failed.

### 1. Preview state checks (`checks`)

The script runs every `ios/DesignPreviewTests/run_*.py` with `xcrun swiftc`. On the box,
`run_linux.py` already ran the same checks with Swift 6.3.3 for Linux. These are the
counts the Mac run should match:

| Runner | Expected |
| --- | --- |
| `run_plan_preview.py` | Passed 58 Plan preview checks |
| `run_group_preview.py` | Passed 50 group preview checks |
| `run_home_balance.py` | Passed 80 Home balance projection checks |
| `run_receipt_preview.py` | Receipt preview checks passed: 44 |
| `run_avatar_crop.py` | Avatar crop checks passed: 213 |
| `run_temporary_chat.py` | 10 `PASS:` lines, Spanish and English |

On integration alone, `run_home_balance.py` doesn't compile `CuadraoBalancePeriod.swift`
(`HomeBalanceChecks.swift:145`: cannot find 'CanvasBalancePeriod'). #790 carries the runner
fix, so on the #790 branch this runner is expected to pass.

### 2. Design UI tests (`tests`)

The script runs `CuadraoHomeChartUITests`, the 13 grafted design UI test classes and
`CuadraoSignInPresentationUITests` through
`ios/scripts/verify.sh test`. It then exports their screenshot attachments to
`ui-attachments/`. Every design launch now passes
`--cuadrao-design --cuadrao-home --home-populated` (`CuadraoPreviewLaunch.arguments`),
which is what a standalone `CUADRAO_DESIGN_PREVIEW = true` build implied on the design
branch. Without those arguments the tests open the Connected app.

These tests are expected to skip on a simulator:

- `CuadraoSignInPresentationUITests.testDefaultLaunchOffersNoAppleSignIn` in the main run.
  The default build has auth off and never shows Connected sign-in. The script runs it again
  in its own auth-on build (loopback placeholder URLs, both social flags forced off, and
  `TEST_RUNNER_ARGUS_TEST_AUTH_UI_ENABLED=true`), where it must pass.
- `CuadraoVoiceDesignUITests.testVoiceChoiceAndProposalHandoff`. Voice selection needs
  `--cuadrao-voice-selection` and the sample clips, which stay out while their licensing
  is unsettled. `testVoiceProposalHandoffWithoutVoiceSelection` covers the rest of that
  journey and checks that no picker is offered.
- `CuadraoReceiptUITests.testPhysicalScannerPresentationAndCancel`. The document camera
  needs a physical device.

Location, camera and photo-save prompts come from the simulator. The permission journeys
answer them through Springboard.

### 3. Before/after screenshots (`screens`)

The script builds `BASELINE` (default `2185aefe`) in a temporary worktree, then this tree.
Both builds pass `ARGUS_AUTH_ENABLED=false CUADRAO_DESIGN_PREVIEW=false` to `xcodebuild`.
The baseline worktree has no copy of the ignored `ios/Config/Local.xcconfig`, so without the
pin a local override would apply to the after build only. Each build gets a clean install
and a fixed status bar. It takes these screenshots in
`screens/`:

| Screenshot | Launch arguments | Expected difference from baseline |
| --- | --- | --- |
| `before/after-default-light` | none | None. Connected keeps its fixed tokens. |
| `before/after-default-dark` | none | None. |
| `before/after-design-light` | `--cuadrao-design` | Welcome only. Separator and border use the system separator inside the preview. |
| `before/after-design-dark` | `--cuadrao-design` | The baseline forced light. After, the preview's dark tokens apply. |
| `after-design-home-light/dark` | `--cuadrao-design --cuadrao-home --home-populated` | New in #786 |
| `after-design-gallery-light/dark` | `--cuadrao-design --design-gallery` | New in #786 |

`compare.txt` lists each before/after pair. Any difference in a `default` pair is a
regression in the live app.

## Manual checks

The automation doesn't cover these. Record each result in #784.

1. **Connected, signed in, against the baseline.** Check Priya's shared-code value swaps
   from #783: `WelcomePalette.pine`/`sage`/`separator`, the Registration heading, button
   and field, the navigation bar's glass tint and the Home section font.
2. **No preview side effects without the flag (#785).** Launch with no flag and use the
   app. No `Application Support/CuadraoReceipts` folder and no `cuadrao-groups.json` should
   appear in the app container (`xcrun simctl get_app_container <UDID> local.argus.foundation data`),
   and no location prompt should appear.
3. **Release gate for the permission keys.** Camera (receipt scan), location (receipt
   place) and photo-add (save the sample group card) are requested only inside the design
   preview. Before any TestFlight or App Store build, those requests must be reachable in
   the shipped app, or `NSCameraUsageDescription`, `NSLocationWhenInUseUsageDescription`
   and `NSPhotoLibraryAddUsageDescription` come out. The photo-add strings are marked
   `REWORD` for when group cards are real.
4. **First-release presentation (#787, #790).** In a release build, Profile shows no
   Personalization, Security, Shared conversations, Removed activity, Memory, Usage, More
   options or photo option. A DEBUG build shows every one of them; launch it with
   `--cuadrao-release-gates` to preview the release set
   (`CuadraoProfileFollowupUITests.testReleaseGatesHideUnfinishedRowsAndPhotos`). Search has
   no Memory perspective and temporary chat drops its memory copy through the same
   `CuadraoFirstRelease.shows(.memory)` gate. Notifications has no "Por correo". The preview
   sign-up and sign-in screens show no Apple or Google button, and password-recovery help
   doesn't mention Apple.
5. **Chart truth.** A month with confirmed complete coverage and no spending shows 0, and a
   comparison against it is an amount, never a percent. "Sin datos" shows only when coverage
   is missing. `CuadraoHomeChartUITests.testSpendingEmptyAndUnavailable` asserts both.
6. **Physical device (optional).** Scan, save for later and reopen a receipt. The design
   branch's founder check covered this on build 3419. This graft hasn't been on a device.

## Sign-off

Comment on #784 with the PR 4 head SHA, Xcode and simulator versions, the check counts,
UI test pass/skip/fail counts with failing test names, `compare.txt`, and the manual
check results. Attach or commit the screenshots you want to keep next to this README.

The design branch's own verification for the checkpoint is
[continuity-2026-10-02 at `2558f866`](https://github.com/lagarcess/argus/blob/2558f86666d2c9a0fb2336225a02aed4f18077b2/docs/reports/evidence/cuadrao-native-design/continuity-2026-10-02/README.md).
It is the founder's evidence for the design branch, not for integration. This checklist
doesn't copy it.

## Native Apple and Google sign-in (#795) Mac pass

This list is rebuilt only from durable sources: the 5-step #795 entry on #784
([issuecomment-5965182186](https://github.com/lagarcess/argus/issues/784#issuecomment-5965182186),
head `96b550f1`) and the Mac-dependent gates in #800. An 8-step version was described in
the handoff but was never recorded anywhere durable, on GitHub or in the repo. It is not
reconstructed here from memory, and no step below comes from it.

From the #795 entry on #784:

1. **Default build, switches off.** Run `SIMULATOR_ID=<UDID> ios/scripts/verify.sh build`.
   Xcode first fetches GoogleSignIn-iOS 9.2.0 and its seven dependencies. Expect no visible
   change: no Apple or Google button, and the email flow unchanged. If Xcode rewrites
   `Package.resolved` (originHash), commit it.
2. **Compile risk spots.** `ios/ArgusFoundation/Auth/NativeProviderSignIn.swift`:
   `SignInWithAppleButton`, the GIDSignIn async
   `signIn(withPresenting:hint:additionalScopes:nonce:)`, the `GIDSignInError` cancel check
   and `UIWindowScene.keyWindow`. Also `ProfileAuthModel.signIn(with:appleAuthorizationCode:)`.
3. **Google, simulator.** Set `ARGUS_GOOGLE_SIGN_IN_ENABLED=true`,
   `GOOGLE_SIGN_IN_IOS_CLIENT_ID` and `GOOGLE_SIGN_IN_IOS_URL_SCHEME` in `Local.xcconfig`,
   and add both Google client ids in Supabase. The button appears only when the scheme
   matches the client id. Sign in, and expect Connected Home with the `/me` profile.
4. **Apple, device only.** Enable the capability on the App ID, use
   `CODE_SIGN_ENTITLEMENTS = Config/SignInWithApple.entitlements` in `Device.local.xcconfig`
   and set `ARGUS_APPLE_SIGN_IN_ENABLED=true`. Sign in, and expect Connected Home. With #793
   deployed and `CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED=true`,
   `POST /api/v1/auth/apple/authorization-code` returns 204.
5. **Screenshots, before and after.** The create-account and sign-in screens with the
   switches off, which should be identical, and on.

From #800, the gates that need a Mac:

6. **Credential state on launch.** Handle `getCredentialState` and revoked Apple credentials
   on launch (#800 gate 5).
7. **Release force-off.** Release inherits the ignored `Local.xcconfig`. A release-build
   gate, with a CI check, must keep both flags from shipping on by accident (#800 gate 3).
8. **Flag-aware `testDefaultLaunchOffersNoAppleSignIn`.** With auth and either flag on, its
   label check matches the new buttons. Make it flag-aware (#800 gate 4). The Mac pass
   script runs it with both flags forced off.
9. **Privacy manifest.** Add `PrivacyInfo.xcprivacy`, check whether the GoogleSignIn, AppAuth
   and GTMAppAuth SDKs ship their own manifests, and mark email and user ID as linked in the
   privacy labels (#800 gate 8).
10. **Dark-mode buttons.** The Apple button is always `.black` and Google always `.light`.
    Adapt both to dark mode (#800 gate 9).

Items 3, 4 and 6 need keys or a device and are open. Items 7 to 10 are #800 work, not
checks the current code passes. The October 3 #790 run recorded in the
[release UI evidence](../cuadrao-release-ui/README.md) covers item 1 and the switches-off
half of item 5 on a simulator only.
