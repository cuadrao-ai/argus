# Mobile footer divider correction

The physical-phone retest after PR #1202 failed. Its previous mobile crop
acceptance is superseded. This correction removes the extra horizontal divider
above the outline wordmark on `/`, `/personal`, `/en`, and `/en/personal`.
It does not claim to fix the remaining Safari toolbar crop.

## Cause and change

PR #1202 extended the Business mobile crop rule to every page and added its
1px border to Personal. The shared component already supplied the same wordmark
markup and crop geometry to all four landing routes. Home had a lower-contrast
version of the same divider.

The correction changes only `border-top` in the shared mobile rule to `0`.
Desktop rules, wordmark markup, crop height, top padding, overflow and page
colors stay unchanged. The footer test now rejects that extra mobile divider.
It no longer repeats the crop height or padding values as acceptance criteria.

## Verification

The fetched integration base and the refreshed integration tip are both
`5f793ad2dc4b8df97e91f4315dd20dab8a4cc884`. No reconciliation merge or semantic
overlap exists. The failing test precedes the fix in commit
`dc63a045dc557968e51fe2c44488c4a3cb2f5b3c`.

- Four mobile routes failed with `Expected: "0px"`, `Received: "1px"` before the fix.
- The corrected footer suites pass 74 tests across desktop and mobile Chromium.
- Eight desktop comparisons across four routes and Chromium/WebKit are byte-identical.
- Marketing lint, typecheck and production build pass.
- Baseline unit tests pass 212, skip 4 and fail 0. The runtime delta is CSS only.
- The modularity budget reports no violations on the would-be merged tree.
- Read-only comment review reports zero comments or suppressions introduced.

The focused browser command uses mock-only local services:

```sh
MARKETING_E2E_SITE_PORT=4793 MARKETING_E2E_PUBLIC_PORT=4794 \
MARKETING_E2E_MOCK_PORT=4795 bun run test:e2e \
  e2e/footer-crop.spec.ts e2e/footer.spec.ts e2e/footer-background.spec.ts --trace off
```

Media remains outside Git as requested. Local evidence is under
`/Users/garces/.codex/visualizations/2026/10/16/01a1430c-fce8-78b1-a002-a704ae804d29/cuadrao-sprint/footer-safari-toolbar`.
`targeted-green.log`, `divider-red.txt`, `desktop-parity.json`,
`native-probe-results.md`, and the native screenshots record these checks.
The root coordinator owns the final native captures, independent evaluation,
exact-head CI, integration landing and staging decision.

## Safari toolbar item remains blocked

Native iPhone 17e Safari on iOS 27.0 shows the hard crop above its floating toolbar
on both the unchanged home and Personal pages. This does not reproduce the good
home behavior reported on Lucas's physical phone.

Temporary probes tested viewport coverage, visible overflow, an opaque Personal
footer, and normal root overscroll. None produced the requested crop at the
physical screen edge. These probes did not become source changes.

The simulator accepted native address navigation to an id on the existing crop.
CUA finger click, drag and scroll did not reach the simulated webpage. The
captures therefore show native Safari chrome after anchor navigation, not the
physical finger-scroll state. This limit prevents a toolbar acceptance claim.
Lucas's phone retest still gates main promotion. No merge, deployment, public
publication or paid provider call is part of this worker change.
