# iPhone chart validation evidence

This folder contains simulator evidence for the standalone chart prototype, not
physical-iPhone or production certification. The exact committed capture head is
in `captured-head.txt`; `source-identity.json` records every iOS source and shared
fixture/presentation-palette SHA-256. Evidence-only follow-up commits preserve those tested inputs.

Final capture: **f5f4f4467fe53c3a1990cda9574b353c8b72d83f**. Build and all eight
UI tests passed, fixture model checks passed, and every captured source/fixture
hash was revalidated equal. System Light/Dark screenshots were visually inspected.
Earlier local captures are superseded by this evidence.

## Environment and isolation

- Host: Mac17,9, Apple M5 Pro, 48 GiB RAM, macOS 27.0 (26A428).
  Shared development host, not an isolated physical-device benchmark.
- Xcode 27.0 (27A266a); Apple Swift 6.4; Swift 5 language mode; iOS 27 SDK.
- Swift Charts is the Apple system framework (no separate package version).
- iPhone 17e simulator, iOS 26.5 (23F77), 1170×2532 screenshot pixels.
- Dedicated instance `Argus Chart Validation 17e`, UDID
  `AAC78F82-61C2-4E51-A14C-4F341CD19A79`.
- Native-auth's running simulator and all shared devices/resources were untouched.
- iOS 17.0 configured deployment floor compiles. No local iOS 17 runtime exists;
  that minimum is **unverified at runtime**. No physical-device claim.

## Repeat and inspect

From repository root, with your owned device UDID and a new result bundle path:

```sh
prototypes/chart-validation/ios/capture-evidence.sh \
  AAC78F82-61C2-4E51-A14C-4F341CD19A79 \
  /tmp/argus-chart-ios-final.xcresult
```

The script runs build/UI tests, exports screenshots/test summary/performance,
runs fixture model checks, launches System appearance, changes this simulator's
OS appearance Light→Dark while the app remains running, captures both, restores
Light, and records source identity. It leaves the dedicated simulator running for
inspection; shut down **only that instance** after proof:

```sh
xcrun simctl shutdown AAC78F82-61C2-4E51-A14C-4F341CD19A79
```

`attachments.json` maps exported screenshots to XCTest identifiers, device and
timestamps. `test-summary.json` is the machine-readable outcome and
`xcodebuild-test.log` is the build/test receipt. `model-checks.txt` records endpoint,
nearest/tie, explicit-null segment, missing-row selection and lifecycle checks.

## What the tests prove

- `testReadoutEndpointsMissingResetAndLocale`: shared-fixture first point, explicit
  missing row, last endpoint clamp, reset, English→es-419, Dark appearance.
- `testHorizontalReleaseAndVerticalScroll`: real injected horizontal drag updates
  readout; release retains it. A chart-originated vertical drag moves the chart's
  screen Y by more than 40pt **before** any other scroll action, keeping selection.
- `testNativeRecognizerCancellationRestoresSelection`: a real injected horizontal
  drag starts; the standalone test hook disables the active recognizer, causing
  UIKit to emit `.cancelled`. The prior selected date is restored. This proves
  native callback handling, not every possible OS interruption source.
- `testScenarioResetsSelection`: changing scenario clears selection and empty
  scenario disables point navigation.
- `testEmptySingleAndContribution`: empty state, single negative point with clamped
  navigation, and authored recurring-contribution readout in Spanish/Dark.
- `testLongSeriesInteractionPerformance`: five real automated scrubs over the
  2,000-row fixture, including resulting selection checks and screenshot.
- `testScenarioPickerUsesLocalizedFixtureTitles`: Spanish and English option titles
  derive from the shared fixture while selection retains stable machine IDs.
- `testEnlargedTextReadoutAndTouchTargets`: at accessibility-medium Dynamic Type,
  selecting a point preserves relative readout/chart geometry; point-navigation
  buttons remain at least 44pt high and the primary amount stays inside the screen.
- `system-light.png` and `system-dark.png`: app set to System responds to OS
  appearance change without relaunching between the two captures.

Accessible alternative proof is the visible date/value readout and labeled native
Previous/Next/Reset buttons exercised by accessibility-driven XCTest. No precision
dragging is required. This is not a full physical-device VoiceOver audit.

## Performance interpretation

