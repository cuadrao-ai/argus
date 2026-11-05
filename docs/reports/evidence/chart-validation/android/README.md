# Android Vico prototype evidence

**Prior-layout evidence.** Current visual and performance acceptance is in
[axis-precision/README.md](axis-precision/README.md). The files below remain
unchanged for provenance. In particular, prior OS-theme screenshots captured a
previous compositor frame; revised captures supersede those visual theme claims.


Capture head: `f93e11d7e639b77b5ffd82ec9d04076bdb6dd713`.
Capture date: September 28, 2026. Local emulator evidence only.
`provenance.json` records every Android source hash, shared fixture hash and both
APK hashes. The fixture packaged in the app was verified byte-identical to the
sole committed JSON. No production/native-shell files changed.

## Result and recommendation

**CHANGE before adoption.** Keep Vico as the Android candidate, but resolve its
newer dependency graph with the Android build owner and improve/remeasure the
long-series interaction before copying this adapter into product screens.

- Build, two unit tests and Android lint pass (`final-verification.txt`,
  `unit-tests.xml`, `lint-verification.txt`).
- All five instrumented tests pass at this head (`instrumentation.txt`).
- Both APK installs succeeded; direct instrumentation retained files until their
  durable pull (`install-receipt.txt`, `pull-receipt.txt`).
- Straight actual lines and dashed projected lines preserve independent gaps;
  explicit dates/values, nulls, singleton points and weekly contribution facts
  come from the shared fixture. No returns/forecasts/balances are calculated.
- Endpoint release, actual pointer cancellation, reset, scenario reset,
  Previous/Next readout, empty/single/long cases, English/es-419 formatting,
  Light/Dark/System, and OS-controlled System appearance passed.
- A vertical gesture originating over the chart increases the page's actual
  scroll offset. Horizontal gestures retain the selected date after release.

## Measurements: retain both contexts

Pixel 4 profile, Android 16/API 36 arm64, 1080×2280 at 440 dpi, emulator 37.1.11,
SwiftShader software GPU, debug APK. No physical-device or API 26 runtime claim.

| Context, 2,000 rows | Frames | Janky | Frame p50 | Frame p95 |
| --- | ---: | ---: | ---: | ---: |
| Compose instrumented test; 12 paced 300 ms shell swipes | 41 | 11 / 26.83% | 17 ms | 48 ms |
| App alone, outside instrumentation; 12 paced 300 ms adb swipes | 92 | 90 / 97.83% | 81 ms | 101 ms |

Raw samples are `long-series-gfxinfo.txt` and `app-only-gfxinfo.txt`. The app-only
sample shows substantial jank on this emulator; this is **not** a smoothness or
60 fps pass. Software rendering, debug build and test-clock effects limit transfer
to physical phones. Do not select only the better instrumented sample.

The instrumented scenario-switch-to-idle measurement is 398.57 ms. Twelve commands
plus synchronization took 5099.93 ms under instrumentation and 4549.11 ms app-only.
These are harness/command wall times, **not** finger-to-pixel latency.

The app-only sample used the visible scenario menu to choose “2,000 synthetic
observations”, then `adb -s emulator-5584 shell dumpsys gfxinfo
ai.argus.chartprototype reset`. Twelve alternating `input swipe 200 1120 880 1120
300` / reverse commands were followed by `dumpsys gfxinfo ai.argus.chartprototype
framestats`. Coordinates were inspected on this AVD and stay inside its chart,
away from Android's system back-gesture edge. `app-only-long-scrub.png` shows the
resulting actual readout. Other devices need their own inspected coordinates.

## Compatibility and limits

`environment.json` and `resolved-dependencies.txt` distinguish compiler plugin
2.2.10 from resolved Kotlin stdlib 2.3.21. Vico 2.5.1 resolves Compose UI/runtime/
foundation 1.11.1, Material3 1.4.0 and core-ktx 1.18.0 above the #730 BOM 2025.08.01
baseline. This isolated graph compiled on AGP 9.1.1 / Gradle 9.3.1 / JBR 25.0.3;
that does not authorize a shared-build dependency upgrade.

API 26 is a manifest minimum only; it was not run. TalkBack speech, physical-device
latency, device GPU performance and production-shell integration are unverified.
The chart's accessible Previous/Next/Reset controls and semantic readout are tested.
Manual dark-mode capture shows low-contrast system-bar icons in this standalone
host; production system-bar ownership remains with the native shell lane.

## Discarded preflight attempts

Preflight batched Compose touch injection was unsuitable for representative frame
measurement. One accidentally overlapping local verification attempt was stopped
and discarded. A near-edge physical-style swipe activated Android's back gesture
and produced zero frames; that sample is discarded. The final test uses interior
swipes, asserts changed readouts, and requires a parsed positive frame count.
An attempted post-test file-copy hook did not preserve artifacts through AGP
uninstall; it was removed. The final direct adb runner pulls before cleanup.
None of those discarded attempts supports the table above.

## Reproduce and cleanup

Runnable build, dedicated-device and direct-test commands live in
`prototypes/chart-validation/android/README.md`. Screenshots cover every case,
Spanish appearance, System responding to the OS, endpoint scrub and vertical
scroll. `screenshots.sha256.json` indexes the durable images.

Only chart-owned resources were stopped: emulator-5584 and Gradle daemons under
`/tmp/argus-chart-gradle`. The unique app/test packages were uninstalled first.
The stopped AVD at `/tmp/argus-chart-avd`, isolated Gradle cache and ignored local
build outputs remain reusable; no shared emulator, adb server, Docker resource or
native-auth project was restarted or stopped. See `cleanup.txt` for receipts.
