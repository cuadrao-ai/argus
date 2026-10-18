# iPhone foundation acceptance

Simulator acceptance for [PR #729](https://github.com/lagarcess/argus/pull/729),
September 28, 2026. This is an acceptance record, not a terminal review/CI or
merge authorization. The final review and reconciliation disposition belongs
in the PR after Codex responds.

## What actually works

Five-destination navigation and selected states, header sheets and return,
local sample search with keyboard, retained in-memory search/Plan state, and
persistent Light / Dark / System appearance. Financial amounts are fixed
display fixtures. The app has no backend connection, authentication, financial
posting/persistence, business calculations, voice, sharing or provider SDK.

## Devices, source and results

Xcode 27.0 (`27A266a`), iOS Simulator 27.0 (`24A434`), arm64.

| Device | Display | Full suite | Final affected checks |
| --- | --- | --- | --- |
| iPhone 17e, `1A90F684-345F-465C-AA50-6A5298F34156` | 390 × 844 points | [5 passed](compact/test-results.json) | [2 passed](compact/search-contrast-test-results.json) |
| iPhone 18 Pro Max, `26D1423D-1F0F-44C6-88B5-5084ADDD13BF` | 440 × 956 points | [5 passed](large/test-results.json) | [2 passed](large/search-contrast-test-results.json) |

Full runs: `5adfca1f43155226f292e939f749cd8a9c8b161b`. Their app/resource tree
was `e87d161426d11fb9d993cdff608b31133b1c7d0a`.
The only subsequent app change, `143883c4412692a7f4baeb40dd0d50fd1d05ff0d`,
sets Search's placeholder to the existing semantic secondary-text color.
Final app/resource tree: `edab64f6b1e5d1c29867a9ce136158b4970615f7`.
Large-device affected checks ran at that commit; compact checks ran at
`58c23351b1663bc055563373df84e52150c1ab69`, which changes tests only.

Unchanged navigation, appearance persistence, fonts, configuration and Spanish
large-text evidence are retained. Search dark/keyboard captures were replaced;
superseded empty-search captures were removed. Per-image test, timestamp, source
commit and hash are in [compact manifest](compact/capture-manifest.json) and
[large manifest](large/capture-manifest.json). Images are unedited full simulator
captures, not HTML mockups. Later evidence-only commits preserve these source
trees; revalidate equality before using this evidence against a newer head.

## Reproduce

From repository root, with the selected simulator available:

```bash
SIMULATOR_ID=<UDID> ios/scripts/verify.sh build
SIMULATOR_ID=<UDID> ios/scripts/verify.sh test
```

The final affected check command adds:

```text
-only-testing:ArgusFoundationUITests/FoundationUITests/testDarkNavigation
-only-testing:ArgusFoundationUITests/FoundationUITests/testSearchStateSurvivesTabSwitchAndKeyboard
```

See [setup](../../../../ios/README.md). Full result bundles remain local ignored
build outputs; durable JSON results and exported PNGs are committed here.

## Observations

- All five tabs remain ordered, reachable and visibly selected on both sizes.
  The center uses the existing Argus mark. Updates/Profile remain in the header;
  empty chat has Recents left and Temporary right. Header sheets return to the
  selected destination, including Close from Preferences.
- Light and Dark persist through termination/relaunch. System stays selected
  and resolves to the OS appearance. [System readback](system-appearance.json)
  and [Light](compact/system-light.png) / [Dark](compact/system-dark.png) captures
  show the same open Preferences screen following an OS change without relaunch.
  Captured at `5714518b`; later changes affect only Search and tests.
- [Compact chat](compact/dark-argus.png), [large chat](large/dark-argus.png),
  [compact Plan](compact/dark-plan.png), [large Accounts](large/accounts.png)
  and [large Search](large/dark-search.png) show the shared visual foundation.
- [Keyboard](compact/search-keyboard.png) leaves navigation reachable above it;
  switching tabs dismisses input focus and preserves the local query.
- Spanish uses native resources. Accessibility XXXL wraps content and stacks
  amounts; screens scroll while navigation remains reachable. See
  [compact preferences](compact/spanish-large-preferences.png) and
  [large accounts](large/spanish-large-accounts.png).
- XCTest's hit-region, sufficient-description and trait audits pass on all
  five Spanish/XXXL destinations. Explicit default-size checks cover primary
  tab and Plan tab minimum targets. Amounts are announced with their context.
- The pixel contrast audit passes for Search in dark mode on both sizes.
  Whole-screen automated contrast is **not** claimed: on compact Home and chat
  it flags partially occluded text behind the floating bar or at the edge of a
  horizontal chip rail. The final test scopes this additional audit to the
  Search fix without suppressing audit issues. Home is also scrolled to show
  [the lower section clear of navigation](compact/dark-home-scrolled.png).
- Parent inspected representative light/dark, keyboard and large-type captures.
  There was no unrecoverable clipped control or horizontal page overflow in
  those checks. Scrollable content can pass under the floating material.
  Native sheets/scrolling use platform motion; no synthetic progress animation
  or network activity is implemented. Reduced transparency has a solid material
  fallback; physical-device VoiceOver and a complete WCAG audit remain unverified.

## Verification history and limits

Initial tests exposed dynamic localization-key interpolation, a missing Close
toolbar in pushed Preferences, and amount-only accessibility descriptions;
these were corrected. Local review found Plan labels with insufficient touch
width; fixed with one minimum-width rule. The first large run then exposed
subpixel frame rounding (`43.999999999999986`), resolved with a one-millionth-point
test tolerance. Failed result-bundle finalization left three Xcode runners
waiting; they were stopped and successful runs exported. Unreliable manual tab
captures were discarded/replaced by XCTest captures with selection assertions.

Source inspection confirms appearance is the only persisted preference and
there is no networking or financial arithmetic. Built Info.plist reports device
family `[1]` and platform `iPhoneSimulator`; both localization catalogs validate.
The iOS 17 deployment floor is configured, but this report verifies iOS 27 only.
No physical-device, production signing, auth/backend, live-model or hosted test
is claimed. Existing Linux repository CI does not build the SwiftUI project.

Original and fetched integration base at acceptance:
`3b9313f3dcf80e3ff9eddfcce8818a829a081225`. No intervening integration diff or
semantic overlap; no reconciliation merge needed at that check. The worker tree
therefore is the would-be merged tree, and modularity reports no violations.
Locked design reference remains #727 at
`d7faac770369242436a5e108bb557ba0bae893d3`, with the unchanged archive identified
in the [lane spec](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-09-28-ios-foundation.md).
