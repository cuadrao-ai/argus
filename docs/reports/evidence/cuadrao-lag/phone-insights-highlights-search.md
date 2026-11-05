# Insights, spending highlights and Search: second phone recording and build 3427

Date: October 4. Device: iPhone 15, Release preview build with sample data. Branch `claude/cuadrao-lag-fixes`.
Recorded on build 3426 (tree `7a3182488`), fixed in `0bd55440d`, `8a3f28480`, `5753b5d7c`, installed as build 3427
(tree `5753b5d7c`, clean). The interaction recording on 3427 has not been made; it needs a person on the phone.

## What the second recording showed (build 3426, 90 s, Animation Hitches template)

| Measure | run-1 (3425) | run-2 (3426) |
| --- | --- | --- |
| Hitches | 258 | 67 |
| Hitch time ratio | 62.0 ms/s | 29.6 ms/s |
| Money formatting in a sampled hitch | 35 to 43 ms per scrub frame | absent |

run-2 is not like for like: the script was performed twice during the recording. The trace holds one process
for its whole length (one process id, one launch, "Foreground - Active" for 1.50 min), so it shows no quit and
relaunch. The time profiler has no samples on any thread of the app between second 77 and second 85. The
733 ms and 167 ms hitches at 83.2 s and 84.0 s fall in that gap, so their "0 ms of main-thread time" means
no samples, not an idle main thread. The four 50 ms hitches at 99 to 100 s are after the last sample (91.1 s)
for the same reason. None of these six can be attributed to app code from this trace.

Main thread, 16696 ms sampled over 87.7 s. Top ten app symbols by inclusive time (closures of one body are
counted under that body):

| # | Symbol | Inclusive | Share of main thread |
| --- | --- | --- | --- |
| 1 | `CanvasBalanceHistory.points` | 1059 ms | 6.3% |
| 2 | `CuadraoHomeInsights.body` and its closures | 691 ms | 4.1% |
| 3 | per-point closure in `CuadraoHomeBalanceChartContent.chartBase` | 599 ms | 3.6% |
| 4 | `CuadraoHomeInsights.oldest` | 526 ms | 3.2% |
| 5 | `CanvasBalancePeriod.init` | 329 ms | 2.0% |
| 6 | `CuadraoHomeBalanceChartContent.body` | 290 ms | 1.7% |
| 7 | `CuadraoHomeBalanceChartContent.reading` | 255 ms | 1.5% |
| 8 | `CuadraoSpendingHighlights.body` | 248 ms | 1.5% |
| 9 | `CuadraoHomeBalanceChart.body` | 240 ms | 1.4% |
| 10 | `CanvasSpendingStory.longitudinalInsights` | 224 ms | 1.3% |

Rows overlap: 4, 5 and 9 are the three callers of row 1 (498, 323 and 238 ms of it), and row 10 is inside row 8.
`CuadraoSearchCanvas.body` is 43 ms (0.3%), 38 ms of it `activity`.

Callers and callees:

| Cost | Callers | Where the time goes |
| --- | --- | --- |
| `CanvasBalanceHistory.points`, 1059 ms | `CuadraoHomeInsights.oldest` 498 ms; `CanvasBalancePeriod.init` 323 ms (241 ms under the expanded chart, 88 ms under the distribution page); `CuadraoHomeBalanceChart.body` 238 ms | Decimal division 705 ms, multiplication 113 ms, dictionary lookups 62 ms |
| `CuadraoHomeInsights.body`, 691 ms | SwiftUI body update 541 ms, page closures 150 ms | `oldest` 526 ms (read at the page range and at `onChange`), `periodContent` 123 ms |
| `CuadraoSpendingHighlights.body`, 248 ms | SwiftUI body update | `longitudinalInsights` 224 ms, read from `featured` 145 ms, the "See all" destination 34 ms, the emptiness test 24 ms, `hasMore` 21 ms |
| `CuadraoSearchCanvas.body`, 43 ms | first appearance of the Search tab | `activity` 38 ms, 30 ms of it `availableAccounts` rebuilt for each activity row |

Sampled hitches these appear in: 48.238 s (67 ms hitch, 79 ms of main-thread work, 50 ms in the history
builder under Insights), 56.225 s (67 ms, 79 ms, 30 ms in `longitudinalInsights`), 68.522 s (117 ms, 98 ms,
16 ms in the Search body, 8 ms in `activity`; also flagged "expensive render, 12 offscreen passes"),
19.635 s and 29.635 s (33 ms each, 20 and 26 ms in the history builder).

