# Cuadrao on iPhone 15: Home balance chart derived once per body pass

Measured on a physical iPhone 15 (iPhone15,4, iOS 27.0.1, 60 Hz), Release configuration, preview bundle
`local.cuadrao.design.47R3855RTJ` with `CUADRAO_DESIGN_PREVIEW = true` (populated Home, sample data).
Before is build 3424 at `329fd00d`. After is build 3425, the same tree plus this change. The phone was
not touched during any recording.

| Measurement | Before (3424) | After (3425) |
| --- | --- | --- |
| App Launch, "Initial Frame Rendering", 5 cold launches | 1.12, 1.09, 1.09, 1.09, 1.09 s | 209, 192, 192, 191, 191 ms |
| Main thread CPU, first 3 s (Time Profiler, 1 ms) | 1509 ms | 385 ms |
| `CanvasBalanceHistory.points` inclusive, first 3 s | 1177 ms | 26 ms |
| Launch hitch (Animation Hitches) | 1133 ms | 250 ms |
| Hang at launch | 342 ms microhang | 35 ms potential interaction delay |
| Hitch time ratio over the 40 s recording | 28.1 ms/s | 6.1 ms/s |
| Process CPU, idle Home, seconds 10 to 40 | 5 ms | 1 ms |

Cause. `CuadraoHomeBalanceChart` kept `history`, `points`, `bounds`, `shown`, `selected`, `xDomain`,
`availableRanges` and `effectiveRange` as computed properties that each rebuilt the whole balance
history. The chart read `bounds` once per plotted point and the range buttons read `effectiveRange`
twice per button, so one body pass rebuilt the history hundreds of times (SwiftUI instrument, before:
11 body passes at 52 ms, 10 chart content passes at 39 ms, 60 range button passes at 4.3 ms).

Change. The body derives one `Reading` from one history and the marks, labels and buttons read it.
Every derived value keeps its original expression, so the drawn output is the same.

Not measured here: chart scrubbing, period swipes and tab switches need a person on the phone.
