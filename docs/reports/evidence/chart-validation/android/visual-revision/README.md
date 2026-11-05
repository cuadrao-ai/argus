# Revised Android chart evidence

**Superseded for axis rendering and current measurements:** see
[../axis-precision/README.md](../axis-precision/README.md). This directory preserves
the prior visual revision and its original measurements/provenance.

Capture began September 28, 2026 at **b6aecdfdaf964f81aeb411110c003d9662bd5e68**.
The parent advanced HEAD during capture; recorder/export metadata observed
**f5f4f4467fe53c3a1990cda9574b353c8b72d83f**. Both SHAs are retained in
`provenance.json`; no per-artifact commit timing is asserted. Android source and
shared fixtures/style are byte-identical across these heads and identical to
implementation commit `de8f9cdf6874e8e46d04c887393f003fb5b74492`. The intervening
#727 merge and later parent changes did not alter these acceptance inputs.
`provenance.json` records source hashes, both shared JSON hashes, APK hash, and
byte equality of packaged shared assets. All PNGs and the MP4 are original captures.

**CHANGE before adoption.** The assigned visual corrections pass on the dedicated
API 36 emulator. The dependency convergence and measured jank still require an
Android-owner decision and follow-up before production use. No library swap,
shared build change, optimization, production integration or physical-device claim.

## Acceptance

- Build, 2 JVM tests and lint pass: `build-verification.txt`, `unit-tests.xml`.
- All **7 instrumented tests pass**, 37.937 seconds: `instrumentation.txt`.
- Six synthetic cases retain their supplied actual/projected values, null gaps,
  straight jumps, negative singleton and weekly contribution facts. See `stress`,
  `empty`, `single`, `buy-and-hold`, `recurring-contributions`, `long` screenshots.
- Previous/Next/Reset provide a non-drag alternative. Endpoints, every stress
  readout, release retention, injected real pointer cancellation and scenario
  reset pass. Chart-origin vertical input increases the actual page scroll offset;
  `vertical-scroll.png` preserves that position instead of scrolling to the top.
- `spanish-dark`, `spanish-light`, `spanish-system`, `system-os-dark` and
  `system-os-light` show locale/appearance. The capture helper asserts the actual
  bitmap body color matches resolved theme before saving. Manual inspection
  confirms readable system-bar icons in both themes. These supersede the previous
  directory's incorrectly timed OS-theme screenshots.
- `enlarged-text.png` shows 1.5× system font size. Selection preserves measured
  readout height; visible readout text is not clipped. Vertical scrolling keeps
  below-fold controls reachable. This is not an assertion for every font scale.
- `reduced-motion.png` was captured with all three Android animation scales zero;
  direct selection and date readout pass. `chart-motion.mp4` is an eight-second
  app-only recording of horizontal scrubbing followed by vertical chart scrolling
  at normal settings. It is qualitative motion proof, not a latency measurement.

The chart uses licensed Space Grotesk 500/Inter, a flat surface, stable readout slots,
three quiet scale ticks and a separate diagnostics area. Shared series colors are
read from `visual-style.json`: light `#4d8f80`/`#6a88ac` (3.78:1/3.66:1 against
white), dark `#5ba897`/`#7da0ca` (6.11:1/6.32:1 against `#191c1f`). Neutral text,
dashes and explicit labels retain meaning without color alone.

## Both final performance contexts

Pixel 4 profile, Android 16/API 36 arm64, 1080×2280, 440 dpi, emulator 37.1.11,
SwiftShader software rendering, debug build. One sample of each context, no retries
for better numbers. Both use the same 2,000-row fixture and 12 interior 300 ms swipes.

| Context | Frames | Janky frames | Frame p50 | Frame p95 |
| --- | ---: | ---: | ---: | ---: |
| Instrumented revised layout | 12 | 12 (100%) | 81 ms | 121 ms |
| App-only revised layout | 101 | 101 (100%) | 81 ms | 101 ms |

Raw `long-series-gfxinfo.txt` and `app-only-gfxinfo.txt` are retained. This is
substantial emulator jank, not a smoothness or 60 fps pass. Debug/SwiftShader and
instrumentation effects limit comparison and transfer to physical phones. Prior
layout samples remain unchanged in the parent evidence directory; they are not
current-layout performance evidence and cannot be selected to improve this result.

Instrumented scenario selection-to-idle: 1935.46 ms. Twelve swipe commands plus
synchronization: 5725.51 ms. App-only command wall time: 4749.06 ms. These include
harness/adb overhead and are **not input-to-pixel latency**.

## Reproduce and capture lifecycle

From repository root, set `JAVA_HOME` to Android Studio's JBR, `ANDROID_HOME` to the
SDK, and `GRADLE_USER_HOME=/tmp/argus-chart-gradle`. Follow the standalone Android
README to boot only `Argus_Chart_Validation_2825`, serial `emulator-5584`.

```sh
prototypes/chart-validation/android/gradlew -p prototypes/chart-validation/android \
  :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest :app:lintDebug
adb -s emulator-5584 install -r prototypes/chart-validation/android/app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5584 install -r prototypes/chart-validation/android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s emulator-5584 shell am instrument -w ai.argus.chartprototype.test/androidx.test.runner.AndroidJUnitRunner
adb -s emulator-5584 pull /sdcard/Android/data/ai.argus.chartprototype/files/. ./device-evidence/
adb -s emulator-5584 shell am start -W -n ai.argus.chartprototype/.MainActivity
```

App-only sample: choose “2,000 synthetic observations” using the scenario menu.
Inspect chart bounds first. This device's plot bounds were `[198,946][1025,1551]`.
After `dumpsys gfxinfo ai.argus.chartprototype reset`, issue 12 alternating
`adb -s emulator-5584 shell input swipe 322 1248 900 1248 300` and reversed commands,
then `dumpsys gfxinfo ai.argus.chartprototype framestats`. Capture screenshot and
UI hierarchy. `app-only-before.xml` has no selection; `app-only-after.xml` shows
February 6, 2021 and DOP 596.00, also visible in `app-only-long-scrub.png`.

Record motion separately, after measurement, with
`adb -s emulator-5584 shell screenrecord --time-limit 8 /sdcard/chart-motion.mp4`.
This recording used horizontal swipes at y=1248 followed by vertical input from
(600,1450) to (600,1100). Pull before uninstalling. The recording does not enter
either performance sample.

## Compatibility and cleanup

`environment.json` records the unchanged actual toolchain. Vico 2.5.1 raises the
resolved Compose UI/runtime/foundation to 1.11.1, Material3 to 1.4.0, core-ktx to
1.18.0 and Kotlin stdlib to 2.3.21; compiler plugin remains 2.2.10. The full resolved
graph is retained in `../resolved-dependencies.txt`. API 26 is declared only; its
runtime, physical-device behavior and TalkBack speech are unverified.

Both prototype packages were uninstalled, owned emulator-5584 stopped, and the
single isolated Gradle daemon stopped (`cleanup-receipt.txt`). Shared adb/Docker
were not restarted or stopped. Reusable owned AVD/cache remain under
`/tmp/argus-chart-avd` and `/tmp/argus-chart-gradle`; ignored local build outputs
remain. No active Android process or device is required to review this evidence.
