# Evidence receipts: browser evidence

Captured at lane head against a **production build** with
`CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED=true` and
`NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED=true`, on a local memory-mode backend
with no provider keys. Phone width first, then desktop.

Enabling sharing is a separate decision from merging it. Both flags default to false
and stay false; these captures exist only to show what the surface does if it is ever
turned on.

## One receipt per supported strategy, in both languages

Every executable template in the capability registry, plus both readings of a
crossover, at 375 px. English and Spanish for each.

| Frames | What the rules block does |
| :--- | :--- |
| `01a-phone-en-buy-and-hold.png` &middot; `01b-phone-es-buy-and-hold.png` | Never sells, so the rules stop at one line that says so. |
| `02a-phone-en-recurring-buys.png` &middot; `02b-phone-es-recurring-buys.png` | Also never sells. The cadence is the sentence, not a parameter beside it. |
| `03a-phone-en-rsi-threshold.png` &middot; `03b-phone-es-rsi-threshold.png` | Buy and sell as two rules, with the indicator and its period on the exact line. |
| `04a-phone-en-buy-the-dip.png` &middot; `04b-phone-es-buy-the-dip.png` | Fixed trigger in the engine, so one sentence and no parameters to show. |
| `05a-phone-en-crossover.png` &middot; `05b-phone-es-crossover.png` | Both windows, and a mirrored exit stated as such rather than repeated. |
| `06a-phone-en-crossover-differing-exit.png` &middot; `06b-phone-es-crossover-differing-exit.png` | The exit carries its own windows because the compiler allows them to differ. |
| `07a-phone-en-macd-crossover.png` &middot; `07b-phone-es-macd-crossover.png` | Three periods on the exact line, both crossings in words. |
| `08a-phone-en-tombstone.png` &middot; `08b-phone-es-tombstone.png` | Revoked. Honest, permanent, still offers Try Argus. |

`09-desktop-en-crossover-differing-exit.png` is the densest case at 1280 px.

## The action bar, at both extremes

`10a`/`10b` are the shortest shape (recurring buys) and `11a`/`11b` the longest
(a crossover exiting on other windows), each captured twice: `-fold` before any
scrolling and `-end` scrolled to the bottom. `12a`/`12b` are the tombstone.
`action-bar-metrics.json` records what was measured rather than eyeballed.

| Frame | Page | Bar | On screen at the fold | Main padding | Covers last line |
| :--- | ---: | ---: | :--- | ---: | :--- |
| shortest, en and es | 1023px | 71px | yes | 112px | no |
| longest, en and es | 1152px | 71px | yes | 112px | no |
| tombstone, en and es | 812px | 71px | yes | 112px | no |

Before the bar, the only action sat 1.34 to 1.50 screens down and the pages ran
1201 to 1330px. Removing the in-flow block and adding the clearance leaves them
1023 to 1152px with the action reachable from the first paint.
`card-01` to `card-08` are the real preview images a platform fetches, at
1200&times;630.

`rendered-text.json` holds the rendered body text of all seventeen pages. Every frame
here was checked by reading that text before the image was trusted; two earlier
capture attempts in this lane produced plausible-looking frames that were wrong, one
from intercepting a request a server-rendered page never makes and one from pointing
the web server at the wrong API variable.

## What this version is

A dated record, read once. Ruled rows and a record stamp rather than bordered cards,
because the form has to argue for the numbers on a page nobody reached through Argus.

- **Nothing appears twice.** One date, in the stamp. The benchmark is in the headline
  and not restated in the fine print. The rules list only the rules that exist.
- **Two of the five strategies never sell.** `buy_and_hold` and `dca_accumulation`
  both set every exit to false in the engine, so a fixed buy-against-sell layout was
  built around the exception. The rules block shrinks to one line and says "It never
  sold" instead of leaving an empty half.
- **A mirrored exit is now a guarantee, not an assumption.** "Sold when it crossed
  back below" only appears when the exit rule really is the engine's mirror of the
  entry, judged over every field the engine reads. An exit configured in the same
  direction as the entry compiles to cross_above on both sides, so the mirrored
  sentence would describe the opposite of what ran; that shape refuses instead.
- **Direction is not published at all.** Argus executes long only, so a frozen
  "bearish" names which way two averages crossed and not a position taken; beside a
  sell rule it reads as shorting a stock, which Argus cannot do. The sentence carries
  the crossing direction already. This one was rendering on the branch before, so it
  is a correctness fix and not a styling one.
- **The card publishes less than the page.** A 1200 px card lands in a chat bubble
  around 250 to 320 px wide, so everything on it divides by roughly four. The title,
  symbols and dates were under eleven effective pixels and came off; platforms render
  `og:title` as text beside the image anyway. What is left is the wordmark, the
  return, the comparison and the not-a-tip line.
- **Metric labels render in the viewer's language** for the keys Argus owns, so a
  Spanish page no longer reads "Max drawdown" among its own numbers.
- **The only action is fixed to the bottom, with the caveat attached to it.** A
  permanently visible call to action is mildly promotional on a page a stranger did
  not ask for, so it never ships without the framing beside it. That also inverts the
  old arrangement, where the caveat was scrolled past and the button was found.

## Still English on a Spanish page

**Fixed by issue #417.** At the time these frames were captured, two things on a
Spanish page were still English, and both were frozen prose rather than chrome:
the assumptions, `Long only, no leverage.` and `Modeled commissions and slippage.`,
and the tested window, `Jan 2, 2024 to Mar 1, 2024`. They were generated as prose
by the result-card builder at run time and frozen into the payload, so unlike a
metric label there was no key to render from.

The payload now freezes keys and bare scalars for the assumptions, the metrics and
the tested window, and every sentence, label and date format is composed in the
reader's language at view time. The frames in this directory predate that change
and are kept as the record of what the surface looked like when this lane shipped.
See `docs/reports/evidence/417-receipt-language/` for the current behaviour.

The idea title stays in whatever language it was written in, which is deliberate and
marked with `lang` so a screen reader pronounces it correctly.

## Standing checks

Never-expose absent from payload, page source and preview image. Numbers unchanged on
re-run. Deleting the source revokes. Noindex present and untoggleable. Flag-off byte
identity `b0411118c770f8f6881177566f6dfab6bb52002efb07004efeafca99f52e43d3`, matching
base `01044cda` where no receipt code exists.

## Not captured, and why

- **The share action on a result card.** Reaching it needs a completed chat turn,
  which needs a live provider. Covered by `web/__tests__/evidence-receipts.test.ts`.
- **The receipt list inside the mobile shell.** Unchanged by this redesign; its
  frames are in the PR history at `ad0c8b1b`.
- **A curved equity line.** The hermetic fixture is linear, so every chart here is a
  straight rise. Real receipts will have their own shape.
