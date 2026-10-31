# Issue #417: a receipt no longer freezes the author's language

Captured at lane head against a **production build** with
`CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED=true`,
`NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED=true` and
`NEXT_PUBLIC_ENABLE_SPANISH=true`, on a local memory-mode backend with no provider
keys. Enabling sharing stays a separate founder decision; both flags default to
false and these captures only show what the surface does if it is ever turned on.

## One receipt, two readers

Both frames below are the **same stored snapshot**, seeded once and served from
`/api/v1/public/receipts/argusreceiptevidence417abc`. Nothing about the payload
differs between them. The only thing that changes is the `Accept-Language` the
browser sent.

| Frame | Reader |
| :--- | :--- |
| `01a-phone-en-same-frozen-receipt.png` | `en-US` |
| `01b-phone-es-same-frozen-receipt.png` | `es-419` |

The run behind them was **written up in Spanish**: a recurring-contribution
strategy with modeled costs, produced by the real `build_result_card` at
`language="es-419"`, whose card assumptions read `Aporte recurrente: $200 mensual`,
`Capital inicial: $0`, `Solo largo`, `Peso igual`, `Neto de comisión de 10 bps +
deslizamiento de 5 bps`, `Referencia: SPY (mismos costos modelados)`, and whose
tested window read `2 de enero de 2024 al 1 de marzo de 2024`.

None of that prose is in the payload. What the snapshot actually holds is:

```json
"metrics": [
  {"key": "cash_value", "value": "$600 -> $720"},
  {"key": "total_return_pct", "value": "+18.4%"},
  {"key": "max_drawdown_pct", "value": "-6.2%"},
  {"key": "benchmark_return_pct", "value": "+9.1%"},
  {"key": "delta_vs_benchmark_pct", "value": "9.3"}
],
"assumptions": [
  {"key": "recurring_contribution", "value": "200"},
  {"key": "contribution_cadence", "value": "monthly"},
  {"key": "starting_principal", "value": "0"},
  {"key": "long_only", "value": null},
  {"key": "equal_weight", "value": null},
  {"key": "modeled_fee_bps", "value": "10"},
  {"key": "modeled_slippage_bps", "value": "5"},
  {"key": "benchmark_same_modeled_costs", "value": "SPY"}
],
"date_range": {"start": "2024-01-02", "end": "2024-03-01"}
```

So the English reader gets `$200 every month` and
`Jan 2, 2024 to Mar 1, 2024`, and the Spanish reader gets `$200 cada mes` and
`2 ene 2024 al 1 mar 2024`, from one frozen object that contains neither line.

## Register, checked against the lane that set it

The fine print stays fine print. Compare the block under the rules here with
`../receipt-sharing/02b-phone-es-recurring-buys.png`: terse muted one-liners of the
same weight, no terminal periods, no second narration beside the sentence above
them. That is the register the result card already froze (`Solo largo`,
`Peso igual`, `Sin comisiones/deslizamiento`, `Referencia: SPY`), and the reason
these are keys rather than prose is to render it in either language, not to make
it longer.

Six lines, the same count the app shows for this run: two pairs each read as one
line, the contribution with its cadence and the fee with its slippage.
`web/__tests__/public-receipt.test.ts` holds the bound, at the length of the
longest fragment the card itself froze.

The comparison line under the headline reads `9.3 pts ahead of SPY · SPY +9.1%`
and `9.3 pts por encima de SPY · SPY +9.1%` from the same two numbers. The card
this run produced states that comparison as `Beat by 9.3 percentage points`, in
English in both languages, so the receipt carries the figures instead and composes
the sentence for whoever opened the link.

`rendered-text.json` holds the full rendered body text of both pages. Every frame
here was checked by reading that text before the image was trusted: an earlier
capture attempt in this lane produced two plausible-looking frames that were both
a browser error page, and the byte-identical file sizes were the only tell.

## What still reads in the author's language, and why

`AAPL cada mes` is the idea's title. It is the one field a person wrote about
their own idea, so it stays as written and carries `lang="es-419"` for screen
readers. `owner_note` is the same case. `content_language` exists to name the
language of exactly those two fields, and nothing else.

## Capture note

Taken at 375 px on a 1500 px tall viewport. The action bar is fixed to the
viewport, so a full-page shot floats it across the middle of the document and
covers three assumption lines; a viewport tall enough to hold the whole receipt
leaves the bar below the last line, where it covers nothing.

## The shell reached the bottom, and the tombstone became readable

Two defects on this route, both shipped with #397, both byte-identical at base
, and both visible in that lane's own evidence
() without having been noticed.

**The white band.**  sized the dark shell with , a
percentage min-height, which resolves against the containing block's height. Body
sets  and never a height, so its own height stays content-based and
the percentage resolved to nothing. On any page shorter than the screen the dark
surface stopped at the last line and the white body showed underneath. Now
, which is sized against the viewport and needs no cooperation from a
parent.

**The invisible tombstone.**  was the one component on this route
written with  variants. The route runs no theme provider and the shell is
one fixed colour on purpose, so those variants never applied and their light-mode
values shipped: black text on the dark shell. Every sibling component was already
unconditional light-on-dark; this one now matches.

| Frame | Shows |
| :--- | :--- |
|  | 394 px of white body, and a title nobody can read |
|  | dark to the bottom edge, text legible |
|  | the same fix on a short real receipt |

Captured at a real 375x812 viewport, never : a full-page shot stretches
the viewport to the document and the gap it is meant to show disappears.
 records what was measured in the page rather than read off an
image. Both are pinned by test now: the layout must use , and no
component on this route may carry a  variant.

## The shell reached the bottom, and the tombstone became readable

Two defects on this route, both shipped with #397, both byte-identical at base
`d4ebaa96`, and both visible in that lane's own evidence
(`../receipt-sharing/08a-phone-en-tombstone.png`) without having been noticed.

**The white band.** `app/r/layout.tsx` sized the dark shell with `min-h-full`, a
percentage min-height, which resolves against the containing block's height. Body
sets `min-h-full` and never a height, so its own height stays content-based and
the percentage resolved to nothing. On any page shorter than the screen the dark
surface stopped at the last line and the white body showed underneath. Now
`min-h-dvh`, which is sized against the viewport and needs no cooperation from a
parent.

**The invisible tombstone.** `ReceiptNotice` was the one component on this route
written with `dark:` variants. The route runs no theme provider and the shell is
one fixed colour on purpose, so those variants never applied and their light-mode
values shipped: black text on the dark shell. Every sibling component was already
unconditional light on dark; this one now matches.

| Frame | Shows |
| :--- | :--- |
| `03-phone-en-tombstone-before.png` | 394 px of white body, and a title nobody can read |
| `03-phone-en-tombstone-after.png` | dark to the bottom edge, text legible |
| `02-phone-en-short-receipt-after.png` | the same fix on a short real receipt |

Captured at a real 375x812 viewport, never `fullPage`: a full-page shot stretches
the viewport to the document and the gap it is meant to show disappears.
`shell-height.json` records what was measured in the page rather than read off an
image. Both are pinned by test now: the layout must use `min-h-dvh`, and no
component on this route may carry a `dark:` variant.
