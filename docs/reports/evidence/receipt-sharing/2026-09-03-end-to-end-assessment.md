# Evidence receipt sharing: end-to-end assessment

Captured 2026-09-03 at `codex/private-alpha-next` head `5d408acf`, on the lane
`claude/argus-conversation-sharing-spec-09a17b`. Frames and rendered text are in
[`2026-09-03-end-to-end/`](./2026-09-03-end-to-end/). The earlier evidence set
in this directory was captured against a seeded artifact; its README says the
share action on a result card was never driven because reaching it needs a
completed chat turn. This pass drives that path.

## Verdict

The built flow works end to end, locally, with the flags on. A registered owner
can share a completed result from the chat, a stranger sees a sanitized page in
their own language on a phone, the preview card renders, the owner can find and
revoke the link from Data Controls, deleting the chat revokes it on its own, and
nothing private reaches any public artifact. Production has both flags off and
answers every receipt route as if the code were not deployed.

Three limits on that verdict:

- The stranger's landing after the call to action was not observed as a guest.
  The link goes to `/`, which under mock auth lands in the signed-in app. On
  production `/` is the guest entry (`docs/PRODUCT.md`, Guest Entry).
- Persistence was memory mode. The database guarantees (immutability, refuse an
  insert whose chat is gone, revoke on every kind of source deletion) were
  proven separately by the 21 Postgres tests against a local disposable
  database, not through the browser.
- No guest was involved. Guests never see the share action today, because it
  is gated on the registered-only `can_save_decision` capability.

## How it was driven

Local stack, no production writes:

| Layer | Setting |
| :--- | :--- |
| Backend | `uvicorn argus.api.main:app`, memory persistence, mock auth, synthetic market data, real interpreter through OpenRouter, `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED=true`, `ARGUS_RESEARCH_RAIL_ENABLED=true`, `ARGUS_APP_ORIGIN=http://localhost:3000` |
| Web | `next dev`, `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED=true`, `NEXT_PUBLIC_MOCK_AUTH=true`, Spanish enabled |
| Driver | Headless Playwright 1.59, scripts under `2026-09-03-end-to-end/drivers/` |
| Production | Three read-only `GET` probes, listed at the end |

Test suites at this head, hermetic: 268 passed in the four
`tests/test_public_excerpt_*.py` files, 21 passed in
`tests/test_public_excerpt_snapshots_postgres.py` against
`postgresql://127.0.0.1:54332`, 17 passed in `web/__tests__/evidence-receipts.test.ts`.

## What happened, step by step

| Step | Observed | Frame |
| :--- | :--- | :--- |
| Chat turn "Test buying AAPL and holding it from January 2, 2024 to March 1, 2024" | Confirmation card, Run, result card with Quick take and Try next. "Share this" renders under the result actions. | 01 |
| Share this | Panel states what the link is before the note field: "Makes a link anyone can open. It shows these numbers, locked as they are right now. Your chat, your name, and anything Argus remembers all stay out of it." Note field is bounded at 280 with a public warning under it. | 01 |
| Make the link | Link appears in a code box with Copy link and "Your name is not on it, search engines cannot find it, and you can take it down any time from Data Controls." Copy link shows Copied. One `receipt_created` event. | 02 |
| Recipient, phone, English | Provenance mark, creation date stamp, title, +3.3%, "1.0 pts behind SPY · SPY +4.3%", asset, window, worst dip, equity line, "What ran", assumptions, owner note, framing, fixed action bar. | 03 |
| Recipient, phone, Spanish | Same page, every label, sentence and date in Spanish. The title and owner note stay in English with `lang="en"`, by design. | 04 |
| Recipient, desktop | Same content at 1280 px. | 05 |
| Preview card | 1200 by 630: wordmark, +3.3%, "1.0 pts behind SPY", "A what if, run on past market data. Not a tip." | 06 |
| Call to action | Label "Test your own idea", `href="/"`, one `try_argus` funnel event. Landed in the signed-in app under mock auth. | 07 |
| View counting | One `viewed` event per rendered page. The read endpoint was hit three times for one visit (metadata pass, page, image) and counted nothing. | log |
| Data Controls, Shared links | Title, symbols, window, "Shared September 3, 2026", Copy link, Open it, Take it down, and the honest cache note. | 08 |
| Take it down | Second tap "Sure?", then "Taken down September 3, 2026". | 09 |
| Tombstone, English and Spanish | "This one is gone", the reason in plain words, still offers the action. Metadata title becomes the tombstone title. | 10, 11 |
| Tombstone preview card | The unchanged `og:image` URL now renders the tombstone card, status 200. | 12 |
| Re-share the same result | New public id, previous stays revoked. | API |
| Delete the chat | Public read answers `revoked`; the list says "Taken down on its own when you deleted the chat behind it." Sharing the result again answers 404 "That result is not available." | 13 |

