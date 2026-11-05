# Standalone web chart validation

Recommendation: **adopt Lightweight Charts 5.2.0 for this rendering direction**,
with explicit segment splitting and Argus-owned accessible selection state.
This is a prototype recommendation, not approval to integrate product screens.

## Run

From repository root, using the existing `web/node_modules` installed from
`web/bun.lock` (Lightweight Charts 5.2.0, Playwright 1.59.1):

```sh
node prototypes/chart-validation/web/server.mjs
# Separate terminal; synthetic local browser checks only:
node --test prototypes/chart-validation/web/model.test.mjs
node prototypes/chart-validation/web/verify.mjs
node prototypes/chart-validation/web/motion.mjs
```

Open http://127.0.0.1:4179. `PORT` can select a different server port; the evidence
runner intentionally targets 4179. Stop the server with Ctrl-C. No build step,
provider, account, credentials, CDN or shared build configuration is needed.
The server serves a fixed allowlist, bound only to loopback. `/fixtures.json`
reads the sole shared fixture file; it never copies or calculates financial facts.

## Verified official direction

Checked September 28, 2026:

- [Official 5.2 getting started](https://tradingview.github.io/lightweight-charts/docs):
  client-only ES2020 requirement and the standalone ES module are compatible with
  the installed 5.2.0 package. Node only serves files; it does not render the chart.
- [Official time scale API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ITimeScaleApi):
  coordinates map to logical sample positions. Selection rounds nearest, ties
  earlier, and clamps endpoints. This sample-index axis is not elapsed-time
  spacing; explicit missing rows occupy their own positions.
- [Official scroll options](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/HandleScrollOptions):
  library scroll/scale handlers are disabled in this bounded full-range example.
  The local pointer surface uses `touch-action: pan-y`, horizontal direction lock,
  capture, cancellation restore and retained release selection.
- [5.2.0 NOTICE](https://raw.githubusercontent.com/tradingview/lightweight-charts/v5.2.0/NOTICE):
  the required notice and TradingView link remain visible under the card.

The installed native toolchains do not constrain this browser module. No React
Native or native-wrapper chart is used. No minimum browser version or mobile OS
support is certified: ES2020, ResizeObserver, Pointer Events, Intl and modern
canvas support are required. Browsers tested are recorded in the measurements.

## Visual acceptance

The representative card uses locally served repository Inter and Space Grotesk
assets (existing [font attribution](../../../web/app/fonts/FONT-ATTRIBUTION.md)),
Space Grotesk 500 headings, neutral text, flat surfaces, pill actions and reserved
readout height. Diagnostic controls and date/unit mechanics sit below in the lab.
No shared CSS or build files are changed. The single shared
`fixtures/visual-style.json` owns chart colors for all three clients; the server
serves those exact bytes. Light strokes are contrast variants of DESIGN's muted
teal/soft blue, while dark retains the base colors. Both themes measure at least
3:1 for chart strokes and 4.5:1 for readout text against their actual backgrounds.

Quiet horizontal grids and sparse ticks support the values. Marker visibility
uses whole-case density, so a short fragment of the long series cannot turn into
a thick cluster. Singleton fragments still render an isolated point. There are
no authored transitions or animations; reduced-motion remains static.

## Behavior

Actual and projected facts are separate solid/dashed line series. Nulls create
independent contiguous series, preventing the library from bridging missing data.
No smoothing, forecasts, returns or balances are computed. Contributions are shown
as authored facts, not interpreted from jumps. Previous/next buttons traverse every
fixture row, including nulls; reset clears selection. Locale and theme changes keep
selection; changing the example clears it. Empty and singleton cases work without
special invented data. The date display explicitly uses UTC even when the browser
runs in Pacific/Honolulu. Amounts display ISO currency codes and two decimals.

## Evidence and limits

[Durable browser evidence](../../../docs/reports/evidence/chart-validation/web/)
contains English/light, es-419/dark, empty/single, enlarged-text, missing-point, recurring-contribution and desktop/long screenshots
for Chromium and WebKit. `measurements.json` records capture head, fixture hash,
OS/engine versions, assertions, raw measurements and shared-palette hash.
`chromium-touch-motion.webm` records a short scrub/release/cancel/scroll sequence;
`motion-metadata.json` records its capture head and hash. Parent delivery records
source equality after evidence-only commits. Initial development captures are
superseded by the final committed-head rerun.

The automated suite exercises all six fixture cases, endpoint selection, all
stress rows, no-data readouts, segment boundaries, English/es-419, all themes,
keyboard buttons, local font loading, contrast, 150% body text without overflow or
readout height changes between neighboring selections, reduced motion, scenario reset, and retained mouse release in both engines.
Chromium CDP dispatches actual browser touch events for horizontal drag, release,
cancellation and vertical scrolling; these are not synthetic DOM pointer events.
WebKit's touch cancellation/scroll coexistence is **not** certified by this runner.
Screen-reader announcement quality and physical-device touch feel require later
manual device acceptance; keyboard controls and the polite live region are present.

Performance captures are unthrottled on the local arm64 Mac. `renderLongMs` measures
synchronous construction through two animation callbacks for each 2,000-point
render (not GPU completion). `readoutMs` measures local selection formatting/DOM
work, excluding browser input delivery and paint. `idleFrameMs` is baseline frame
scheduling, not chart-under-load FPS. Raw samples support comparison; none imply
physical iPhone/Android speed or a production latency SLO. Browser closes after
successful verification; the server is explicitly stopped by the owning agent.