## What changed

1. `0bd55440d` Insights builds the balance history once per body pass in balance mode, reads the oldest
   offset from it once, and hands it to each live page. The chart uses a handed history instead of building
   one and gives it to its period; `CanvasBalancePeriod` has a second initializer that takes the history, and
   the first one builds it and delegates. The distribution page builds its period once instead of twice. A
   handed history carries the day it was built for and is used only while that day holds. One Insights pass
   built the history about eight times and now builds it once.
2. `8a3f28480` The highlights body reads `longitudinalInsights` once per pass instead of from four places.
3. `5753b5d7c` The Search activity filter reads `availableAccounts` once instead of once per activity row.

No stored cache and no new state. View tree, copy, modifiers, identifiers, gestures and transitions are unchanged.
Money entry was not touched.

## Checks at `5753b5d7c`

| Check | Result |
| --- | --- |
| `ios/scripts/cuadrao-design-mac-pass.sh checks` | `== checks: ok`; Home balance 82 checks, money format 9 x 12157 |
| New Home balance check | a period given a history built earlier the same day equals the period that builds its own, field by field, three ranges, offsets 0 to -14, five fixtures; a history is refused on the next day |
| Debug simulator compile | BUILD SUCCEEDED |
| `CuadraoHomeChartUITests` (class, 13 tests: ranges, paging, distribution, breakdown, spending highlights, large English) | 13 passed |
| `CuadraoSupportUITests`: `testSearchPlansChatReturnAndRecovery`, `testActivityDetailsReturnToSearchAndAccount`, `testGroupSearchFiltersArchiveAndReturn`, `testFirstUseSavedChatAppearsInSearch` | 4 passed |
| `CuadraoHistoryDesignUITests/testSharedDatesInSearchAndLargerText` | passed |
| `CuadraoContextUITests/testChartContextKeepsPeriodAndDistributionSelection` | passed |
| Release device build 3427 | BUILD SUCCEEDED, clean tree, installed, phone reads 3427 |

Simulator: iPhone 18 Pro Max, 19 tests, 0 failures. `testFirstUseSavedChatAppearsInSearch` took 441 s and passed;
its duration at the previous head was not measured, so that is recorded, not explained.

## Build 3427 without a person (launch and idle)

| Measurement | 3426 | 3427 |
| --- | --- | --- |
| Initial Frame Rendering, 5 cold launches | 286, 319, 317, 171, 179 ms | 277, 169, 165, 167, 167 ms |
| UIKit Initialization, same launches | 204, 178, 190, 70, 73 ms | 165, 68, 65, 68, 67 ms |
| Initial Frame Rendering in the 40 s hitches recording | 167 ms | 171 ms |
| Hitches in 40.9 s | 0 | 0 |
| Main thread CPU, first 3 s | 370 ms | 381 ms |
| Process CPU, first 3 s | 643 ms | 685 ms |
| `CanvasBalanceHistory.points`, first 3 s | 2 ms | 2 ms |
| Idle Home, process CPU, seconds 10 to 40 | 5 ms | 6 ms |
| Idle Home, main thread CPU, seconds 10 to 40 | 1 ms | 1 ms |
| Thermal state | Nominal | Nominal |

Launch and idle did not regress. The first launch after the install was slow again in the system's UIKit
Initialization phase, as on 3426. The 11 ms and 42 ms differences in the first 3 s are one recording each.

## Not changed, with measured cost in run-2

| Item | Cost | Why |
| --- | --- | --- |
| Offscreen passes on the Search tab's first frame | 117 ms hitch, 12 offscreen passes; 98 ms of main-thread work of which app code is 16 ms | Render cost of the drawn design; changing it changes how it is drawn |
| Per-point closure in the Home chart | 599 ms over the run | Swift Charts builders and eager accessibility strings per plotted point |
| Decimal division inside the balance projection | 705 ms over the run before this change | Arithmetic rewrite with its own equality proof; the builds that reach it fall from about eight to one per Insights pass |
| Home chart outer body, one build per Home pass | part of the 238 ms | One build per pass is the floor without a stored cache |
| `CuadraoSearchCanvas.activity` read from four places in the body | 8 ms after this change, estimated from 38 ms less 30 ms | Small; a hoist touches a 100-line body |
| Spending expenses rebuilt per Insights page in activity mode | 43 ms over the run | Not in a sampled hitch |
| Six hitches with no time-profile samples (83.2, 84.0, 99.5 to 100.5 s) | 733, 167, 4 x 50 ms | No samples to attribute; needs a clean recording |
