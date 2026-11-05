# Package 0B-1 browser evidence

All API traffic was intercepted by Playwright. Authentication, conversation
history, failed HTTP responses, and the successful SSE response are fixtures.
No backend, provider, production account, or analytics sink was contacted.

- Browser: Playwright Chromium.
- Time zone: `America/Santo_Domingo`.
- Languages: English and `es-419`.
- Viewports: 360 × 800 and 1280 × 900.
- Acceptance receipt time: `2026-08-13T18:17:32Z`, keeping the shared
  guest fixture's August 14 expiry in the future.
- Daily-cap header: `Retry-After: 20548`, derived from the receipt's next
  UTC midnight (`2026-08-14T00:00:00Z`).
- The local reset is `8:00 PM` in both languages; missing-header cases use the
  same fixed browser clock and next UTC midnight.

## Before

Runtime source: `6747ff3193687c885f9647d0af265e0af906ceb0` (integration base).
Captured before runtime edits, using a temporary spec retained as
[`before/capture.spec.ts.txt`](before/capture.spec.ts.txt).
The [run log](before/playwright.txt) records 12 passing baseline captures.
The baseline clock was `2026-09-26T18:17:32Z`. The acceptance clock was
later moved to August 13 to respect the existing guest fixture's expiry.
The reset time and visible expiry caption are identical at both clocks;
before images retain their original provenance and have not been rewritten.

The baseline images show the settled failure, not a fabricated old notice.
After the mocked 503 or 429 arrives, a history refresh restores the two
previously persisted greetings and discards the locally submitted question
and failure message. This occurs for signed-in 503 and both account kinds'
429. Holding that refresh pending instead leaves “Opening conversation…”;
that transient loading state is not used for these images.

## After

Current after screenshots were captured at
`cb3d305de2fdad813722a6d550ad5535d5ac92c6`. The complete package suite passed
31 cases, including one account-scoped notice above the composer and its full
reload, dismissal, expiry, account-change, and recovery lifecycle. See the
[current browser revalidation](after/revalidation.md) and
[run output](after/playwright-lifecycle.txt).

The [notice design rationale](limit-notice-design.md) records the official
Codex, Grok, and Claude Code references and the reused Argus treatment.

Initial implementation run: 22 tests passed, with the
[Playwright output](after/playwright.txt) retained. These are HTTP recovery
surfaces; the fixture does not interpret or simulate the sample question.

Acceptance specs:

- `web/e2e/registered-compute-claim-503.spec.ts`: both languages and widths;
  one disabled countdown control; no automatic retry; repeated 503 preserves
  one local question; eventual success; new-chat 15-second fallback.
- `web/e2e/daily-cap-429.spec.ts`: both account kinds, languages, and widths;
  exact local reset copy with the header and without it; no vague wait or
  claim countdown; new-chat notice and question remain visible. The notice is
  outside message rows; same-tab persistence, dismissal, expiry, successful
  recovery across navigation, account isolation, and first guest bootstrap
  have dedicated cases.

The tests use the existing breakpoint account fixture and #681's mocked
Problem Details and SSE pattern. They exercise the actual web application.
No response copy is injected into the DOM. The existing screenshot CSS hides
development tools and disables animations, transitions, and caret blinking.

```sh
cd web
PLAYWRIGHT_BASE_URL=http://127.0.0.1:31693 \
COMPUTE_LIMIT_SHOT_DIR="$PWD/../docs/reports/evidence/693/after" \
bunx playwright test e2e/registered-compute-claim-503.spec.ts \
  e2e/daily-cap-429.spec.ts --workers=1
```

## Image index

Each stem below has `en` and `es-419`, then `mobile` and `desktop` variants
in `before/` and `after/`:

- `registered-503-<language>-<viewport>.png`
- `guest-429-<language>-<viewport>.png`
- `registered-429-<language>-<viewport>.png`

`after/registered-503-repeated-<language>-<viewport>.png` also captures the
second failed response and its restarted countdown.
