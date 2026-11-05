# Android axis precision review fix

This is the current Android evidence set, superseding `../visual-revision/` for
rendered axes and measurements. Previous screenshots and both performance contexts
remain historical evidence with their original provenance.

Source: `81d8c2182fa4c8fa0d859b7278b7250df9dad1b2`. The review found that the
singleton's exact negative amount was rounded by an independent integer-only axis
formatter. Axis labels and readouts now derive precision from the same numeric
presentation function: at least two fraction digits, retaining meaningful extra
digits for a scale midpoint. Decimal midpoint construction avoids binary arithmetic
artifacts. No fixture facts, financial calculations, library versions, chart bounds,
fixed axis width or gesture behavior changed.

The canonical fixture is linked directly into JVM test resources. A test-only
`org.json:json:20240303` dependency provides the same parser API that Android owns
at runtime; it does not change the shipped dependency graph. The regression covers
all fixture values in English and es-419 and an odd-cent-derived midpoint requiring
three decimals. The device regression checks the singleton's exact axis label and
matching readout in both locales. Three unit tests, APK builds and lint pass.

See `provenance.json` for source/shared JSON/APK hashes and packaged-asset equality,
`build-verification.txt` and `unit-tests.xml`. Device and toolchain remain those in
`../visual-revision/environment.json`; runtime graph remains recorded in
`../resolved-dependencies.txt`. API 26 and physical devices remain untested.

Run commands are unchanged from `../visual-revision/README.md`: direct APK installs,
`am instrument -w ai.argus.chartprototype.test/androidx.test.runner.AndroidJUnitRunner`,
then pull app external files before uninstall. The full eight-test suite refreshes
all fixture, locale, theme, 1.5× text, reduced-motion, pointer cancellation and
chart-origin scrolling evidence. The instrumented long-series sample is naturally
part of that suite; one app-only sample follows to retain both measurement contexts.
No performance optimization or additional measurement iteration is included.

## Final result

All **8 instrumented tests passed** in 31.021 seconds (`instrumentation.txt`).
Twenty original PNGs preserve the final renderer. `axis-cents-single.png` and
`axis-cents-single-es.png` show the exact -12.50 minimum and -6.25 midpoint;
`stress.png` shows 2,600.00 / 1,124.875 / -350.25. `enlarged-text.png` and
`long-enlarged.png` confirm decimal labels remain single-line and readable at
1.5× text size. Normal stress/long and enlarged stress/long were visually inspected:
no visible tick/readout clipping or wrapping. This bounded device/fixture result
does not certify arbitrary wider values or every accessibility font size.

The automated suite again verifies matching rendered theme backgrounds before
saving, locale presentation, stable enlarged readout geometry, direct reduced-motion
selection, release/cancellation/reset and chart-origin vertical scrolling. `chart-motion.mp4` is current qualitative motion evidence with final decimal axis
labels. The prior `../visual-revision/chart-motion.mp4` is historical only.

**CHANGE before adoption** remains the recommendation. Dependency convergence and
physical-device performance follow-up are still required. Both final samples below
are retained, without selecting the better context or claiming a performance gain.

| Final precision-fix context, 2,000 rows | Frames | Janky frames | Frame p50 | Frame p95 |
| --- | ---: | ---: | ---: | ---: |
| Instrumented, 12 paced 300 ms swipes | 36 | 12 (33.33%) | 17 ms | 65 ms |
| App-only debug, 12 paced 300 ms swipes | 99 | 99 (100%) | 81 ms | 101 ms |

Raw files: `long-series-gfxinfo.txt`, `app-only-gfxinfo.txt`. Instrumented scenario
selection-to-idle was 488.81 ms; twelve swipe commands plus synchronization took
5066.28 ms. App-only command wall time was 4719.46 ms. These contain harness/adb
costs and are not input-to-pixel latency. Debug build, software SwiftShader rendering
and instrumentation timing effects prevent physical-phone smoothness claims.

The app-only plot bounds were re-inspected and unchanged at `[198,946][1025,1551]`.
The same interior swipes (322,1248)↔(900,1248), 300 ms each, were used after resetting
gfxinfo. `app-only-before.xml` shows no selection; `app-only-after.xml` and
`app-only-long-scrub.png` show December 31, 2020, DOP 409.75. The additional long
1.5× screenshot was taken after this sample and did not affect its statistics.

Capture started at `81d8c2182fa4c8fa0d859b7278b7250df9dad1b2`; evidence export
observed `62c6e674cb16576c25f71e90377826d3ac21b3e8` after the parent's integration
documentation merge. Git comparison confirms Android implementation and shared
fixture/style files are identical across those heads. Both are recorded separately;
no per-artifact commit timing is invented.

Cleanup complete (`cleanup-receipt.txt`): both chart packages uninstalled, owned
emulator-5584 stopped, isolated Gradle daemon stopped. Shared adb/Docker were not
restarted or stopped. Owned reusable AVD/cache under `/tmp/argus-chart-avd` and
`/tmp/argus-chart-gradle`, plus ignored build outputs, remain. No Android resource
is left running for this task.

## Updated motion artifact

`chart-motion.mp4` was captured separately at `62c6e674cb16576c25f71e90377826d3ac21b3e8`
using the identical verified APK/source from the precision-fix commit. The stress
fixture shows exact decimal ticks while horizontal scrubbing changes the selected
date/value, followed by vertical page movement originating over the chart. The
recorder was requested with `--time-limit 8`; the encoded video duration is 6.2561
seconds. Exact frames at 1, 4 and 6 seconds were inspected to verify the original
artifact includes changed selection and scrolling. This clip is not a performance
measurement. No tests or performance samples were rerun.

One setup attempt captured a still-open scenario popup and was discarded. The
included clip used verified plot bounds `[198,946][1025,1551]` and the existing
700 ms horizontal swipes at y=1248 followed by vertical (600,1450)→(600,1100).
The app was uninstalled and owned emulator stopped again;
`motion-install-receipt.txt` and `motion-cleanup-receipt.txt` preserve this lifecycle.
No Gradle daemon was started for this recording.