## What a recipient sees, and what stays out

Shown, all frozen at creation: idea title, headline return, benchmark comparison
and the benchmark's own return, symbols and asset class, tested window, worst
drawdown, the equity line (60 points here, capped at 500), the rule sentence,
assumptions, the owner note, the creation date, the framing, the provenance
mark. Every label, sentence, number format and date format is composed in the
reader's language at view time; only the title and the note are author text.

Never shown, and checked rather than assumed: the owner, the app language, the
Quick take and Explain result prose, trades, chart markers, and every id.
The leak audit ([`leak-audit.md`](./2026-09-03-end-to-end/leak-audit.md))
harvested nine private identifiers from the owner's own transcript read
(conversation, user, request, turn, run, idea, idea version, evidence artifact,
confirmation) and searched the public JSON, the server-rendered HTML and the
image headers. None appear. The only marker hit is the word "supabase" inside
a Next.js chunk filename in the app shell.

Headers ([`headers.md`](./2026-09-03-end-to-end/headers.md)): the page carries
`robots: noindex, nofollow, nocache` plus `googlebot: noindex, nofollow,
noimageindex` in metadata and `Cache-Control: no-cache, must-revalidate`; the
image carries `X-Robots-Tag: noindex, nofollow, noimageindex` and
`Cache-Control: no-store, max-age=0`.

## Production, read-only

| Probe | Answer |
| :--- | :--- |
| `GET https://api.arguschat.ai/api/v1/public/receipts/<24 chars>` | 404, body `{"detail":"Not Found"}`, 22 bytes |
| `GET https://api.arguschat.ai/api/v1/definitely-not-a-route` | 404, same 22 bytes |
| `GET https://api.arguschat.ai/api/v1/public-excerpts` | 404, same 22 bytes |
| `GET https://arguschat.ai/r/<24 chars>` | 404, the app's not-found page, `noindex, nofollow` in its metadata |

Both services therefore run with the flag off, and the flag-off byte identity
pinned by `tests/test_public_excerpt_api.py` holds on the deployed build.

## Findings that are not defects of the sharing lane

1. **A grounded answer can persist with untyped sources.** At `5d408acf`, the
   question "What has been going on with NVDA lately and why is the stock
   moving?" produced an answer with today's move, quarter figures and three
   publisher URLs written into the prose, and no `research` sidecar. The log
   shows the rail fell through to the pre-rail search-packet answerer
   (`knowledge_answer._external_facts_answer`, voiced by the `knowledge_voicing`
   task), which appends the packet's URLs to the prose and persists no typed
   sources. A second question at the same head, phrased around a specific
   earnings report, took the rail proper and persisted the full sidecar
   (`sources` with dates, `retrieved_at`, `anchor_symbols`, `follow_up`,
   `usage`). Frame 14 shows the first shape. Both transcripts, labelled with
   their SHA, and the re-verification on `5761dd41` after #544 touched this
   path, are in [`rail-gap.md`](./2026-09-03-end-to-end/rail-gap.md). Any
   sharing rule keyed on typed sources will correctly refuse the first shape
   and will therefore miss the most common research question until that path
   persists a sidecar. That belongs to the rail lane.
2. **The call to action is not labelled "Try Argus".** The spec and the
   funnel stage say Try Argus; the page says "Test your own idea" and
   "Prueba tu propia idea". Copy drift only.
3. **A 403 on creation reads as a generic failure.** `receiptFailureReason`
   maps only the note rejection and the rate limit; an
   `account_conversion_required` answer would say "Argus could not make that
   link. Try again." Unreachable today because guests never see the button,
   but it matters the moment the guest tap becomes a conversion hook.
4. **Issue #402 is still open.** Viewer-side funnel stages carry no actor, so
   receipt-driven conversion cannot be separated from ordinary guest traffic.

## Recipe, for the next person

Stage the integration `.env` into a scratch file, append the memory-mode
exports from `argus_export_dev_mode` in `.github/argus-env.sh` plus the two
sharing flags, and start `uvicorn` from a background shell rather than the
Browser pane (the pane's sandbox cannot read key files). Start `next dev` with
the `NEXT_PUBLIC_` flags inline. Do not write `.env` or `web/.env.local` into a
lane worktree. Drive with the scripts in `drivers/`: `driver-a.js` creates the
receipt from a real chat turn, `driver-b.js` and `driver-c.js` capture the
recipient views, the revoke, the tombstones and the delete-conversation
revocation. Delete the staged env file when done.
