# PR #773 integration landing

_Recovered from draft PR #774 on October 6, 2026 and reconciled against current integration. The merge facts below were re-verified: `f28b56421` is an ancestor of integration, with parent `15e579315` and tree `2f55d72b`. This report restores the landing register that draft PR #774 held; it does not replace newer board or ledger status._

## Landed change

- PR: [#773](https://github.com/lagarcess/argus/pull/773)
- Approved PR head: `dee829f8a3a7f83fb25cd81aaf3fa6deac8bfe45`
- Integration parent at squash: `15e57931584b21dd7f9e453dbeb9127fc4b8cff3`
- Squash merge / tip: `f28b56421caf71d6610caf1cce891e1848e0ace1`
- Merge time: October 2, 2026, 00:47:28 UTC
- Tree identity: squash tree `2f55d72b3b34bca3925208e7b705d286cf08599f` matches worker head tree

## Outcome and remaining work

Default-off shared Household planning on landed membership (#763) and native
consent/activity (#766): budgets, bills, savings goals and debt commitments with
explicit view/edit rights, unequal responsibilities, attributable versioned
changes, record/link/correct/release contributions, private funding redaction,
departure retention freezes, and connected Home/Plan/Search surfaces.

Additive migrations `20261001190000` and `20261002000000`–`20261002050000` are
not applied to production by this landing. They stay clear of the ingestion
reserved block `20261002120000`–`20261002120300`. `CUADRAO_HOUSEHOLDS_ENABLED`
remains default-off in tracked templates. Physical iPhone/internet delivery,
external invitation delivery, hosted enablement, Preview repair, and design
checkpoint `aba489b0…` adoption remain outside this land.

## Accepted evidence

- Pre-merge Exact head `dee829f8…`: PR CI, push CI, and local smoke SUCCESS;
  Supabase Preview SKIPPED at concurrent-branch limit (not a sole gate);
  terminal audit on the PR; Codex P1 contributor-freeze finding fixed and
  resolved; **0** unresolved review threads; modularity budget clean;
  `mergeable_state: clean`.
- Original and current integration at promote: `15e579315…`. Integration did
  not advance; no reconciliation merge; no intervening semantic overlap.
- Durable packet:
  [docs/reports/evidence/shared-household-planning/](evidence/shared-household-planning/).
  Retained demo ports `59750`–`59755` / `ios-accounts-59750` preserved.

## Documentation and environment audit

Landing updates the execution manifest, integration ledger, documentation
authority remainder, and this report. No new production environment variables.
`CUADRAO_HOUSEHOLDS_ENABLED` already present and `false` in `.env.example`,
`render.yaml`, and `.github/argus-env.sh` at the time. On the October 6
readback the flag is `false` in `.env.example`, `render.yaml` and
`.github/private-alpha-release-profile.json`; `.github/argus-env.sh` no longer
carries it. No secrets inspected or rewritten.
No linked issues to close. #768–#772 and Preview untouched.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, design-checkpoint adoption,
ingestion edits, Preview repair, or next-slice start.
