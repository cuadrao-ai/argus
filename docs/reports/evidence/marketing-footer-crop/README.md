# Mobile footer reference crop

Owner: marketing footer writer. Base: `4a21a1672419f0963a2fe244b8910238dcfb84ef`.

The mobile Personal footer used a 20vw crop without the home footer's top inset
or border. It now shares the existing home reference rule: 22vw crop, 10px top
inset and 1px border. No bottom padding, overscroll rule, copy, form, route color,
or desktop rule changed. The tradeoff is that Personal now includes the same
reference top divider. This is the approved reference reuse, not extra bottom space.

## Before and after

At 390px, both Chromium and WebKit measured:

| Route | Before crop | After crop | After crop bottom vs viewport bottom |
| --- | --- | --- | --- |
| / | 85.796875px | 85.796875px | -0.03125px |
| /personal | 78px | 85.796875px | -0.1875px |
| /en | 85.796875px | 85.796875px | -0.03125px |
| /en/personal | 78px | 85.796875px | -0.1875px |

All four after crops have the same 16.85px wordmark offset. The fractional bottom
values are layout rounding, under one pixel. All eight desktop screenshots
(two engines, four routes, width 1440px) are byte-identical before and after.

Native Safari proof used one iPhone 17e simulator, iOS 27.0 build 24A434, at
390 logical pixels (1170 physical pixels). Before and after screenshots and
recordings cover all four routes. Each recording includes a further upward
finger gesture at the document bottom and release. The outline remains cropped
at the page end after release. No persistent scrollable tail was reproduced
before the change; browser elastic movement is not claimed as a fixed defect.
This simulator proof is not Lucas's physical iPhone confirmation. Promotion
still waits for that confirmation.

## Checks and detection

- `marketing/e2e/footer-crop.spec.ts`: 8 cases, four routes at mobile and desktop.
  Baseline failed the two mobile Personal cases; the shared reference rule passes.
- `marketing/e2e/footer.spec.ts` plus the new crop suite: 42 passed.
- Marketing production build, TypeScript, focused ESLint, ownership and modularity passed.
- Detection signal: crop geometry, clipping and additional-scroll assertions in CI.
  No runtime log or metric is needed for this CSS-only change.
- Targeted probe: `node temp/footer-crop/probe.mjs after` against the local production
  preview. `after.json` contains measured bounds for every engine, route and width.

## Retained artifacts

All media stays outside Git. `manifest.json` records exact sizes and SHA-256 hashes.
The external directory is:

`/Users/garces/.codex/visualizations/2026/10/16/01a1430c-fce8-78b1-a002-a704ae804d29/cuadrao-sprint/footer-crop`

Native names are `before-ios-{home,personal,en,en-personal}.{jpg,mp4}` and the
corresponding `after-ios-*`. Browser names include engine, route and width.
`before.json`, `after.json`, `probe.mjs` and test/build logs preserve reproducibility.
