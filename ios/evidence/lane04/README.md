# Lane 04 iOS follow-ups

Owner: Lane 04 sole iOS writer. Base and refreshed integration: `6bfa52658c86175e2382e60c9fe9bc9459dbf189`.
This is signup polish; it unblocks no direct step of the three-receipt goal and lands after that goal. No merge or release is included.

## Result

- #1166: create-account acceptance requires both terms and privacy URLs. Each single-document fixture hides the sentence and both links in connected and explicit design-preview screens. Published URLs remain empty.
- #1165: contribution deletion uses the shell toast owner. Red swipe deletes immediately, with no confirmation dialog. Deshacer restores the contribution count and remaining amount. Its measured accessibility frame is at least 44 by 44 points. The shared close identifier is `toast.close`, labelled Cerrar in Spanish.
- The shared toast wraps its message above the controls at accessibility sizes. Moving the minimum action frame inside the button label fixes the reproduced 18-point accessibility target.
- Perfil keeps its existing wording with straight apostrophes. The existing guest first-entry note stays one-time; a second-launch test proves it does not return. No persistent home banner was added.

Tradeoff: all toast callers share one close identifier and accessible layout. Existing callers were updated together. Detection signal: the UI tests check the target bounds, dismissal label, contribution count, acceptance visibility, and second-launch state. The owning Cuadrao DESIGN.md, HIG and WWDC26 guide informed the shared toast reuse, direct Undo and scalable controls; no new visual system was introduced.

## Local verification

All screenshots use es-419. The current source passed **24 UI test executions, zero failures** on iOS 27:

| Run | Tests | Evidence |
| --- | ---: | --- |
| SE | 7 | [xcodebuild output](logs/final-se.log) |
| iPhone 16 | 7 | [xcodebuild output](logs/final-16.log) |
| Pro Max | 7 | [xcodebuild output](logs/final-promax.log) |
| iPhone 16 contribution Undo, AX5 and dark appearance | 1 | [xcodebuild output](logs/final-ax5-dark.log) |
| Local connected Perfil, unpublished links | 1 | [xcodebuild output](logs/local-connected-profile.log) |
| Local connected Perfil, owner-supplied links | 1 | [xcodebuild output](logs/local-connected-links.log) |

The seven-test matrix selects these methods in `FinancialLoopUITests`:

```
testGuestPlansInSpanish
testSignUpHidesAcceptanceAndLinksWhenOnlyOneDocumentExists
testSignUpHidesTheLegalLinksUntilThePagesArePublished
testSignUpShowsTheLegalLinksFromTheOwner
testSignUpRemainsReachableAtLargeTextSizes
testSpanishGuestToastWrapsAtLargeTextSizes
testSpanishModeLineDoesNotReturnOnSecondLaunch
```

Source files: `GuestPlansUITests.swift`, `CuadraoLegalLinksUITests.swift`, `GuestNoticesUITests.swift`. Signup and the first guest toast run at Large, XXXL and AX5 on all three devices. An additional contribution-delete run uses `ARGUS_TEST_CONTENT_SIZE=UICTContentSizeCategoryAccessibilityXXXL ARGUS_TEST_APPEARANCE=dark`.

Each retained log includes the full `xcodebuild test` command and named test results. Common options: `-project ios/ArgusFoundation.xcodeproj -scheme ArgusFoundation -configuration Debug -parallel-testing-enabled NO CODE_SIGNING_REQUIRED=NO -collect-test-diagnostics never`, with each named method selected using `-only-testing:ArgusFoundationUITests/FinancialLoopUITests/<method>`. The real Cuadrao build gate stayed enabled. No legacy preview-build bypass was used.

`python3 ios/DesignPreviewTests/run_cuadrao_legal_urls.py` passes Debug and Release checks; test overrides remain Debug-only. `python3 scripts/check_modularity_budget.py` and `git diff --check` pass. The changed source fingerprint and ordered paths are in [source-sha256.txt](source-sha256.txt); evidence-only changes do not change that source.

Connected tests used the expressly supplied ignored local config, loopback API/auth and two synthetic local users. The documented isolated local stack was created for this lane. No paid providers were enabled. This proves local native email/password flows only; it is not hosted staging, external-provider auth or physical-phone evidence. FinancialModelTests were not selected, so their historical failures are not claimed as resolved or waived.

## Screenshots

Measured files are listed in [image-dimensions.json](image-dimensions.json). SE is 750×1334 pixels, 375-point width. iPhone 16 is 1178×2556 pixels, approximately 393-point width, rather than the brief's nominal 390. Pro Max is 1320×2868 pixels, 440-point width.

| Device | Before toast | After toast | Before one-document signup | After signup/text-size set |
| --- | --- | --- | --- | --- |
| SE | [before](before-se/aporte-eliminado-deshacer-es.png) | [after](after-se/aporte-eliminado-deshacer-es-normal.png) | [before](before-se/registro-un-documento-terms-vista-previa.png) | [after set](after-se) |
| iPhone 16 | [before](before-16/aporte-eliminado-deshacer-es.png) | [after](after-16/aporte-eliminado-deshacer-es-normal.png) | [before](before-16/registro-un-documento-terms-vista-previa.png) | [after set](after-16) |
| Pro Max | [before](before-promax/aporte-eliminado-deshacer-es.png) | [after](after-promax/aporte-eliminado-deshacer-es-normal.png) | [before](before-promax/registro-un-documento-terms-vista-previa.png) | [after set](after-promax) |

[Actual contribution toast at AX5](after-16-ax5-dark/aporte-eliminado-deshacer-es-UICTContentSizeCategoryAccessibilityXXXL.png) wraps the message without clipping. Connected Perfil light and dark captures are in [local-connected-profile](local-connected-profile).

Dark screenshots were captured. **Dark Mode support: NOT CHECKED**, as directed. Spanish labels and minimum target dimensions were asserted. The existing shared toast posts a VoiceOver announcement and uses opacity with no animated slide when Reduce Motion is enabled; source paths were inspected. Audible VoiceOver output and the OS Reduce Motion toggle were not manually verified, so those runtime checks remain notes for independent Eval.

## Baseline and runner classification

Before screenshots temporarily used the original toast, create-account and guest-plan implementation at the integration base, then final sources were restored before all final runs. The new assertions reproduced the original single-document acceptance bug and 18-point Undo target. These are fixed by the final source.

The first SE selection used iOS 26.5, where the existing swipe implementation does not expose the iOS 27 path; that run is not current runtime-regression evidence. The full iOS 27 SE run passes. A baseline SE attempt also showed target amount zero because keyboard focus was not ready; the UI helper now waits for the keyboard and reselects the field before typing. [Baseline screenshot](baseline-notes/se-plan-target-zero.png) is retained. No amount-handling product change was made. Final logs above supersede earlier attempts; there are no remaining failures in the selected current matrix.

## Review and release boundary

No CI gate exists for this iOS lane; named local xcodebuild output is the required substitute. Independent exact-head Eval and any later landing belong to the coordinator. The branch must remain frozen after DONE. No production, main, hosted configuration, public legal page or model call was changed.
