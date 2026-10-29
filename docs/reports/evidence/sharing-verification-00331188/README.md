# Signed-out receipt verification

Verified 2026-09-08 against **`00331188c9e42bb86b74042d0a74a8e24e423af3`**.

**Result: the existing shared receipt opens correctly while signed out at
390 × 844 and 1280 × 900. No receipt defect requiring a code change was found.
No PR is needed. Production sharing remains dark.**

## What was exercised

The actual Next.js production build and FastAPI public receipt route, on localhost.
Two owner-owned artifact fixtures were frozen through the existing
`create_receipt_for_artifact` service: buy and hold, and monthly contributions with
an explicit $200 contribution, $0 starting principal, and modeled costs. The cards
come from the production card builder via the repository's shared fixture factory.
The chart and returns are synthetic fixture data, not a newly executed backtest.
Receipt reads were not intercepted or replaced in the browser.

Eight fresh page loads: two strategies × English/Spanish × mobile/desktop. Each has
a frame before scrolling and a frame at the bottom. A Spanish unknown-link
tombstone is also captured. The browser was Chrome 152.0.7977.83 on macOS, with
CSS viewport resizing and a light system preference; the receipt correctly keeps
its own dark appearance. These are browser width checks, not physical iOS-device
or safe-area acceptance.

Signed-out evidence:

- Both `CUADRAO_MOCK_AUTH` and `NEXT_PUBLIC_MOCK_AUTH` were **false** for the running
  servers. No sign-in or guest identity was created in the browser.
- Cookies were empty for every capture. Session storage was empty; the only local
  storage key was the non-authentication language preference `i18nextLng`.
- Every recorded browser request and backend public read lacked Authorization
  and Cookie headers. Traffic stayed on the two localhost ports.
- No search, login form, navigation, sidebar, or dossier dialog mounted on a receipt.

The local process overrides were
`CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED=true`,
`NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED=true`, and
`NEXT_PUBLIC_ENABLE_SPANISH=true`. Persistence was memory mode, with no database or
provider credentials. Chat-runtime startup was disabled in the verification
wrapper because no chat turn was needed; the receipt routers and middleware were
the existing app code. The owner fixture was seeded directly, so this does not
re-prove the owner's Share button or database persistence guarantees.

## Results

| Check | Result |
| --- | --- |
| Signed-out receipt loads | 8/8 HTTP 200, expected title and language |
| Mobile / desktop widths | 390 / 1280 px, zero horizontal overflow |
| Long title | Wraps fully; one h1; no ellipsis or duplicated sheet heading |
| Frozen content | Numbers, asset, dates, chart, rules, note, and framing present |
| Monthly contributions | Amount, cadence, starting principal, fractional shares, and costs visible in both languages |
| Fixed action | Visible before scrolling, 46 px tall, href `/`, no carried query or state |
| End of content | Last line clears the bar by 40.78–41.09 px |
| Chart | 390 px wide on mobile, 620 px in the centered desktop column, 220 px tall |
| Live resize | 12/12 checks, 320–1920 px including 719/720/721 and 1023/1024/1025; no horizontal overflow |
| Runtime | Zero JavaScript exceptions; non-blocking font-preload warnings |
| Indexing | Every receipt has `noindex, nofollow, nocache` |
| Unknown receipt | Spanish tombstone and action render, no login required |

The resize list includes odd widths where the canvas rounds down by one CSS pixel;
its container still fills the available width. No chart label is clipped because
this receipt chart intentionally has no time or price axis labels.

## The seven #422 findings, checked against this receipt