`performance.json` contains every raw sample, including XCTest clock, application
CPU and physical memory measurements. An iOS26+ UI hitch metric was requested,
but this simulator exported no hitch samples; **unavailable is not zero hitches**. Clock includes touch injection
and automation overhead. CPU is application CPU time, memory is process footprint,
and no frame/hitch claim can be made from the absent hitch export. They are
not interchangeable with chart-only latency or physical-device FPS. There is no
accepted regression baseline or device FPS threshold in this prototype.

For five long-series scrubs, mean automated interaction clock was **1.169 s**,
mean application CPU time **0.976 s**, and mean peak physical memory **47,345 kB**.
Individual clock samples ranged **1.066–1.262 s**. These include automation and
injected drag duration; no chart-only latency or frame-rate conclusion follows.

## Product-style prototype checks

These are bounded visual checks on the recorded iPhone17e simulator, separate
from physical-device/performance readiness. Thirteen screenshots supersede the
prior engineering-harness appearance.

| Check | Result and evidence |
| --- | --- |
| Localized controls | Met: menu labels use fixture titles, never machine IDs; bilingual XCTest passes. |
| Typography | Met: bundled licensed Space Grotesk Medium headings and Inter body; font registration assertions pass at app launch. Font bytes/licenses are unchanged from read-only #729 reference. |
| Palette and contrast | Met: marks and swatches load `visual-style.json` directly. Against white, actual/projected strokes are 3.78:1/3.66:1; against #191c1f they are 6.11:1/6.32:1. Small labels/readouts use neutral ink. Solid/dashed strokes and point shapes keep non-color meaning. |
| Hierarchy and spacing | Met: chart/readout first, synthetic label visible, 24pt page inset and restrained spacing; diagnostic controls and UTC/unit notes live below in Chart lab. Flat neutral surfaces; no decorative shadow/card chrome. |
| Stable readout and touch targets | Met at default and accessibility-medium text: fixed primary-amount slot, monospaced digits, >=44pt capsule controls; accessibility-size controls stack without clipping. Full range of Dynamic Type sizes remains unverified. |
| Axes and edges | Met: sparse horizontal grid; short localized dates use nontruncating labels with greedy collision omission and scaled edge space. Normal Spanish and enlarged screenshots contain no clipped date ellipses. Full selected date remains in the readout. |
| Empty and single point | Met: empty chart has no fabricated date axis; single negative amount stays visible with clamped navigation. |
| Motion | Met for the bounded interaction: no custom tweening/flashing/implicit chart animation. The recording shows real native horizontal selection followed by vertical page scrolling. OS Reduce Motion was not separately toggled; no app-owned animation requires a fallback. |

## Short motion proof

[`scrub-and-scroll.mp4`](scrub-and-scroll.mp4) records only the chart app while
XCTest drives its existing horizontal-release/vertical-scroll test. Recording
starts after the first chart gesture begins and stops at the vertical-scroll
attachment; the additional test passed. The 3.02-second recording decoded successfully,
and inspected beginning/end frames contain only the chart app. It is a visual demonstration, not an FPS
measurement. `motion-identity.json` records head/device/result provenance.

Reproduce after the full capture build, from repository root with the owned device
still booted:

```sh
python3 docs/reports/evidence/chart-validation/ios/record-motion.py \
  AAC78F82-61C2-4E51-A14C-4F341CD19A79
```

## Recommendation and limits

**Adopt Swift Charts as the iPhone rendering direction for further bounded work.**
The framework builds with the actual native toolchain and renders shared facts,
explicit gaps, actual/projection styles and accessible selection with the required
native gesture coexistence. Keep the explicit selection lifecycle and shared data
contract; do not spread charts into production screens based on this prototype.

Remaining limits: unavailable simulator hitch/FPS measurements, iOS17 runtime,
physical-device performance/VoiceOver, broader
Dynamic Type/device sizes and exhaustive OS interruption scenarios were not
certified. Xcode27's documented conditional ChartContent issue for older deployment
targets is avoided by using ForEach mark arrays; no unsupported workaround or
alternative library was silently substituted.

Cleanup verified in `cleanup.txt`: the dedicated simulator is **Shutdown**. Its app/test
bundles remain inside it, alongside disposable `/tmp/argus-chart-ios*` build/result exports.
No provider keys, production accounts, hosted writes or shared resource restarts.
