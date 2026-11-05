# PR #672 integration landing

## Landed change

- PR: [#672](https://github.com/lagarcess/argus/pull/672)
- Approved PR head: `0b534d0040c12520cd03b4b5101b6ab3b24c56d8`
- Integration parent: `acf6639a23be368dbf3848a2b873f4a69d7579c4`
- Squash merge: `86df1ee95cc3c88d713efa6a24538c6217b2ea29`
- Merge time: September 28, 2026, 21:51:06 UTC

## Outcome and remaining work

Docs-only accuracy audit against current integration and founder authority.
Kept still-valid corrections (calculation catalog ownership, memory/sharing
production truth, decision-log locks, promotion deploy proof). Dropped the
draft Wave 1 roadmap revival. Durable promotion evidence lives under
`docs/reports/evidence/2026-09-17-main-promotion/`. Founder execution-board
ownership and revenue/pricing deferral ship in place via
`docs/DOCUMENTATION_AUTHORITY.md` (no separate status PR).

No code, config, workflow, migration, or environment-template changes.
No deployment or `main` promotion. No linked issue auto-close.

## Accepted evidence

- Pre-merge worker gates on `0b534d00`: `docs-checks` + ownership/docs gates +
  aggregate `ci` success (backend/frontend/guest/local-smoke skipped as
  docs-only); Codex clean at 21:38:48Z; 0 unresolved threads; behind_by 0;
  `mergeable_state: clean`; clearer READY naming that tip.
- Post-squash product tip `86df1ee9`: [CI](https://github.com/lagarcess/argus/actions/runs/36488798095)
  and [Private Alpha Local Smoke](https://github.com/lagarcess/argus/actions/runs/36488798007)
  both `success`.

## Documentation and environment audit

This landing adds the integration register entry and this report. Product
docs and board text already shipped inside #672. `.env.example` /
`web/.env.local.example` / `render.yaml` unchanged. No secrets inspected or
rewritten. `git diff --check` clean for the squash vs parent.

Direct push to integration was rejected (branch protection), so this register
ships through a docs-only PR. The housekeeping tip's final SHA, clean
local/remote parity, and exact-head CI/smoke after that merge are recorded in
the #672 landing-completion comment once those checks reach terminal state;
this report does not anticipate those results.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, or merge of any other PR
is part of this landing. #723 remains HOLD (asset-listing lane owns final
audit); #725 remains LANDING HOLD; #646 and #634 were not touched.
