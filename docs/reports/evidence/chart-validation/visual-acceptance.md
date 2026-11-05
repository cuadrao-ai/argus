# Bounded chart visual acceptance

The final examples follow the locked DESIGN direction within this standalone
prototype. This is not a production readiness or universal accessibility claim.
The rendering library alone does not supply the required Argus presentation.

## Changes from the first technical proof

- Loaded licensed Space Grotesk / Inter fonts, neutral flat surfaces and larger
  touch targets replace fallback typography and default chart-host treatment.
- One shared `fixtures/visual-style.json` owns actual/projected colors across all
  clients. Light variants derive from DESIGN's muted tokens; strokes exceed 3:1
  against their chart background. Solid/dashed strokes and labels carry meaning
  independently of color. Financial signs do not determine these series colors.
- The chart and stable selected-value readout precede a separate diagnostic lab.
  Synthetic labeling remains visible. Engineering units and test mechanics stay
  in supporting detail; the web retains required TradingView attribution.
- Quiet grids/ticks preserve gaps and jumps. Web singleton segments are dots,
  not short flat lines. iOS date ticks avoid truncation at plot edges.
- Android fractional scale ticks and precise readouts share one numeric
  presentation policy; decimal midpoint geometry avoids spurious or rounded digits.
- Android screenshots now wait for the rendered theme; earlier System captures
  could lag OS changes. Its standalone host fixes system-bar icon contrast.

The initial screenshots remain inspectable in Git at
`5d5517484bd40c85b8603cbd4cc6bfca7aec53ab`; use the final platform provenance
rather than treating the old appearance as current proof.

## Met and bounded

| Check | Evidence |
| --- | --- |
| Light/dark, actual/projected contrast and loaded typography | Platform light/dark screenshots, source font hashes and shared contrast test |
| Normal/enlarged readout and controls | iOS Dynamic Type, Android 1.5x font, web 150% text screenshots and geometry assertions |
| Honest gaps, negative/flat/jump/single/empty and contribution cases | Shared fixtures plus platform scenario screenshots/tests |
| Stable scrub readout and scroll coexistence | Gesture tests and short platform recordings; release/cancel tests remain explicit |
| EN/es-419 and System appearance | Localized screenshots and tests, including fixed iOS scenario titles and Android rendered-theme synchronization |
| Reduced motion | No authored chart transitions; Android/web reduced-motion checks; direct pointer following retained |
| Accessible alternative to dragging | Previous/Next/Reset and semantic selected-value readouts; real screen-reader speech is not certified |

Native elapsed-date spacing and web sample-index spacing remain intentionally
reported, not presented as identical geometry. The hierarchy and controls adapt
to platform conventions rather than requiring pixel-identical clients.

## Remaining limits

The tested enlarged-text sizes and device profiles are bounded proof, not coverage
of every font size/viewport. Physical devices, iOS17/API26 runtime, full
VoiceOver/TalkBack/screen-reader behavior, and WebKit touch remain unverified.
Android's software-emulator long-series jank remains an adoption blocker, separate
from its visual corrections and dependency convergence. Do not describe that
interaction as polished or production-ready on the basis of still screenshots.
