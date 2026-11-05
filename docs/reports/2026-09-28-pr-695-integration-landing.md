# PR #695 integration landing

## Landed change

- PR: [#695](https://github.com/lagarcess/argus/pull/695)
- Issue: [#686](https://github.com/lagarcess/argus/issues/686) (unused `argus-api` onrender hostname hygiene)
- Approved PR head: `a890eee95f8cb698319e79032db6ebd88bb7b661`
- Integration parent: `4e024a4e2837058e73c4be6c528fc41f24d7a03e`
- Squash merge: `25015963600fa9dd9290080bf641238693509a37`
- Merge time: September 28, 2026, 20:28:40 UTC

## Outcome and remaining work

`argus-api` declares `renderSubdomainPolicy: disabled` so the unused
`https://argus-ohr5.onrender.com` hostname is no longer a supported reachability
path. Runbook and public-alpha readiness docs require HTTP `404` from that host
after Blueprint sync; the internet benchmark API URL falls back through
`ARGUS_PRIVATE_LAUNCH_API_URL` from the release contract. This does not close
an IP-trust gap; forged `CF-Connecting-IP` proof remains the #694 promotion-window
test.

No new environment names, migrations, feature flags, or tracked-template
requirements. No deployment or `main` promotion.

## Accepted evidence

- Exact-head CI on approved PR head `a890eee9` before merge (backend, frontend,
  guest-release, aggregate `ci`, Codex clean, 0 unresolved threads).
- Landed tree is the squash of that head onto tip parent `4e024a4e`.

## Documentation and environment audit

This landing adds the integration register entry and this report. Runbook and
readiness prose already shipped inside #695. `.env.example` / `web/.env.local.example`
unchanged. No secrets inspected or rewritten.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, or merge of any other PR is
part of this landing. #723 remains HOLD; #646 and #634 were not touched.
