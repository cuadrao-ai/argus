# Issue 688 browser safety evidence

## Scope and provenance

Captured with Chromium and the committed provider-free Playwright fixture at
`c4ca2a517e05339515e753d7bad0b52b03b67861` on 2026-09-27 UTC.
Original integration baseline: `ab9143c18740c28f582646d405445c01c4c8aff4`.
The account implementation includes the nonblocking post-claim completion fix `d56fc9be`; the image implementation is `b54f8564`.
The final expired-view styling is `222037e3`; canonical research hydration is
asserted by the browser fixture at `dec393c4`.
The evidence commit adds screenshots and this report, with no runtime changes.

This is **simulated authentication evidence**, not real Supabase authentication
or a backend authorization audit. `NEXT_PUBLIC_MOCK_AUTH=false` exercises the
actual Supabase browser client, cookie parsing, `getSession`, `setSession`, and
native cross-tab BroadcastChannel notifications. Synthetic unsigned tokens and
invented profiles are accepted only by the isolated fixture HTTP server.
Next server-side `getUser` and the public receipt read use that same local server.
No customer data, paid chat, market provider or real account was accessed.

Two Chromium tabs share browser cookies. For cross-tab cases, tab B updates the
Supabase session cookie and posts the actual auth channel event. The ordinary
send test intentionally suppresses the event, proving the send boundary checks
current credentials even while tab A still displays its old draft.

## Baseline reproduction

A clean `git archive` of the original integration SHA was served from a temporary
directory with these synthetic fixtures. No original checkout was edited.

| Original behavior | Observed browser requests |
| --- | --- |
| Private, research and shared Markdown image syntax | 3 automatic requests to `tracking.example.invalid`; each was intercepted and aborted |
| A draft remains open; cookie switches to B without auth event; submit | 1 stream request containing A's draft authenticated with B's synthetic bearer token |
| Same stale state, first stream answers 404 | B-authenticated stream 404, conversation create, and resend: 3 requests |

These baseline assertions passed by expecting the unsafe original behavior. They
are separate from the fixed-behavior regression suite. No request reached the
external tracking host.

## Review regression: failed Recents refresh after guest claim

At `c3412e54`, the new browser case reproduced the reviewed defect: login and
claim succeeded, then the actual `GET /conversations?...` Recents refresh returned
503. The old catch rechecked the source guest identity and replaced the claimed
conversation with the account-change/reload screen. The expected login error
modal was absent. This was a confirmed browser failure, not a speculative case.

The first repair retained the destination identity but left the sign-in modal
open after consuming the handoff. At `90b0b7be`, a stronger browser regression
confirmed that the modal failed to close automatically after Recents returned
503. The fixture now makes the claim single-use and counts handoff/login calls,
so a second authentication cannot accidentally repair the fixture state.
[Historical error-modal capture](baseline-post-claim-recents-error.png) was taken
at `2544aaf2`; it is **obsolete baseline evidence**, not final behavior.

At `d56fc9be`, successful, failed and held Recents refresh cases close the modal
automatically after the canonical claim completes. The claimed conversation and
destination identity remain available; no message sends automatically. One
subsequent deliberate message uses the destination token. Each case performs
exactly one handoff and one login. The fixture keeps the Recents outage active
throughout the failure case.

At `64a6a236`, a separate held-response test reproduced the remaining ordering
problem: an exhausted guest's Run backtest action opened conversion; claim B
completed and its modal closed, but no resumed stream started within five seconds
while Recents remained pending. The final fixture now covers this explicit
`simulation_limit` action. On the fixed head it emits exactly one `run_backtest`
stream authenticated as B before releasing Recents. Releasing the response does
not emit another stream. This verifies submission/ownership only: the fixture
does not run a backtest engine or claim a completed simulation. The composer can
remain disabled while the synthetic simulation has no completion artifact.

## Browser acceptance

All 16 Chromium cases pass in 47.6 seconds. Screenshots contain synthetic fixture data only.

Run from `web/`:

```sh
ISSUE_688_EVIDENCE_DIR="$PWD/../docs/reports/evidence/issue-688" \
node node_modules/@playwright/test/cli.js test \
  --config e2e/issue-688-browser-safety.playwright.config.ts
```

The local Next server uses port 3688 and the synthetic auth/receipt server uses
port 5688. Webpack supports this checkout's dependency symlink; build output is
isolated in `.next-688`. Both servers stop with the test runner.

| Verification | Expected outcome and evidence |
| --- | --- |
| Private, research and shared conversation Markdown | Zero tracking requests and zero remote image elements; readable alt text and 3 ordinary safe links. [Screenshot](markdown-images.png) |
| Real public `/r/` receipt route | Zero tracking requests, readable alt text and safe link. [Screenshot](public-receipt-images.png) |
| Actual response CSP and existing Argus icon | Header contains `img-src 'self' data:`; `/icons/argus-192.png` decodes with positive natural width |
| Cross-tab switch A to B | Zero create/stream requests, A transcript and draft removed, localized notice. [English](account-switch.png), [Spanish](account-switch-es-419.png) |
| Cross-tab logout | Zero create/stream requests; draft and transcript removed. [Screenshot](logout.png) |
| Cookie switches without broadcast before ordinary submit | Zero create/stream requests; canonical credential mismatch closes stale view |
| Switch with pending stream response | Only the original A request; no late response enters the new view. [Screenshot](switch-pending-stream.png) |
| Switch while 404 response is pending | Only the original A request; no recovery conversation or resend. [Screenshot](switch-pending-404.png) |
| Switch during 404 recovery create | Original stream and create remain authenticated as A; no resend. [Screenshot](switch-pending-create.png) |
| Switch during initial new-chat create | One create authenticated as A; no stream follows. [Screenshot](switch-pending-initial-create.png) |
| Same-user token refresh | Draft retained and one stream uses refreshed A token |
| Same-user 404 recovery | Exactly original stream, replacement create, resend; all as A. [Screenshot](same-user-404-recovery.png) |
| Explicit guest claim | Existing login modal, verified synthetic claim, actual browser `setSession`, retained conversation; no automatic send, deliberate follow-up uses destination identity. [Screenshot](guest-claim.png) |
| Guest claim followed by Recents failure | Modal closes automatically, one handoff/login completes, claimed conversation remains available, zero implicit sends and one deliberate destination-account send. [Retained view](guest-claim-recents-failure.png) |
| Guest claim with held Recents | Previously requested simulation resumes once as B before the history response is released; releasing it does not duplicate the action. [Pending projection](guest-claim-held-recents.png) |
| Cold guest first send | Bootstrap establishes guest identity; exactly one stream is sent with that identity. [Screenshot](cold-guest-first-send.png) |

The pending-stream fixture holds the HTTP response; it verifies request
cancellation and late-response exclusion, not incremental network chunk timing.
Existing unit tests cover request-session authorization throughout stream events.
This fixture verifies client ownership enforcement. It does not claim that a
backend can retract a request already accepted under its original A identity.

## Other verification supplied by release captain

- Frontend: 2,193 unit tests pass; complete lint has zero errors and 8 existing warnings.
- Next production webpack build and TypeScript check pass.
- Backend: 9,056 passed, 617 skipped; 89% coverage, 568.30 seconds.
- Mocked evaluation harness: 272 passed (also included in the backend suite).
- Ruff, documentation ownership and modularity checks pass.
- Backend verification used a temporary environment with the exact locked SciPy
  1.15.3 official macOS 12 wheel; no shared environment or lockfile was changed.

CI and terminal review status belong to the final PR audit, not this capture.
