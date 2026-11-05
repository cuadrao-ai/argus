# PR #766 integration landing

## Landed change

- PR: [#766](https://github.com/lagarcess/argus/pull/766)
- Approved PR head: `04831ccb12a46b89a3cd5f5391139d3589321815`
- Integration parent at squash: `09ce4e0af3b6df7a41e2d21c52c67b4fe7c82c0a`
- Squash merge: `079ec8d819f8e2513cc624bfa7a4eb9ca60c7627`
- Merge time: October 1, 2026, 15:10:45 UTC

## Outcome and remaining work

Default-off Household native consent and canonical financial activity on top of
landed #763 membership and #760 connected shell: explicit named-account grants,
view/edit separation, Home/People/invitation/Search/corrections in English and
Spanish, private-leg redaction, owner-qualified history retention, and
server-derived `households_unavailable` gating so disabled Household does not
look like lost membership.

Additive migrations
`20261001120000_household_consent_recovery.sql` and
`20261001130000_household_grant_deletion.sql` are not applied to production by
this landing. `CUADRAO_HOUSEHOLDS_ENABLED` remains default-off in tracked
templates. Physical iPhone/internet delivery, external invitation delivery,
shared Plan/budgets/goals/debt, Business/Custom lifecycle, and hosted
enablement remain outside this land. Design checkpoints `1dcd12a5` and
`1b2005fd9` stay parked.

## Accepted evidence

- Pre-merge Exact head `04831ccb`: PR CI, push CI, local smoke, and Supabase
  Preview SUCCESS; Codex follow-up clean; **0** unresolved review threads;
  modularity budget clean; `mergeable_state: clean`.
- Original assignment base `9b5e8643…`; reconciliation merge `4fed9efb…`
  incorporated #763/#760/#765 landing docs only. Fresh tip at promote was still
  `09ce4e0a…` (integration already an ancestor of the worker). Overlap
  disposition: no intervening tip move after reconcile; no runtime/API/data/UI/
  migration/env/test overlap requiring re-proof.
- Durable packet:
  [docs/reports/evidence/connected-household-native/](evidence/connected-household-native/README.md).
  Terminal scoped audit on the PR supersedes the earlier fda readiness note.

## Documentation and environment audit

Landing updates the execution manifest, integration ledger, documentation
authority remainder, and this report. No new production environment variables.
`CUADRAO_HOUSEHOLDS_ENABLED` already present and `false` in `.env.example`,
`render.yaml`, and `.github/argus-env.sh`. No secrets inspected or rewritten.
No linked issues to close.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, design-checkpoint adoption,
chat/voice slice start, Accounts-tab invention, or Apple-on-connected-path
changes.
