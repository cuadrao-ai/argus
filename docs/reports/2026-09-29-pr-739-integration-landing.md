# PR #739 integration landing

## Landed change

- PR: [#739](https://github.com/lagarcess/argus/pull/739)
- Approved PR head: `608ed936706837d1b36d0b73db2f0a087d54d28d`
- Integration parent at gate: `19550f28e344c1004dd3ea366625c25fae4b3355`
- Integration parent at squash (after [#738](https://github.com/lagarcess/argus/pull/738)): `00368a64658a106ee705db241a92d3b1aabce127`
- Squash merge: `738e11a4813f85feff051e6bb4f3d05fc19453a1`
- Merge time: September 29, 2026, 01:17:45 UTC

## Outcome and remaining work

Android registered-session continuity behind local opt-in (`ARGUS_ANDROID_LOCAL_AUTH`).
Device-bound encrypted credential storage, official Supabase Kotlin SDK refresh
and revocation, bilingual profile/session controls, and browser recovery handoff.
Financial features remain samples. Authentication remains default-off and
local-debug-only.

No server, API/data contract, iOS, web, analytics, migration, or hosted
configuration changes. No production CAPTCHA, app identity, signing,
distribution, or guest-conversion acceptance in this land. No deployment or
`main` promotion.

## Accepted evidence

- Pre-merge worker gates on `608ed936`: applicable CI SUCCESS (backend,
  frontend, guest-release, ownership, docs-change, aggregate `ci`), Private
  Alpha Local Smoke SUCCESS, Android Foundation `build-test-lint` SUCCESS;
  Codex latest-delta Completed clean on `608ed93` ("Swish!"); **0** unresolved
  review threads; behind_by **0** vs `19550f28` at gate time; `mergeable_state:
  clean`.
- Intervening integration before squash: [#738](https://github.com/lagarcess/argus/pull/738)
  at `00368a64` (iOS-only tree). No shared files with #739; no semantic overlap
  on runtime owners, API/data contracts, migrations, or env templates.
- Squash tree for android + committed evidence matches approved head
  `608ed936`.
- Durable evidence under `docs/reports/evidence/android-registered-session/`
  and baseline `docs/reports/android-registered-session.md`.
- Terminal audit: https://github.com/lagarcess/argus/pull/739#issuecomment-5881145827

## Documentation and environment audit

This landing adds the integration register entry and this report. Android local
debug variables (`ARGUS_ANDROID_*`) remain documented in
`mobile/android/README.md` for explicit local opt-in; they are not hosted
service variables and do not require `.env.example` / `web/.env.local.example`
/ `render.yaml` changes. No secrets inspected or rewritten.

Direct push to integration is expected to be rejected (branch protection),
so this register ships through a docs-only PR (same pattern as #734 / #736 /
#737). Exact-head tip CI/smoke after the product squash are recorded when
those checks reach terminal state.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, or merge of #732 / #735.
[#732](https://github.com/lagarcess/argus/pull/732) remains design hold.
[#735](https://github.com/lagarcess/argus/pull/735) remains account backend
only and was not a hard land blocker for #739. #646 and #634 were not touched.
