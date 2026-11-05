# Transfer-label clarity check

Native source: `7a3bf64fcfa34b48281f6ba33bec08f19e604f41`.
This is focused local simulator verification of the From/To label change, using
Xcode 27.0 (27A266a), iOS 27 and the retained iPhone 17e simulator
`DD9EF306-EFED-41F1-9A8E-B42EBCEE07DA`. It used the real retained API on 58500
and synthetic user A. No financial command was confirmed.

The build succeeded. The focused UI check passed **1/1 in 163.259 seconds**.
[Terminal status](terminal-status.txt) records the result-finalization limitation.

- [English/dark](transfer-labels-en-dark.png) shows visible **From/To** and no
  redundant origin heading. Both menus were used to select cash as source and
  bank as destination.
- [Spanish/light](transfer-labels-es-419-light.png) shows **Desde/Hacia**, the
  same correct selections and no redundant heading.
- Both review flows showed the DOP 40 transfer’s effects: cash 225 → 185 and
  bank 750 → 790. [English review](transfer-labels-review-en-dark.png) and
  [Spanish review](transfer-labels-review-es-419-light.png) were cancelled.
- The existing [transfer correction form](transfer-correction-labels-en-dark.png)
  retained its bank → cash direction with visible labels. It was cancelled.
- [Expense](expense-picker-smoke-en-dark.png) and
  [card-payment](card-picker-smoke-en-dark.png) pickers still exposed their
  selected values and working menus. Those drafts were cancelled.
- [Canonical readback](readback.json) confirms all three tested account balances
  and versions are unchanged. No transfer, correction or other financial record
  was saved.

The focused [driver](TransferLabelCheck.swift) reused the existing UI helpers and
was removed from the compiled UI test target after execution. It is preserved
only to make these clicks and assertions inspectable; it is not a new general
journey test or financial fixture setup.

The accepted 2:55 recording predates this label-only correction and remains
financial-behavior evidence for its recorded source. These screenshots cover the
updated labels; no replacement recording or broad journey rerun was needed.

The unchanged Spanish horizontal type row still partly clips the Transferencia
chip at the right edge. That existing polish item is separate from this change.
No defect was found in the changed selectors. Other selector labeling, spacing,
long-name and larger-text polish were not claimed as complete.

The updated app is left signed in as A, English/dark, on Home with direct API
58500. The prior data and running services are preserved. Physical-iPhone access,
signing, deployment and the full MVEE remain outside this local check.
