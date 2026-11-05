# Standalone Swift Charts prototype

Synthetic rendering and selection only. Open `ChartPrototype.xcodeproj` with
Xcode. No package download, signing account, provider key or native shell changes.
`../fixtures/series.json` is a direct PBX resource reference for application and
tests. Xcode packages those same bytes; no fixture copy is maintained here.

## Compatibility checked September 28, 2026

- Installed Xcode 27.0, build 27A266a; Swift compiler 6.4, Swift 5 language mode.
- Swift Charts is Apple's system framework, linked from iOS 27 SDK. There is no
  independently pinned package version. Test runtime is iOS 26.5 (23F77).
- Configured iOS 17.0 floor follows open #729's setup. **Not minimum-OS certified**:
  only iOS 26.5 and 27 simulators exist locally; iOS 17 runtime and physical-device
  proof are absent. No deployment to a physical iPhone was attempted.
- Open #727 supplies approved chart direction; #729 supplies Xcode project shape.
  Neither branch was merged or assumed shipped. This project has its own build
  configuration, application ID and dedicated simulator.

Official Apple references checked before implementation:
[Swift Charts](https://developer.apple.com/documentation/charts),
[ChartProxy](https://developer.apple.com/documentation/charts/chartproxy),
[interactivity and selection](https://developer.apple.com/videos/play/wwdc2023/10037/),
[gesture direction admission](https://developer.apple.com/documentation/uikit/uigesturerecognizerdelegate/gesturerecognizershouldbegin(_:)),
[Xcode 27 release notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-27-release-notes).
Apple's iOS 17 selection API and custom proxy overlays support this direction.
The implementation uses a directional UIKit pan recognizer because the prototype
contract explicitly distinguishes release, cancellation and vertical scrolling.
The Xcode 27 release notes flag `ChartContent` conditionals with older deployment
targets. Chart marks here use arrays and `ForEach`; no conditional ChartContent.

## Behavior

Actual solid and projected dashed series have independent contiguous
segment IDs. Explicit nulls split paths and remain selectable. Points make isolated
samples visible. Lines are linear; values/contributions come only from JSON.
Dates use a Gregorian UTC civil-date parser and formatter; numbers use en-US or
es-419 with explicit ISO currency codes and two decimals.

Horizontal gestures choose nearest date, clamp endpoints, and resolve ties earlier.
UIKit rejects vertical recognizer starts so the parent page scrolls. Release retains;
recognizer cancellation or application deactivation restores pre-drag selection.
Previous/Next inspect every row without dragging, Reset clears, scenario change
clears; theme/language preserve selection. Chart visuals expose a concise accessible
label, while the date, three value readouts and buttons remain separate accessible
controls. This is accessible-control proof, **not a full VoiceOver user study**.

Static chart rendering is isolated from the dynamic selection overlay. Selection
search is binary over parsed dates; clients do not compute financial facts.

## Run

From repository root, select only an owned simulator. Initial proof used:
`AAC78F82-61C2-4E51-A14C-4F341CD19A79`, named `Argus Chart Validation 17e`.

```sh
xcrun simctl create 'Argus Chart Validation 17e' \
  com.apple.CoreSimulator.SimDeviceType.iPhone-17e \
  com.apple.CoreSimulator.SimRuntime.iOS-26-5
xcodebuild -project prototypes/chart-validation/ios/ChartPrototype.xcodeproj \
  -scheme ChartPrototype -sdk iphonesimulator \
  -destination 'id=YOUR_OWN_DEVICE_UDID' \
  -derivedDataPath /tmp/argus-chart-ios \
  -resultBundlePath /tmp/argus-chart-ios-proof.xcresult \
  test CODE_SIGNING_ALLOWED=NO -parallel-testing-enabled NO
xcrun swiftc -module-cache-path /tmp/argus-chart-model-cache \
  prototypes/chart-validation/ios/ChartPrototype/ChartData.swift \
  prototypes/chart-validation/ios/verify-model.swift -o /tmp/argus-chart-model
/tmp/argus-chart-model prototypes/chart-validation/fixtures/series.json
```

Use a fresh resultBundlePath for repeat runs. Test launch environments select case,
language and appearance only. `CHART_CANCEL_DRAG=1` is a standalone UI-test hook:
after a real drag starts, it disables the pan recognizer so UIKit sends native
`.cancelled`. This tests the actual cancellation callback, not an invented touch
state. It does not certify every possible OS interruption source.

Long-series performance records five automated drags with XCTest clock, app CPU,
app memory and requests (iOS 26+) [UI hitch metrics](https://developer.apple.com/documentation/xctest/xcthitchmetric).
The tested simulator exported no hitch samples; absence is not zero hitches.
Clock includes injected touch duration and test automation, not just renderer time.
There is no physical-device FPS claim or regression baseline.

Evidence and measured performance: `docs/reports/evidence/chart-validation/ios/`.


## Visual prototype acceptance

The chart is the primary surface; scenario/language/appearance and UTC/unit
provenance sit in a labeled Chart lab below it. Flat neutral backgrounds,
Space Grotesk Medium headings, Inter body/readout text, capsule point-navigation
controls with a 44pt minimum, and sparse horizontal grid lines derive from
DESIGN.md and the approved #727 reference. Licensed native font bytes and OFL
licenses are copied unchanged from read-only #729 at
`b422d986bcf068b56e07283481de373ba8e30dc0`; no dependency on its shell is created.

The chart directly packages `../fixtures/visual-style.json` as its one series
palette owner. Actual/projected describe observation kind, not gains or losses.
Light-theme stroke contrast against white is 3.78:1 actual / 3.66:1 projected;
dark-theme contrast against #191c1f is 6.11:1 / 6.32:1. Small legend/readout text
uses neutral ink, not muted stroke colors. Solid/dashed paths and distinct point
shapes preserve non-color meaning.

A fixed-height primary amount slot and monospaced digits keep the readout stable.
Dynamic Type scales bundled fonts; navigation buttons stack at accessibility
sizes. The focused enlarged-text test checks readout/chart relative geometry and
44pt touch targets. There are no custom tweening, flashing, smoothing or implicit
chart animations; selection follows touch directly, so there is no app-owned
animation to disable under Reduce Motion. Native control transitions remain OS
owned. These checks do not claim all text sizes, all devices or physical readiness.
