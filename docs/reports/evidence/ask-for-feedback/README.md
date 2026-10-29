# Ask for feedback: evidence

Roadmap item "Ask for feedback" in `docs/specs/argus-grounded-finance-roadmap.md`
(added at `ff98fec7`). Integration base `ff98fec7`. Integration `7c21ea62` (the
readout PR, #588) merged one way as `44d92028`. Code head `794aa2e6`.

Founder decisions on 2026-09-11:

- The test email arrived.
- Older conversations whose last turn is a result keep asking once.
- A one-tap save carries the pointers a thumbs rating saves, and no conversation
  text.

## Browser proof, both languages

Run from `web/` against a real local API: this worktree, memory persistence,
mock auth, no `.env`, and the SMTP credential blank on purpose.

```bash
FEEDBACK_ASK_LIVE_API=1 FEEDBACK_ASK_EVIDENCE_DIR=../docs/reports/evidence/ask-for-feedback PLAYWRIGHT_PORT=3100 bunx playwright test e2e/feedback-ask.spec.ts --workers=1
```

Result at `794aa2e6`: 10 passed, five tests per language. The transcript is a
route fixture with one user turn and one result card, which carries an evidence
artifact id. Its shape matches `e2e/issue-509-card-copy-language.spec.ts`. With
`FEEDBACK_ASK_LIVE_API=1`, feedback goes to the real endpoint. Without it the
save is stubbed and the spec also passes. The failed-tap test stubs a 503 in both
modes.

| Screenshot | What it shows |
| --- | --- |
| `en-1-ask-after-result.png`, `es-419-1-ask-after-result.png` | The ask under a result: three one-tap answers and a dismiss button |
| `en-2-tap-saved.png`, `es-419-2-tap-saved.png` | After a tap: thanks, with focus on "Tell us more" |
| `en-3-tell-us-more-dialog.png`, `es-419-3-tell-us-more-dialog.png` | The existing feedback dialog, opened from the ask |
| `en-4-dismissed-after-reload.png`, `es-419-4-dismissed-after-reload.png` | No ask after a dismissal and a reload |
| `en-5-failed-tap-stays-open.png`, `es-419-5-failed-tap-stays-open.png` | A failed save: the error toast, and the answers still offered |
| `en-6-next-turn-closed-after-reload.png`, `es-419-6-next-turn-closed-after-reload.png` | No ask after sending the next turn without answering, then reloading |

The spec also asserts, per language:

- The tap's request is `type: "general"`. Its context includes
  `source: "feedback_ask"`, `surface: "chat"`, `rating: "positive"`, and the
  result's `conversation_id`, `message_id`, and `evidence_artifact_id`.
- No message of the conversation, and not the card's title, appears anywhere in
  the tap's request.
- After the tap, keyboard focus lands on "Tell us more".
- The dialog's "include approved context from this conversation" checkbox is
  present and unchecked.
- Unticked, the dialog's detail carries `source: "feedback_ask"` and nothing that
  points at the conversation.
- Ticked, the detail carries the result's `conversation_id` and `message_id`, still
  no rating, and no conversation text.
- A failed save leaves the ask open, and it asks again after a reload.
- The ask stays gone after a reload that follows a tap, a dismissal, or the next
  turn.

The next-turn test was checked against a mutation. With the line that closes an
unanswered ask on the next turn removed from `FeedbackAsk.tsx`, the test fails,
because the ask returns after the reload.

API log for the eight real saves (per language: the tap and the unticked detail,
then the tap and the ticked detail):

```text
INFO     | argus.api.routers.feedback:feedback:116 - Feedback submitted
"POST /api/v1/feedback HTTP/1.1" 200 OK
WARNING  | argus.api.feedback_notification:notify_feedback_submitted:93 - Feedback notification failed
```

That block appears eight times. Because the credential was blank, every save also
shows a failed email that still saved the feedback.

## After merging integration `7c21ea62`

The readout PR and this lane both touch `ChatInterface.tsx`, `ChatMessage.tsx`,
`API_CONTRACT.md`, and `.env.example`, with no textual conflicts. What was
checked:

- **The card gate:** the merged `ChatMessage.tsx` gates the result card on the
  shared `isSettledStrategyResult`, and the readout PR removed the other inline
  `strategy_result` checks. `web/__tests__/alpha-frontend.test.ts` read that
  literal from `ChatMessage.tsx`; `794aa2e6` reads it through the shared check.
- **Pending breakdowns:** they are projected right after a user's
  `show_breakdown` action, so the ask cannot show while a breakdown is still
  arriving, including after a reload.
- **Result artifact ids:** live results still stamp `artifactId: run.id` with
  `backtest_run`.
- **Size and docs:** the merged `ChatInterface.tsx` is 2591 lines, within its
  budget of 2598. The readout PR's `API_CONTRACT.md` and `.env.example` hunks
  are in other sections.
- **Local environment:** the merge adds the `argus_display_contract` package, so
  `poetry install --with dev,workflows` has to run before the API or the backend
  suite can import.

## Test email

One email, marked as a test, sent on 2026-09-11 from a local run of the real app
at code head `044b9713`. One `POST /api/v1/feedback` went through FastAPI's
`TestClient` with memory persistence and the message:

> [TEST] Ask for feedback lane, local run on 2026-09-11. Please ignore: this
> only checks that feedback reaches support@get-argus.com.

The route returned 200 and saved one row. The notification task logged
`Feedback notification sent` with Resend receipt
`0e15b6d0-e9e1-4553-830e-1820002c2947`. The founder confirmed it arrived at
support@get-argus.com. The Resend transport and the notification's content have
not changed since. Later backend changes add `evidence_artifact_id` to the
sanitizer's kept keys and move the support address into one API owner,
`SUPPORT_EMAIL_ADDRESS` in `src/argus/domain/resend_email.py`, with the same
value. That change is backend-only, so the browser evidence at `794aa2e6`
still stands.

The test run read the credential from the integration `.env` into its own
process and never printed it. In that file
`CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD=${RESEND_API_KEY}` sits above the
`RESEND_API_KEY` line, so a loader that reads in order, such as python-dotenv or
`source .env`, sees the password as empty. The run resolved that one reference
itself, and no `.env` was edited. Hosted services set the password directly.

## Checks

| Check | Head | Result |
| --- | --- | --- |
| `poetry run pytest tests -q --no-cov` | `44d92028` (backend unchanged since) | 7667 passed, 585 skipped |
| `poetry run ruff check src tests workflows scripts` | `44d92028` | clean |
| `cd web && bun test` | `794aa2e6` | 1822 pass, 0 fail |
| `cd web && bunx eslint` on changed files | `44d92028` | clean |
| `cd web && bun run build` | `44d92028` (app code unchanged since) | compiled |
| `e2e/feedback-ask.spec.ts` against the real local API | `794aa2e6` | 10 passed |
| `scripts/check_modularity_budget.py` | `44d92028` | no violations; `ChatInterface.tsx` 2591 of 2598 lines |

`tests/test_access_request_postgres.py` runs only in CI's real-PostgreSQL matrix.
It failed at `2bd096a7` because it still patched the old
`access_approval_email.smtplib` path. `538e05f4` fixed that, and CI at `94fff4b3`
passed it.

No live measurement: no model-facing text or routing changed.
