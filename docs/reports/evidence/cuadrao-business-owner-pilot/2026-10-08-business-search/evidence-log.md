# Business search, local end to end (2026-10-08)

Code under test: `claude/business-search` at `99d30b649` (API `2fb6053d9`, web
`99d30b649`), off `claude/business-spaces` `3cfc961aa`.

## Setup

- Stack: disposable local Supabase `argus-biz-spaces` (DB port 57782), reset
  with `supabase db reset` before the run. No hosted Supabase.
- API on 8631 and web on 3631, both from this worktree. Business, documents,
  jobs and WhatsApp intake flags on; outbound WhatsApp off.
- The document extractor is a local stub that returns a fixed read for the
  synthetic receipt `receipt-web.png` (sha256 `a56e610c6058…`). It was called
  once. Every HTTP proxy variable points at a dead local port, and the browser
  aborts any request to a host other than localhost. No provider was called.
- Owners A and B are local test accounts made through the local admin API.
- Owner A's Business space: account "Caja" (DOP), and the receipt, uploaded
  with consent, prepared by the stub, reviewed to merchant "Ferretería La
  Esquina" and confirmed as one RD$ 3,450.00 expense.
- Owner A's Personal side: account "Casa" (DOP) and one RD$ 99.00 expense with
  the same merchant, "Ferretería La Esquina", written through the canonical
  Personal money service.

## Results

| Check | Result |
| --- | --- |
| A searches "Ferretería" on /biz | PASS. One Business row, "Ferretería La Esquina, Oct 6, 2026 · Caja, RD$ 3,450.00" (`search-ferreteria.png`). The Personal RD$ 99.00 expense is absent. |
| Open it by keyboard (Down, Enter) | PASS. The palette closes and the receipt opens as "Saved expense" (`receipt-opened.png`). |
| Download the original | PASS. The downloaded file's sha256 equals the uploaded `receipt-web.png`. |
| Search by file name "receipt-web" | PASS. The receipt row appears, since its expense does not match the file name (`search-receipt-filename.png`). |
| Search "Casa", the Personal account | PASS. No Business rows; the existing "No results found" with the Business hint (`search-personal-account-absent.png`). |
| API reads (`search-reads.json`) | PASS. A's Business search returns only the Business expense; A's Personal `/financial-search` returns only the Personal expense; B finds nothing of A's; B reading A's source is 404. |
| Phone width (`search-phone.png`) | PASS. Same row at 390 px. The owner's profile language is English, so the UI is English. |
| External hosts requested by the browser | None. |

`business-search-journey.webm` is owner A's browser for the desktop run.
`journey.log` is the step log, including the search requests made.

## Gaps seen in this run

- The /biz palette still shows the decision ledger chips (Promising,
  Watching, Rejected, Revisit later) and the "Select a result to preview" pane.
  Both predate this change.
- Conversation results on /biz are the person's conversations, not only
  Business ones. Separating them is S4 of the space slice plan, not built.
