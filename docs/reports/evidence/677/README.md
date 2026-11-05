# Issue 677 evidence

Playwright captured the mocked 503 guest-claim error on
`9fa00690` (before). The after images were refreshed on 2026-09-26 at
`20dffebca24f14e1a2e456dfa802f95b7bf7aeab`, after merging integration.
The API body still says
`Argus could not start this turn. Please try again.`; the client on this
branch maps `guest_compute_claim_unavailable` instead of rendering that
English detail.

| Locale | Before (`9fa00690`) | After |
| --- | --- | --- |
| en | [before-en-claim-503.png](./before-en-claim-503.png) | [en-claim-503.png](./en-claim-503.png) |
| es-419 | [before-es-419-claim-503.png](./before-es-419-claim-503.png) | [es-419-claim-503.png](./es-419-claim-503.png) |

A second claim 503 on Retry used to reload `GET .../messages` (empty, because
the claim runs before the user turn is saved) and wipe the local transcript.
`en-claim-503-retry-again.png` is the after of that path: the composed
message, localized notice, and Retry countdown stay on the second 503.

## Integration reconciliation

- Original integration base: `9fa0069027dfd19e02d5ab090b2051d0dfdf7dd7`.
- Current integration: `f7c002d940f146a027166a95b6f1d8e8aa915bd6`.
- Merge commit: `20dffebca24f14e1a2e456dfa802f95b7bf7aeab`, preserving
  PR head `fff96b69934ada5647c41f55d1eec8de03cc8261` as its first parent.
- No textual conflicts. Semantic overlap is the guest compute admission
  boundary and its HTTP error contract: #678 exposes `Retry-After` and
  `X-Request-Id`; #699 moves the claim after conversation/replay validation
  while retaining the pre-persistence 503 response. The frontend state owner,
  localization keys, and retry payload are unchanged by integration.
- Integration's registered-account counter, migration, and environment
  variables do not change guest recovery. This PR adds no migration or flag.
- Historical before images remain baseline evidence. Earlier after evidence
  is replaced by the refreshed images and [local test output](./guest-compute-claim-503.txt).

## Local browser verification

From `web/`:

```sh
bunx playwright test e2e/guest-compute-claim-503.spec.ts --workers=1
```

Result: **3 passed (21.8s)**, no retries. The cases cover English and Spanish
localization, disabled countdown, one user-initiated retry with the same text,
and transcript preservation through a second 503 before success.

This is local Chromium evidence using mocked HTTP and auth, with no model or
market-data calls. It does not claim hosted-provider acceptance. The affected
surface is transport recovery and is independent of strategy shape. The spec
is not part of CI; CI runs only the browser-storage disclosure spec.

The PR's terminal verification comment records the final head, its repeated
browser check, backend contract checks, CI, and completed Codex review. This
capture record is not a terminal readiness claim.