The board's earlier Mobile PWA paragraph is stale: it calls #422 open, but its
later completed-work entry says PR #447 closed it. GitHub currently marks
[#422 completed](https://github.com/lagarcess/argus/issues/422), with this
[closure evidence](https://github.com/lagarcess/argus/issues/422#issuecomment-5267444849).
This verification did not edit the board or reopen that issue.

| Finding | Receipt-specific disposition |
| --- | --- |
| 2. Omnisearch title collapses at 390 | Omnisearch is absent. The receipt's longer title wraps over two lines without truncation at 390. |
| 3. Row date collides with menu | No row-action menu exists. Creation stamp and tested-date row are visible within the viewport in both languages. |
| 4. Confirmation repeats symbols | No confirmation card or symbol chips mount here. The asset facts row renders once; no adjacent duplicated symbol heading. |
| 5. Spanish usage count has plural verb for one | Usage panel and allowance counts are absent. The receipt's Spanish contribution and cost facts render correctly. The original count-one strings are not exercised by this route. |
| 6. Spanish auth strings lack accents | No auth form or password controls mount. The receipt opens without a login step; these six original strings are unreachable here. |
| 7. Dossier sheet duplicates the title | No dossier or sheet header mounts. Exactly one h1 at both widths. |
| 8. Result chart clips first x-axis label | Receipt uses `ReceiptChart`, not `ResultEquityChart`. Both axes are intentionally hidden. The rendered chart fills its container and resizes without overflow. |

Items tied to absent app components are **not applicable to the public receipt**;
this is not a new global regression pass over those other screens. The responsive
app shell remains unconditional; no responsive-shell flag was needed or added.

## Browser evidence

| Fixture / language | Mobile, initial view | Mobile, bottom | Desktop, initial view | Desktop, bottom |
| --- | --- | --- | --- | --- |
| Buy and hold / EN | [Frame](buy-and-hold-390-en-fold.png) | [Frame](buy-and-hold-390-en-end.png) | [Frame](buy-and-hold-1280-en-fold.png) | [Frame](buy-and-hold-1280-en-end.png) |
| Buy and hold / ES | [Frame](buy-and-hold-390-es-419-fold.png) | [Frame](buy-and-hold-390-es-419-end.png) | [Frame](buy-and-hold-1280-es-419-fold.png) | [Frame](buy-and-hold-1280-es-419-end.png) |
| Monthly contributions / EN | [Frame](monthly-contribution-390-en-fold.png) | [Frame](monthly-contribution-390-en-end.png) | [Frame](monthly-contribution-1280-en-fold.png) | [Frame](monthly-contribution-1280-en-end.png) |
| Monthly contributions / ES | [Frame](monthly-contribution-390-es-419-fold.png) | [Frame](monthly-contribution-390-es-419-end.png) | [Frame](monthly-contribution-1280-es-419-fold.png) | [Frame](monthly-contribution-1280-es-419-end.png) |

The exact local verification scripts are retained in [`drivers/`](drivers/). The
capture script uses the public IDs generated for this run; a reproduction must
replace them with the new IDs emitted by the seed server and adjust the output path.
No fixture is a real customer record.

[Unknown-link tombstone](unknown-receipt-390-es-419.png).
[Rendered text, geometry, cookie state, and browser requests](browser-results.json).
[Backend request credential-presence checks](backend-requests.json), including setup reads.

## Supporting verification and limits

- Production build: successful compilation, TypeScript check, and page generation.
- Existing frontend receipt tests: **89 passed**, 0 failed across
  `public-receipt.test.ts`, `public-receipt-language.test.ts`, and `evidence-receipts.test.ts`.
- Existing backend API/read-path tests: **53 passed**, including the flag-off and
  public-read contracts. These tests use their own isolated test configuration;
  the browser servers used mock auth off as stated above.
- The first Spanish capture attempt used a mistaken local flag name and rendered
  English. Those images were discarded and overwritten after rebuilding with
  `NEXT_PUBLIC_ENABLE_SPANISH=true`. The retained driver refuses to capture a page
  whose rendered language differs from its case.
- No baseline images were regenerated and no pixel-difference budget was changed.
- `render.yaml` and `.github/private-alpha-release-profile.json` retain both
  sharing flags as `false`. No production service, flag, data, or deployment was changed.
- Guest sharing, conversion, forking, research receipts, owner creation UX, and
  post-CTA guest entry were not exercised or changed.

This evidence applies to the pinned product source. It is a local signed-out
verification, not a production-enable recommendation or hosted acceptance claim.
The evidence-only publication adds this directory without changing product source.
