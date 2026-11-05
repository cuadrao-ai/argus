# Consumer PR #937 integration landing

Lucas approved the merge on October 9, 2026, after accepting the committed
simulator evidence and green CI. VoiceOver and Switch Control are no longer
part of this PR's gate. Their physical checks are unverified, not passed.

## Source and retained evidence

- [PR #937](https://github.com/lagarcess/argus/pull/937) was squash-merged as
  `43fac94de2672600079f312258908f05747a9d63` from accepted head
  `87d7a8ab64b6e448fddb69088fda796df24fd079`.
- Original base, freshly fetched pre-merge integration and squash parent all
  equal `bbf4da23f01296af4ac639386fe9a0960218a49f`. No intervening overlap or
  reconciliation merge was needed.
- Accepted head and landed commit share tree
  `70af653329b0c2393cd342cb95d3c0260e15056b`; the four committed simulator
  results remain valid. [Checkpoint evidence](evidence/pr-937-consumer-checkpoint/README.md)
  separates real local API/Postgres persistence from sample-preview checks.
- Pre-merge applicable CI and local smoke passed; docs checks were skipped.
  Zero unresolved review threads. The checkpoint records a clean independent
  review of the latest test delta. The known six model-test failures remain
  tracked in [#898](https://github.com/lagarcess/argus/issues/898).
- Modularity and whitespace checks passed on the accepted, now landed tree.
  There are no new environment variables, migrations or feature activations.
- Build 3455 installation and launch on the physical iPhone were verified.
  Its local backend configuration does not prove hosted money flows.

The canonical integration checkout was clean and fast-forwarded to the squash
commit. The final PR landing comment records terminal integration CI, smoke and
any documentation housekeeping head so this report does not predate their result.
GitHub rejected the direct housekeeping push because integration requires a pull
request. The notes are preserved on `codex/cuadrao-consumer-lane`; canonical
integration was restored clean at the merged remote head without discarding the
documentation commit. Lucas subsequently requested the documentation-only PR.
Documentation landing therefore remains open until that PR is reviewed and merged.

## Assigned next outcome

Complete the signed-in free manual-money journey against
`https://cuadrao-api-staging.onrender.com` only: accounts, transactions, budgets,
goals, search/find later, separate currency totals, corrections and correct
balances after relaunch, in Spanish and English with large text.

[#877](https://github.com/lagarcess/argus/issues/877) stays open because these
connected journeys remain to be accepted. No more accessibility tooling.
Guest mode, saved receipts and shared plans remain locked; the transaction-sheet
redesign stays parked. RevenueCat is outside this assignment. No TestFlight
upload, new phone installation, deployment or hosted configuration/schema change
is authorized by this landing.

Consumer owns the native client. Shared ingestion, authentication, API contracts,
schemas and runtime require coordination with their existing owners. The
staging owner's C0/C1 report pins backend `cad1cbe1ec27ff89c08eadbec31718a0e627383c`;
current integration expects later Business schema columns. Verify the existing
staged API before proposing any shared change. A healthy service and a stored
conversation alone do not establish manual-money acceptance.

The [staging evidence](evidence/consumer-staging-preflight-20261009/README.md)
records the initial disabled-gate 404s and the later approved setup. The staging
owner enabled only `ARGUS_FINANCIAL_ACCOUNTS_ENABLED=true` and deployed the same
`cad1cbe1e` revision after a restart alone did not apply the saved setting.
Deploy `dep-db4qeilckfvc73fss4kg` is healthy and authenticated accounts return HTTP
200. Other environment values and both migration ledgers are unchanged. The
synthetic login is available through a private handoff. No further hosted change
is authorized. The first native account correction/relaunch test passed;
broader acceptance remains incomplete, with failed attempts retained in the
evidence report.
