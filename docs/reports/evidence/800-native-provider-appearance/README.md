# Native provider appearance evidence

October 5, 2026. Bounded implementation evidence for #800 item 9, with #803 as related identity context. Independent release-captain review remains separate.

## Scope and source

- Original integration base: `a6688eea10895d9f57664f1ece8a7eba96503732`.
- Current fetched integration: `26c0692d634953bd542a6cca6504138e6e420e6c`.
- Tested source and reconciliation merge: `99b903090881e741a093b30fde5d00a9df2d7863`.
- Reconciliation merged #846, which changes recovery Python tests and documentation only. There is no shared native runtime, API/data contract, UI state owner, migration, environment variable or directly affected test. Appearance evidence remains valid; the final matrix ran again to strengthen footer capture, not because integration invalidated it.
- `ConnectedProviderButtons` reads SwiftUI `ColorScheme`. Apple selects its official white/black variant; Google selects its official dark/light variant.
- The same connected entry form now uses system background and primary foreground colors. Its footer action uses primary foreground too. The captain approved these local prerequisites after screenshot inspection; the global palette is unchanged.
- Provider order, labels, nonce handling, busy disabling, cancellation handling and accessibility identifiers retain their existing owners. No auth-model or session-controller changes.

The data shape is the existing `ColorScheme` enum. Model the Domain favored using that owner directly instead of introducing another appearance model. The delegated worker kept one isolated checkout, simulator and DerivedData directory. The read-only scoped review returned zero actionable findings and zero comment changes after the final source update.

## Baseline gap

The baseline matrix used the unchanged integration application and the new structural screenshot test. All 16 cases passed visibility/order/name checks; those assertions alone do not establish appearance correctness. The screenshots show the defect directly.

- [Dark English create account](baseline/signup-en-dark-standard.png) still has a white canvas, black Apple button and light Google button. Secondary footer text also loses contrast.
- [Dark Spanish Accessibility XXXL](baseline/signup-es-419-dark-accessibility.png) shows the pre-existing clipped Google label.
- [Light English sign in](baseline/signin-en-light-standard.png) records the existing light treatment.

Changing only Apple's style would put its white button on the same fixed white canvas. That reachable mismatch justified adapting the form's two surface colors. The next capture exposed the fixed pine footer action on black; changing that local action to primary foreground corrected it.

## Verification

The final synthetic Debug run uses an owned iPhone 18 Pro simulator with iOS 27.0. Public client identifiers are fabricated. All configured service URLs use `127.0.0.1:9`; no backend, authentication, provider, or paid-model call is part of the test. No provider button is tapped.

Reproduce from the repository root with an isolated simulator UUID exported as `SIMULATOR_ID`, then run `bash docs/reports/evidence/800-native-provider-appearance/verify-command.sh`.

The appearance matrix is both entry forms × English/Spanish × light/dark × standard/Accessibility XXXL, for 16 scenarios. It checks existence, enabled state, hittability, Apple-before-Google-before-email ordering, complete accessible provider names, and complete footer visibility after scrolling. Screenshots record both the initial viewport and the footer after any required scroll. The final xcresult reports 3 passed tests, 0 failures and 0 skips, with 32 screenshots. Color and visible-text acceptance require screenshot inspection; the UI assertions do not compare colors or pixels.

The configuration check is `python3 ios/DesignPreviewTests/run_native_provider_config.py`. It passed 11 Debug and 11 Release cases, including Google requiring Apple and Release force-off. `python3 scripts/check_modularity_budget.py` passed on the would-be merged tree, after the normal reconciliation merge.

## Limits

The pinned official GoogleSignInSwift 9.2.0 dark variant is blue with white text. This uses the provider's SDK style without recoloring its mark.

Google's visible label clips at Accessibility XXXL before and after this change, especially in Spanish. Its accessible name remains complete. This evidence does not close full Dynamic Type acceptance; [#856](https://github.com/lagarcess/argus/issues/856) owns that pre-existing defect.

Busy and cancelled provider flows are unchanged but were not exercised by provider interaction. VoiceOver audio and real-provider physical-phone acceptance were not performed. These checks do not authorize social flag enablement, release distribution, hosted changes or deployment.

The first footer check used hittability, which allowed a partly visible accessibility-size footer. Image inspection caught that test gap. The final test requires the entire footer frame inside the viewport before capture. This correction changes verification only.

## Screenshot index

Visual inspection confirms the selected provider variants and readable adaptive form/footer colors. The known Google accessibility-size clipping remains visible.

| Scenario | Form | Complete footer |
| --- | --- | --- |
| signin-en-dark-accessibility | [Image](after/signin-en-dark-accessibility.png) | [Image](after/signin-en-dark-accessibility-footer.png) |
| signin-en-dark-standard | [Image](after/signin-en-dark-standard.png) | [Image](after/signin-en-dark-standard-footer.png) |
| signin-en-light-accessibility | [Image](after/signin-en-light-accessibility.png) | [Image](after/signin-en-light-accessibility-footer.png) |
| signin-en-light-standard | [Image](after/signin-en-light-standard.png) | [Image](after/signin-en-light-standard-footer.png) |
| signin-es-419-dark-accessibility | [Image](after/signin-es-419-dark-accessibility.png) | [Image](after/signin-es-419-dark-accessibility-footer.png) |
| signin-es-419-dark-standard | [Image](after/signin-es-419-dark-standard.png) | [Image](after/signin-es-419-dark-standard-footer.png) |
| signin-es-419-light-accessibility | [Image](after/signin-es-419-light-accessibility.png) | [Image](after/signin-es-419-light-accessibility-footer.png) |
| signin-es-419-light-standard | [Image](after/signin-es-419-light-standard.png) | [Image](after/signin-es-419-light-standard-footer.png) |
| signup-en-dark-accessibility | [Image](after/signup-en-dark-accessibility.png) | [Image](after/signup-en-dark-accessibility-footer.png) |
| signup-en-dark-standard | [Image](after/signup-en-dark-standard.png) | [Image](after/signup-en-dark-standard-footer.png) |
| signup-en-light-accessibility | [Image](after/signup-en-light-accessibility.png) | [Image](after/signup-en-light-accessibility-footer.png) |
| signup-en-light-standard | [Image](after/signup-en-light-standard.png) | [Image](after/signup-en-light-standard-footer.png) |
| signup-es-419-dark-accessibility | [Image](after/signup-es-419-dark-accessibility.png) | [Image](after/signup-es-419-dark-accessibility-footer.png) |
| signup-es-419-dark-standard | [Image](after/signup-es-419-dark-standard.png) | [Image](after/signup-es-419-dark-standard-footer.png) |
| signup-es-419-light-accessibility | [Image](after/signup-es-419-light-accessibility.png) | [Image](after/signup-es-419-light-accessibility-footer.png) |
| signup-es-419-light-standard | [Image](after/signup-es-419-light-standard.png) | [Image](after/signup-es-419-light-standard-footer.png) |

## Evidence retention and cleanup

Publication commits after the tested merge change evidence files only. `git diff 99b903090881e741a093b30fde5d00a9df2d7863 HEAD -- ios` is empty, explicitly revalidating the captured native inputs. The owned simulator `8988E923-2C87-40F7-B878-E834554C1947` was shut down and deleted after capture. Build products and xcresult bundles remain local for review; no fixture server was started.
