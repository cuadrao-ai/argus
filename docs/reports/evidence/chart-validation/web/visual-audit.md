# Final bounded web visual audit

Browser capture: `49b0495bd0217b94be57b00d8ae96ba6a98b8830`. Motion capture: `de8f9cdf6874e8e46d04c887393f003fb5b74492`.
Native-only work advanced HEAD while recording; relevant web/style/fixture/font/lockfile source equality was verified through `b6aecdfdaf964f81aeb411110c003d9662bd5e68`. These captures replace earlier browser evidence. No production screens, shared build files or native shells changed in this web slice.

## Met

- Repository-local Space Grotesk 500 headings and Inter body/chart text load explicitly before rendering. Font bytes, licenses and attribution are hashed in source-manifest.json.
- Restrained flat light/dark surfaces, neutral text, pill controls, quiet horizontal grid and sparse time ticks. The representative chart/readout appears before the separate diagnostic lab.
- Shared visual-style.json owns actual/projected colors. Light stroke contrasts: 3.78 / 3.66. Dark: 6.11 / 6.32. Readout contrasts: 15.56 / 17.07. Text labels and solid/dashed lines retain meaning without color alone.
- Actual/projected facts remain separate. Missing-point screenshots show both missing fields and broken paths. Whole-case marker density avoids thick fragments in long series. No financial facts or smoothing added.
- Empty case has no invented axis data. Singleton renders an isolated dot, verified by canvas pixels and inspected screenshot; the library's default horizontal singleton stroke is disabled.
- English/light, es-419/dark, System switching, 390px width and desktop evidence. Tested 150% body text has no horizontal overflow and preserves readout height between adjacent selections; buttons wrap rather than clip.
- Node model tests and both browser suites pass. Chromium touch events prove horizontal scrub, retained release, restored cancellation and vertical scroll with preserved selection. The short recording demonstrates that sequence.
- No authored transitions or animations; reduced-motion assertion finds zero active authored animations. Pointer following remains direct.

## Measurements

| Browser | 2,000-point render range ms | Median ms | Readout p95 ms |
| --- | --- | --- | --- |
| chromium 147.0.7727.15 | 17.3–22.0 | 19.1 | 0.4 |
| webkit 26.4 | 33.0–51.0 | 35.0 | 1.0 |

Unthrottled desktop/emulation measurements. Render timing ends after two animation callbacks, not GPU completion. Readout timing measures formatting/DOM work, not input-to-photon latency. Raw samples/toolchain versions are in measurements.json.

## Limits and recommendation

**Adopt** Lightweight Charts 5.2.0 for the validated web direction, preserving segment splitting, isolated singletons, shared palette and accessible controls. This does not authorize product integration.

Physical-device speed/feel, minimum mobile OS/browser support, WebKit touch cancellation/vertical scrolling, and real screen-reader announcements remain unverified. Enlarged-text evidence covers the tested 150% body-text case, not universal accessibility certification. The sample-index time axis remains documented; native elapsed-date spacing is not claimed identical.

## Provenance and cleanup

source-manifest.json hashes all web source, shared series/style, font files/licenses, web lockfile and installed chart bundle. SHA256SUMS covers screenshots, video, reports and metadata. The only data is local synthetic fixtures.

Browser contexts closed and motion temporary directory removed. Owned server PID 48015 was verified as `node prototypes/chart-validation/web/server.mjs`, stopped, and port 4179 checked free. No shared simulator, emulator, Docker or test resource was restarted.
