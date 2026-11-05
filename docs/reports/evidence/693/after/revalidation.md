# Browser revalidation

## Final admission-boundary revalidation

Runtime commit: `bd889e41d8d2e429081254a2033d747232370230`.
Successful ordinary chat turns, including structured response choices, retries,
and retests, clear stale notices. This derives from the existing request kind:
backtests already use `backtest_job`, and cancellation has its separate handler.
Neither cap-exempt path clears the notice. No second action taxonomy was added.

Success also checks that no newer rejection replaced the observation since that
request began; an older background response cannot erase a newer cap. Unit
coverage verifies this ordering. All **4 focused browser cases passed** in 6.7 seconds: structured success,
cancellation, plain-question success, and success after navigation. Results are
retained in [playwright-admission-boundary.txt](playwright-admission-boundary.txt).

The final change does not alter the notice's rendering, placement, wording,
reset calculation, or dismissal/expiry behavior. The complete 31-case run and
16 captures below remain applicable; focused revalidation checks the changed
success path. Full web tests (2,182), lint, production build and modularity have
passed; exact-head CI and Codex review are recorded in the final PR audit.

## Composer notice and lifecycle

Validated runtime commit: `cb3d305de2fdad813722a6d550ad5535d5ac92c6`.
The [complete acceptance output](playwright-lifecycle.txt) records the final
package run: **31 passed in 33.5 seconds**. All 16 after images were recaptured at that commit. The eight
429 images supersede the earlier transcript-positioned notices; the eight
503 images preserve the existing recovery presentation.

The notice appears once above the composer, outside all message rows, with
an accessible Close button. English and Spanish both use `AM`/`PM`; a single
nonbreaking separator keeps the time and day period together on mobile.
The last rejected question stays above the notice, verified by measured
bounding boxes at 360px. No empty assistant placeholder remains.

Lifecycle acceptance covers repeated429 deduplication with no automatic retry,
same-tab reload and New chat, dismissal retained through reload and resurfacing
on a new rejection, timer/focus expiry, successful question/reload, success
after navigation, account isolation, and the first guest send after bootstrap.
The composer remains editable. The rejected question is local; reload restores
the server transcript rather than promising to persist a denied turn.

The runtime build, unit and backend evidence is in [verification.md](../verification.md).
All browser API responses were mocked; no provider or production account was
used. The browser time zone and clock remain those in [README.md](../README.md).
This run supersedes earlier after images. Later evidence-only commits retain
this validation when their runtime diff is empty.

## Earlier AM/PM formatting

Validated source commit: `b56ce0bd4eb0a397cfc1900727abcb75de5e8ef4`.
The complete package suite passed **22 tests**, with the
[output retained](playwright-day-period.txt). All 16 after images were
recaptured on that exact commit. Four Spanish daily-cap images changed to
`8:00 PM`; the four English daily-cap images and eight claim-recovery images
remained byte-for-byte unchanged.

Both languages now assert the same uppercase, unpunctuated `PM` marker,
with one separating space and one sentence-ending period. EN and es-419
mobile captures were visually inspected: the quiet notice fits at 360px,
the reset time is readable, and no answer controls appear.

The browser was set to `America/Santo_Domingo`. The mocked receipt time
was `2026-08-13T18:17:32Z`; `Retry-After: 20548` reaches the next UTC
midnight, displayed as `8:00 PM`. The missing-header cases reached that
same reset using the browser clock. These browser checks exercise display
behavior; backend quota-policy verification is recorded separately by the
main task.

All API responses were mocked, with no backend or provider calls. The owned
mock web server was stopped after capture. This run supersedes the after
images referenced by the historical runs below.

## Quiet daily-cap notice history

Validated source commit: `b9404df285f210587c6fb586dd6478bff7f707a9`.
The complete package acceptance run passed **22 tests**, with the
[output retained](playwright-quiet-notice.txt). All 16 after images were
recaptured on that exact source commit. Eight daily-cap images now show the
quiet bordered failure notice; the eight claim-recovery images remained
byte-for-byte unchanged.

Every daily-cap case, including a new chat, now asserts:

- One visible `recovery-failure-notice` with `role="status"` and exact
  English or Spanish reset-time text.
- No buttons in the containing message, including hidden Copy, rating,
  and More Actions controls.
- The question remains visible, with no raw backend error or vague wait.

EN and es-419 mobile images were visually inspected. The notice fits the
360px viewport, the reset time is readable, and there are no answer controls.
Both account kinds and the existing 503 retry behavior passed. The run used
only mocked API responses; no backend or provider calls were made. The owned
mock web server was stopped after capture.

## Initial implementation history

The following run predates the quiet-notice change and does not validate its
appearance. The current run above supersedes its after screenshots.

Validated source commit: `d604a816f5415f0681541befb7baa09fd7d986f9`.
The 22-case run began at `f83f4124`; the only intervening commit changed
evidence documentation. `git diff f83f4124 d604a816 -- web` is empty.

- Package acceptance: **22 passed in 21.4 seconds**. The
  [complete output](playwright-exact-head.txt) is retained.
- All **16** newly captured after PNGs were byte-for-byte identical to
  the committed after evidence (SHA-256 comparison, zero mismatches).
- Existing #681 guest recovery tests: **3 passed**. The
  [complete output](guest-regression.txt) is retained.
- The #681 spec was copied temporarily with only its screenshot output
  directory changed to `/private/tmp/argus-693-guest-regression-shots`.
  Assertions and fixtures were unchanged. The copy was removed after the run;
  `docs/reports/evidence/677` has no diff.

Both runs used the mock web server and Chromium. The package run used the
documented Dominican Republic time zone; #681 retained its existing default
browser time zone. No paid provider or backend calls were made. The owned
local web server was stopped after validation.
