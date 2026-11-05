# PR #735 integration landing

## Landed change

- PR: [#735](https://github.com/lagarcess/argus/pull/735)
- Approved PR head: `a2f53c16fefee352f256632bc657550311cd6e19`
- Integration parent at squash: `e3f9db651ade97512107e835dbf442aacf637641`
- Squash merge: `296195e86c972e846c251d256b3cc211975bfd57`
- Merge time: September 29, 2026, 02:56:56 UTC (`2026-09-28T21:56:56-05:00`)

## Outcome and remaining work

Financial accounts first slice behind `ARGUS_FINANCIAL_ACCOUNTS_ENABLED`
(default-off). Registered users can create, list, reopen, edit, and write or
correct an opening balance with revision history. Opening writes require
caller-visible `expected_version` (stale-opening hold fix on tip `a2f53c16`).
While the flag is off, every route answers `404 financial_accounts_unavailable`
before authentication.

No hosted feature enablement. No production deployment. No `main` promotion.
[#732](https://github.com/lagarcess/argus/pull/732) design hold untouched.
No linked GitHub issue was attached to #735 for auto-close; none retained open
as a merge prerequisite. Client wiring across interfaces remains follow-on work
against the accepted contract.

## Accepted evidence

- Pre-merge worker gates on `a2f53c16`: tip CI SUCCESS (10 checks; docs-checks
  skipped), Codex Completed clean (“Didn't find any major issues”), **0**
  unresolved review threads, behind_by **0** vs `e3f9db65`, modularity clean on
  reconciled tree, fixer re-READY after stale-opening HOLD.
- Durable evidence under `docs/reports/evidence/financial-accounts-first-slice/`.
- Contract: `docs/API_CONTRACT.md` §17.3, OpenAPI, lane spec, DATA_MODEL.
- Post-squash product tip `296195e8` exact-head:
  - [CI](https://github.com/lagarcess/argus/actions/runs/36514949476) `success`
  - [Private Alpha Local Smoke](https://github.com/lagarcess/argus/actions/runs/36514949394) `success`

## Documentation and environment audit

Flag already declared in product squash (`.env.example`, `render.yaml`,
`.github/argus-env.sh`, release profile) as default `false`. This register adds
the landing report, ledger entry, and authority note only. No secrets rewritten.
Hosted `ARGUS_FINANCIAL_ACCOUNTS_ENABLED` remains unchanged / default-off.
`git diff --check` clean for this housekeeping tree.

Direct push to integration was rejected (branch protection GH006), so this
register ships through a docs-only PR (same pattern as #734 / #736 / #737 /
#740 / #741). After this register merges, the sole lander records the
housekeeping tip SHA, proves clean local/remote parity
(`HEAD == origin/codex/private-alpha-next`), and records terminal exact-head
CI/smoke on that tip when those checks complete — in the #735/#742 completion
comment and Project landing log. This report does not invent those post-merge
results in advance.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted Blueprint sync, tester exposure, or merge of #732.
[#732](https://github.com/lagarcess/argus/pull/732) remains design hold.
#646 and #634 were not touched.
