# PR #738 integration landing

## Landed change

- PR: [#738](https://github.com/lagarcess/argus/pull/738)
- Approved PR head: `fe6379d342152e15d04888305114cdeac4096d48`
- Integration parent: `19550f28e344c1004dd3ea366625c25fae4b3355`
- Squash merge: `00368a64658a106ee705db241a92d3b1aabce127`
- Merge time: September 29, 2026, 01:17:39 UTC

Immediately after this squash, [#739](https://github.com/lagarcess/argus/pull/739)
(Android registered sessions) squash-merged as
`738e11a4813f85feff051e6bb4f3d05fc19453a1` (01:17:45 UTC) onto the same
integration tip. First-parent order is `#738` then `#739`. This register
records the #738 landing; the #739 lander owns that product's register.

## Outcome and remaining work

Default-off iPhone registered-account sessions behind local auth
configuration. Login, signup, Keychain restore/refresh/sign-out use the
existing Argus contract and official Swift Auth SDK. Financial destinations
remain labeled samples. Guest transfer, generic resend, native recovery
callbacks, production CAPTCHA hosting, and app signing/identity remain
explicit follow-ups.

No backend, web, migration, hosted Blueprint, or `main` changes. No linked
issue auto-close. No deployment.

## Accepted evidence

- Pre-merge worker gates on `fe6379d`: applicable CI SUCCESS (PR
  `36499931151`, push `36499898762`) plus Private Alpha Local Smoke SUCCESS
  (`36499931027`); Codex Completed clean on exact head with zero unresolved
  review threads; integration ancestor with no intervening commits and no
  semantic overlap; `mergeable_state: clean`.
- Durable evidence under `docs/reports/evidence/ios-auth-session/` and setup
  in `ios/AUTH_SETUP.md`.
- Terminal readiness audit:
  https://github.com/lagarcess/argus/pull/738#issuecomment-5881004199

## Documentation and environment audit

This landing adds the integration register entry and this report.
`ARGUS_AUTH_ENABLED` and related local iOS xcconfig keys are client-local
only (`ios/Config/*`, `ios/AUTH_SETUP.md`). `.env.example`,
`web/.env.local.example`, `render.yaml`, and `.github/argus-env.sh` are
unchanged by the product squash and by this housekeeping. No secrets
inspected or rewritten.

Direct push to integration is expected to be rejected (branch protection),
so this register ships through a docs-only PR (same pattern as #734 / #736 /
#737). The housekeeping tip's final SHA, clean local/remote parity, and
exact-head CI/smoke after that merge are recorded when those checks reach
terminal state.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, or merge of #732 / #735
is part of this landing. #735 was not a hard API blocker for native auth
(existing login + bearer `/me` only). #732 remains design hold. #646 and
#634 were not touched.
