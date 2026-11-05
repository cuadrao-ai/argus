# Proposed prototype fixture contract v1

`fixtures/series.json` is the sole data source. Clients package or load these
bytes, never maintain copied values. No endpoint or production schema is added.

Envelope: `schema_version`, `synthetic: true`, `date_semantics: civil-date-utc`,
`cases[]`. Each case has `id`, bilingual `title` (`en`, `es-419`), `currency`,
`unit: major-currency`, `shape`, and `points[]`.

Each point has ISO civil `time`, `actual` and `projected` (number or null),
and `contribution` (number or null). Null is missing, never zero. All columns
are explicit. `contribution` is a dated fixture fact, not computed from prices.
At least one fully missing point represents each internal missing interval.

The recurring case includes authored `funding` metadata: `starting_capital`,
`recurring_contribution`, and `cadence`. Its first contribution row is initial
funding; later weekly Monday deposits carry the recurring amount. Clients render
the dated amounts already present and never generate a schedule from this metadata.

Actual backtest values retain the canonical `chart.series` time/value semantics:
`points.map(p => ({time:p.time,value:p.actual}))` restricted to non-null actuals
is the canonical historical shape. Gap and projection envelope fields are
proposed. Synthetic negative amounts test renderer behavior, not a claim that
a long-only portfolio produced negative equity. There are no forecasts or returns.

Dates are Gregorian civil dates: display in UTC, with no local-zone date shift.
Number/date formatting follows chosen `en-US` or `es-419`; display the explicit
ISO currency code with two fraction digits. Native separators may vary by ICU.

Selection uses the nearest fixture date on the x axis, ties earlier, clamped to
endpoints. Missing dates remain selectable and say No data / Sin datos. Plot
independent contiguous segments for each series; never connect across nulls.
Use straight linear paths and distinct actual/projected stroke styles and legend.

Previous/next controls traverse every row (including missing rows); from no
selection, next chooses first and previous chooses last. Reset clears selection.
Horizontal drag updates readout; vertical gesture scrolls. Release keeps selection;
cancellation restores pre-drag selection. Scenario change clears selection.
Theme or locale change keeps the selected row and only changes presentation.

All cases, including 2,000-point long series, are authored synthetic inputs.
Clients consume the committed JSON; no runtime generator or financial formula
is part of the bundle. The long case deliberately repeats step-shaped drawing
values and gaps, rather than representing an investment process.

## Prototype visual tokens

`fixtures/visual-style.json` owns the shared series palette consumed by all three
clients. Dark uses DESIGN's muted teal and soft blue. Light variants scale their
RGB channels to 85% to reach at least 3:1 against white while preserving hue.
These distinguish actual/projected observations, not gains/losses. Dashed
projection and text legends remain necessary non-color distinctions. This
proposed presentation contract does not change financial data or product tokens.
