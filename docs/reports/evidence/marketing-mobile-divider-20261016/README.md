# Complete mobile footer wordmark

Lucas's latest October 16 decision supersedes the earlier screen-bottom crop
target, its blocked status, and the divider-only evaluation at `a84e5206`.
On `/`, `/personal`, `/en`, and `/en/personal`, mobile now shows the complete
outline wordmark above Safari's floating toolbar. No divider appears directly
above the wordmark at mobile or desktop sizes. Desktop keeps its existing crop.

## Cause and shared correction

The fixed mobile crop box was shorter than the wordmark. Hidden overflow cut the
letters, while the downward text translation pushed them farther below the box.
The existing shared mobile rule now uses automatic height, visible overflow and
`env(safe-area-inset-bottom)` as bottom padding. The mobile text translation is
removed. This lets document scrolling reach the complete wordmark and its inset.

The Business desktop border becomes transparent. Its original 1px box remains
so the desktop letters do not move. Desktop crop height, text position, font,
colors and overflow stay unchanged. All routes reuse the existing component.
No viewport metadata, new copy, dependency or application behavior changes.

## Verification

The original and refreshed integration base are
`5f793ad2dc4b8df97e91f4315dd20dab8a4cc884`. No reconciliation merge or semantic
overlap exists. New failing tests precede the fix at
`f32416f8940275b185896969b6a12349258dac63`.

- Before the change, six focused cases failed and two passed. Both Business desktop dividers were visible; all four mobile wordmark boxes extended below the crop.
- After the change, all 74 focused footer browser tests pass.
- All 32 mobile geometry probes pass across four routes, widths of 320, 390, 430 and 800px, and Chromium/WebKit.
- All eight desktop comparisons preserve wordmark pixels and relative crop geometry exactly. One initial absolute-coordinate check differed by 0.28px from fractional scrolling; the corrected relative-geometry probe passes all eight.
- Marketing build, lint and typecheck pass. Unit tests pass 212, skip four and fail zero.
- Modularity reports no violations. Read-only comment review reports no comments, suppressions or blocking source findings.

The root coordinator captured native iPhone 17e Safari on iOS 27.0 at 390×844.
All four captures show complete letters above the visible floating toolbar and
no divider directly above the wordmark. The other footer separators remain.
The root reached document end through an id added to the existing crop by a
local test proxy. No extra element or style was added for that anchor.

CUA finger gestures did not reach the simulated webpage. These captures prove
native rendering after anchor navigation, not finger scrolling or physical-phone
acceptance. The browser geometry tests inspect element boxes, not glyph ink;
the native captures establish that the letters are visible. The tests do not
claim that every device reports a nonzero safe-area inset.

## Evidence and delivery

Media remains outside Git as requested. Evidence lives under
`/Users/garces/.codex/visualizations/2026/10/16/01a1430c-fce8-78b1-a002-a704ae804d29/cuadrao-sprint/`.
`footer-full-wordmark/` contains red/green logs, unit results and geometry/pixel
probes. `footer-safari-toolbar/native-whole-{home,personal,en,en-personal}.jpg`
contains the root's native captures. Earlier experiments remain historical
records, not acceptance of the new target.

The root owns the fresh independent evaluation, exact-head CI, integration and
staging actions. Lucas's physical-phone acceptance remains separate. This worker
performs no merge, deployment, public publication or paid provider call.
