# Cuadrao on iPhone 15: money formatting and balance history under interaction

Measured on a physical iPhone 15 (iPhone15,4, iOS 27.0.1, 60 Hz), Release configuration, preview bundle
`local.cuadrao.design.47R3855RTJ` (populated Home, sample data). Before is build 3425 at `20f31941b`,
recorded for 90 s with Animation Hitches while a person ran the interaction script (range taps, chart
scrubbing, expanded chart, scrolling, tabs, money typing). After is build 3426 at `7a3182488`.

The interaction recording has not been repeated on 3426 yet. The "after" column below holds only what
was measured without a person: the host check, the simulator tests and the launch and idle recordings.

## Before: build 3425, 87 s of interaction

| Measurement | Value |
| --- | --- |
| Hitches | 258, hitch time ratio 62.0 ms/s (6.1 ms/s idle after launch) |
| Hangs and interaction delays | 109 |
| Main thread CPU | 13312 ms |
| `CanvasMoney.format` inclusive | 3621 ms, 3510 ms of it from the Home balance chart's marks |
| `-[NSNumberFormatter _regenerateFormatter]` under it | 3025 ms |
| `-[NSNumberFormatter maximumFractionDigits]` under it | 2629 ms |
| `-[NSNumberFormatter stringForObjectValue:]` under it | 175 ms |
| `CanvasBalanceHistory.points` inclusive | 1261 ms: 879 ms chart reading, 206 ms `CuadraoHomeInsights.oldest`, 123 ms `CanvasBalancePeriod.init` |
| Decimal division under `points` | 877 ms |
| One scrub frame at the sampled hitches | 61 to 67 ms of main-thread work: money formatting 35 to 43 ms, history 6 ms |
| Money typing, `textField(_:shouldChangeCharactersIn:replacementString:)` | 160 ms: 148 ms inside `-[UITextField setText:]`, 6 ms in `maximumFractionDigits` |

## Cause and change

1. `CanvasMoney.format` built three `NumberFormatter`s per call: one decimal formatter and two currency
   formatters whose only use was reading `maximumFractionDigits`. The chart formats one accessibility
   value per plotted point on every body pass, so every scrub frame paid for it. Commit `931b3c299` reads
   the fraction digits once per device locale and currency code and keeps one `en_US` decimal formatter
   per fraction-digit count, behind a lock.
2. The scrub selection is state of the chart, so each scrub frame rebuilt a history that depends only on
   the accounts, the observations and the current day. Commit `7a3182488` splits the chart into an outer
   view that builds the history when its owner re-evaluates it and an inner view that holds the selection
   and reads it. The inner view rebuilds the history itself if the day has changed since it was built.

The chart still formats a label and a value per point on each pass. Swift Charts takes those as eager
strings, so they cannot be deferred without changing what VoiceOver gets. After change 1 that work is
about 3 ms of a frame by the trace's own split (175 ms of string conversion and 73 ms of date labels
against 3510 ms), so it was left alone.

Money typing was not the formatter problem: 148 of 160 ms is UIKit applying the regrouped text and
updating the keyboard. Change 1 removes the 6 ms. The deferred commit of the binding is untouched.

## Identical output

`python3 ios/DesignPreviewTests/run_money_format.py` compiles `CanvasMoney.swift` with a private copy of
the previous implementation and compares the two byte for byte: every common ISO currency code plus
lowercase, empty and malformed codes, 34 values (zero, negative zero, half-way cases, the app maximum,
values beyond it), 5984 pairs, then again in reverse order, then from 16 threads, plus literal strings
captured from the previous code. It runs under nine device locales (`-AppleLocale`): the Mac default,
`en_US`, `es_419`, `es_DO`, `es_US`, `ja_JP`, `de_CH`, `ar_KW` and `en_US@currency=JPY`. 12157 checks
pass in each. The same run times one call: about 49 µs before and about 1 µs now on the Mac.

A locale change inside a running process is covered by the cache key (the locale identifier is read on
every call) but is not exercised by the check, which sets the locale per process.

The chart split keeps every mark, label, modifier and identifier. `run_home_balance.py` passes its 81
checks, and on iPhone 18 Pro Max (simulator) `CuadraoHomeChartUITests` (13),
`CuadraoConsistencyUITests/testMoneyEntryAndBlankCreationSpanish` and `CuadraoPlanCurrencyUITests` (2)
pass: 16 tests, 0 failures.

## After: build 3426, measured without a person

| Measurement | 3425 | 3426 |
| --- | --- | --- |
| Initial Frame Rendering, 5 cold launches | 209, 192, 192, 191, 191 ms | 286, 319, 317, 171, 179 ms |
| UIKit Initialization in the same launches | 85, about 70 ms | 204, 178, 190, 70, 73 ms |
| Initial Frame Rendering in the 40 s hitches recording | not read | 167 ms |
| Launch hitch in the 40 s recording | 250 ms | none |
| Hitch time ratio over the 40 s recording | 6.1 ms/s | 0.0 ms/s |
| Interaction delay at launch | 35 ms | 34 ms |
| Main thread CPU, first 3 s | 385 ms | 370 ms |
| `CanvasBalanceHistory.points` inclusive, first 3 s | 26 ms | 2 ms |
| Process CPU, idle Home, seconds 10 to 40 | 1 ms | 5 ms |
| Main thread CPU, idle Home, seconds 10 to 40 | 0 ms | 1 ms |

The first three launches on 3426 were slower. In those three the system's own UIKit Initialization
phase, which runs before any app view code, took 178 to 204 ms instead of about 70 ms, and they were the
first launches after the install. The next two launches and the 40 s hitches recording came in at 167 to
179 ms. No app frame grew in the slow launches. In the fourth launch the app left the foreground about
1.1 s after its first frame; nobody was meant to touch the phone, and the cause is not known.

## Not changed, with measured cost in the 3425 recording

| Item | Cost | Why |
| --- | --- | --- |
| `CuadraoHomeInsights.oldest` builds the history twice per Insights body pass | 213 ms over 87 s, 11 ms in one sampled hitch | On range and period changes only, not per frame |
| `CanvasBalancePeriod.init` builds its own history per expanded chart pass | 123 ms over 87 s | Removing it means passing a history into the period type |
| Decimal division inside the projection | 877 ms over 87 s before change 2 | Needs an arithmetic rewrite with its own equality proof |
| `-[UITextField setText:]` on each money keystroke | 148 ms over the typing step, 28 ms in one hitch | UIKit work for the regrouped text |
| Chart and SwiftUI work per scrub frame outside app code | about 14 to 20 ms of the 61 to 67 ms | Framework cost of re-evaluating the chart |
