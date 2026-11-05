# Stopped iPhone account client: recovery checkpoint

This is the historical stop record. Current restart authority, recovered source
and acceptance status live in the
[execution manifest](../../../specs/argus-execution-board.md#active-financial-loop-batch).

Saved September 29, 2026 at the founder's request. **Preservation only. Not a
working-build, review-ready, merge-ready or deployment claim.** Implementation
remains stopped; this checkpoint does not resolve the earlier build approval
rejection or authorize restarting the lane.

## Find the work

- Remote branch: `origin/codex/ios-financial-accounts` in `lagarcess/argus`.
- Preserved worktree: `/Users/garces/.codex/worktrees/8be2/private-alpha-next`.
- Original integration/product base: `296195e86c972e846c251d256b3cc211975bfd57`.
- Spec-first commit: `a0424297e5559af641bfc4b8181fced662d428e2`.
- Scope: [bounded lane spec](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-09-29-ios-financial-accounts.md).
- Shared execution manifest: `docs/specs/argus-execution-board.md`, owned by
  the delivery lead in [PR #743](https://github.com/lagarcess/argus/pull/743).
  Its iOS recovery row points to this branch and checkpoint. Do not copy the
  manifest into this worker or treat the older lane spec as a restart grant.

The checkpoint retains the unfinished `ios/ArgusFoundation/Accounts/` views,
existing-session injection, localization, typed account requests, session-owned
transport, deterministic/opt-in tests and local acceptance helpers. No backend
or shared canonical documentation changes are included. No new PR is opened.

## What was checked before the stop

- Package run reported 33 deterministic tests passed and four opt-in tests
  skipped. The six new deterministic checks cover lossless wire values,
  concurrency tokens, request replay, coded failures, bounded refresh and late
  responses after identity retirement. This is not native UI acceptance.
- `api-journey.json`: 63 local real-auth/HTTP/Postgres assertions, including
  known/zero/unknown, exact large values, debt corrections, date-only carry
  forward, nickname clearing, conflicts, archive/restore, isolation and errors.
- `api-unavailable.json`: default-off response before authentication.
- `api-readback.json`: token refresh and seven exact record reads after API
  process restart. The database was retained; this is not a database restore.

Those JSON files were captured while the helpers were uncommitted. Their
`source_commit` is the then-current spec commit, **not** an assertion that the
helper bytes existed in that commit. The helper source is preserved by this
checkpoint. No new acceptance tests were run for preservation. The standalone
HTTP harness does not establish native app behavior or cross-surface sync.

## Incomplete work and known gaps

- Native build was not verified: automatic approval review rejected the Xcode
  build because it interpreted the direct authorization as authentication-only.
  No workaround was attempted. Founder subsequently stopped all work.
- Accounts UI tests, two-size native screenshots, accessibility/layout/theme
  checks, native relaunch proof and the opt-in Swift live account test are
  incomplete or unrun. `ios/ACCOUNTS_SETUP.md` is not written; README links to it
  are unfinished, not working setup instructions.
- The type chooser directly changes the draft while a create retry is frozen;
  its visible type can differ from the frozen submitted payload.
- Local amount/share validation errors incorrectly enter stale/uncertain-write
  reconciliation on existing-account forms despite no request having been sent.
- Negative entry needs an accessible sign control; the decimal keyboard alone
  does not provide one. Asset ownership controls still need locked-design review.
- No independent final review, current-integration reconciliation, final CI,
  reviewed implementation PR or release readiness was completed.

After an explicit restart, inspect actual code and the current authority/MVEE/
execution manifest, resolve authorization and ownership, then resume the scoped
fixes and native acceptance. Do not assume the partial UI is usable from these
backend checks or start replacement work without inspecting this branch.

## Preserved local state and stopped resources

Ignored `ios/.build/accounts-local/` retains the local stack configuration,
synthetic client credentials, private API state, raw logs and restart data.
Ignored `ios/Config/Local.xcconfig` contains local public endpoint configuration.
The lane `.venv` and package/build caches are local artifacts. **None of these
ignored files is pushed; do not publish credentials or raw responses.** Keep
the worktree and stopped `ios-accounts` Docker volumes to retain this context.

At stop, the owned API (58400), CAPTCHA bridge (58405), and `ios-accounts`
Supabase containers were stopped with database data retained. No lane review
monitor is running. The account-journey heartbeat and all inspected Argus
scheduled runs are paused.

Owned compact simulator `197C9C31-77FD-4D31-A9C6-EACA55732B15` is shut down.
The large simulator `0335699A-C522-492B-A8C3-8FD3D7CAC06A` was not used for this
lane. Founder simulator `8B7975F1-1338-4966-90E2-770416CAF174` was left untouched.
Do not reset shared services, erase simulators or remove the preserved worktree.
