# Daily-cap notice treatment

The daily cap uses one account-scoped `FailureNotice` above the composer,
outside the transcript. It announces status with `role="status"`, keeps the
rejected question visible locally, and shows the localized reset time. No
assistant turn exists for a rejected request. Copy, ratings, and answer menus
therefore have nothing to attach to. No new design primitive, upsell, or
automatic retry was added.

The notice survives reloads and conversation navigation in the same tab until
its reset deadline. Closing it keeps it dismissed for that observation; a fresh
429 replaces and resurfaces the single notice. It clears automatically at reset,
on an authorized successful question, or when the account changes/signs out.
Focus and visibility checks handle a sleeping browser. Closing the tab ends its
session storage. The composer remains editable and manual sending stays available:
the server owns admission and different actions can use different allowances.
A successful ordinary chat turn, including a response choice, retry, or retest,
clears the notice early. Backtests and cancellation use separate existing request
paths and do not prove the question cap lifted. The clearing gate derives from
the existing request kind; it does not introduce another action allowlist.

Only account ID, reset instant, and dismissal state are stored through the
registered session-storage helper. No question, answer, or localized copy is
stored. Blocked storage retains an in-memory notice. The privacy copy describes
this temporary state. Request authorization rejects stale responses before they
can change it, including after guest bootstrap or conversation navigation.
An older successful question cannot erase a rejection observed after it started.

Official product references checked on 2026-09-26:

- [Codex usage limits](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
  describes a limit notice/banner with the reset time and available account
  actions.
- [Grok release notes](https://grok.com/release-notes/jul-18-2026) explicitly
  describe usage-limit cards that show when the limit resets.
- [Claude Code limits](https://support.claude.com/en/articles/14552983-models-usage-and-limits-in-claude-code)
  describes a limit-reached message with the reset time and applicable recovery
  options.
- [Codex's account-limit refresh owner](https://github.com/openai/codex/blob/main/codex-rs/tui/src/app/rate_limit_refresh.rs)
  refreshes account usage, rejects outdated recovery work, and clears stale
  recovery UI when fresh account state no longer supports it.
- [Claude Code's official changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
  records fixes for dismissed usage-limit warnings across same-account sign-in,
  stale pre-reset usage while idle, and repeatedly reopening limit options.

These references support account-scoped status, a concrete deadline, respectful
dismissal, and expiry refresh. They do not establish identical styling or
lifecycle across all three products. Grok's exact dismissal/reload behavior was
not publicly verified; no private account was deliberately exhausted.
Argus's existing notice system owns the visual treatment here. Its acceptance
screenshots and browser assertions verify the actual implementation.

## Reset truth and user settings

Both compute-admission owners (`src/argus/api/chat/guest_compute_ceiling.py`
and `registered_compute_ceiling.py`) send `Retry-After` from the remaining
seconds in `align_usage_period(now_utc, "day")`. Both durable claim migrations
set the database timezone to UTC and end the window at the next UTC midnight.
The guest-session and signed-in environment overrides change the number of
questions; they do not change this reset schedule.

The web uses that response's full delay, without the 503 retry clamp, and
rounds the resulting instant to the displayed minute. Only a missing/invalid
header uses the documented next-UTC-midnight fallback. The profile supports
language, locale, country, and currency, but no timezone preference. Browser
timezone therefore owns the local display, including daylight-saving offsets;
country is not used to infer a timezone. The Usage settings panel's execution
and grounding windows are separate allowances and do not own this chat cap.

The founder's follow-up requests consistent `AM`/`PM` in both supported
languages. This overrides the package's Spanish day-period styling example
(`p. m.`), while retaining the specified localized sentence. A single nonbreaking space
keeps the time and day period together on narrow screens. No second parser
or quota schedule was introduced.

Verification: `tests/test_compute_reset_contract.py` exercises real chat 429
responses for guest and signed-in configured limits, at UTC midnight,
mid-day, and just before reset. Web tests check DR, UTC-positive, and winter/
summer daylight-saving display. Neither backend runtime nor user settings
were changed.
