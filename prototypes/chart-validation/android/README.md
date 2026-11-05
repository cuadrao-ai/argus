# Android chart validation

Standalone synthetic Compose application (`ai.argus.chartprototype`). It owns no
production screen, network permission, authentication, or financial computation.
The only data source is `../fixtures/series.json`, packaged through Gradle's asset
source directory. `Fixture.kt` partitions each actual/projected series into
contiguous segments so nulls cannot become connecting lines. X coordinates are
civil epoch days; UTC dates never shift with device timezone. Vico renders straight
paths. Projected lines are dashed; singleton segments have visible points.

A transparent Compose gesture surface maps horizontal drags to the nearest fixture
date (ties earlier), including missing rows. The same selection state powers the
readout and Previous/Next/Reset buttons. Vertical gestures belong to the page.
Release retains selection; cancellation restores its pre-drag value. Scenario
changes clear it; language/theme changes retain it. This custom adapter is needed
because selecting only Vico's non-null rendered targets would skip missing dates.
No curves, interpolation or inferred finance facts are introduced.

## Pin and compatibility

The existing #730 Android setup was inspected without merging or editing it:
AGP 9.1.1, Gradle 9.3.1, Kotlin/Compose plugin 2.2.10, Compose BOM 2025.08.01,
compile/target API 36, minSdk 26. Vico Android Compose **2.5.1** is pinned; it is the
stable Android series, not the 3.x Compose Multiplatform prerelease direction.

Official sources inspected September 28, 2026:

- [Vico 2.5.1 release](https://github.com/patrykandpatrick/vico/releases/tag/v2.5.1)
- [Vico Compose layer guide](https://www.patrykandpatrick.com/vico/guide/stable/android/compose/cartesian-charts/cartesian-layer)
- [Vico 2.5.1 published Compose sources](https://repo.maven.apache.org/maven2/com/patrykandpatrick/vico/compose/2.5.1/compose-2.5.1-sources.jar)
- [Vico 2.5.1 published core sources](https://repo.maven.apache.org/maven2/com/patrykandpatrick/vico/core/2.5.1/core-2.5.1-sources.jar)
- [AGP 9.1.1 official compatibility](https://developer.android.com/build/releases/agp-9-1-0-release-notes)

Resolved dependency caveat: Vico 2.5.1 raises Compose UI/runtime/foundation to
1.11.1, Material3 to 1.4.0, core-ktx to 1.18.0 and Kotlin stdlib to 2.3.21 above
#730's BOM 2025.08.01 baseline. A regular BOM is not an enforced version lock.
This standalone project compiles and its emulator tests pass, but adopting that
graph in the native shell needs its owner's coordination. Do not copy this
library pin into the shared build and assume unchanged dependency versions.

The source artifacts, rather than newer 3.x API pages, define the exact APIs used.
The app uses Android Studio's installed JBR 25 with Java source/target 17. Build
and emulator results are recorded in the evidence directory. Declaring minSdk 26
is not evidence of API 26 runtime behavior. No physical phone is certified here.

## Reproduce

From this directory, with Android SDK API 36/system image installed:

```sh
export JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home'
export ANDROID_HOME="$HOME/Library/Android/sdk"
export GRADLE_USER_HOME=/tmp/argus-chart-gradle
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:assembleDebugAndroidTest
```

Create a dedicated instance; never operate another lane's device:

```sh
export ANDROID_AVD_HOME=/tmp/argus-chart-avd
mkdir -p "$ANDROID_AVD_HOME"
printf 'no\n' | "$ANDROID_HOME/cmdline-tools/19.0/bin/avdmanager" create avd \
  -n Argus_Chart_Validation_2825 -k 'system-images;android-36;google_apis;arm64-v8a' \
  -d pixel_4 -p "$ANDROID_AVD_HOME/Argus_Chart_Validation_2825.avd"
"$ANDROID_HOME/emulator/emulator" -avd Argus_Chart_Validation_2825 -port 5584 \
  -no-snapshot -no-window -no-audio -gpu swiftshader -no-boot-anim
```

In another terminal:

```sh
export ANDROID_SERIAL=emulator-5584
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest :app:lintDebug
adb -s "$ANDROID_SERIAL" install -r app/build/outputs/apk/debug/app-debug.apk
adb -s "$ANDROID_SERIAL" install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s "$ANDROID_SERIAL" shell am instrument -w \
  ai.argus.chartprototype.test/androidx.test.runner.AndroidJUnitRunner
adb -s "$ANDROID_SERIAL" pull /sdcard/Android/data/ai.argus.chartprototype/files/ ./device-evidence
adb -s "$ANDROID_SERIAL" shell dumpsys gfxinfo ai.argus.chartprototype
adb -s "$ANDROID_SERIAL" emu kill
```

The explicit adb runner keeps the app installed until evidence is pulled; Gradle's connected-test runner automatically uninstalls it.

The instrumented suite exercises every fixture, missing-row segment preservation,
endpoint readouts, English/es-419, theme modes, horizontal release/cancel/reset,
vertical scroll, and twelve real-time shell-input long-series scrubs (300 ms each). Measurements explicitly
include test synchronization and are not finger-to-screen latency claims.

## Bounded visual revision

The chart uses Space Grotesk 500 and Inter from the already licensed #730 native
TTF assets; `licenses/` records upstream revisions. Typography and neutral colors
reuse that foundation's treatment inside this isolated application only.

One shared `../fixtures/visual-style.json` owns actual/projected colors across
clients. Light-theme 85% RGB variants provide 3.78:1 actual and 3.66:1 projected
contrast against white; dark base tokens provide 6.11:1 and 6.32:1 against
`#191c1f`. Neutral legend/readout text carries meaning independently of color.
Dashed projection, straight segments and missing intervals remain unchanged.

The date/readout now precedes the chart in stable text slots, with diagnostics
under “Prototype controls”. Three quiet Y ticks/grids describe the Vico plotting
range; tick arithmetic only positions the scale, never computes financial facts.
Minimum text slots scale with system font size, and the enlarged-text acceptance
checks that selecting a point does not change readout height. Empty cases give
no selection instructions; singleton dates appear once. The standalone host
updates both system bars when focus returns after a popup/theme change.

The capture helper waits for the screenshot background to match the resolved
appearance before saving, avoiding the prior theme's compositor frame. System
appearance, 1.5× font size and reduced-motion settings receive focused device
checks. The chart model uses direct, unanimated updates; no decorative curve or
selection animation is introduced. Earlier performance evidence describes the
prior layout and must not be relabeled as the revised layout's measurement.
