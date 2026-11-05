# PR #721 integration landing

## Landed change

- PR: [#721](https://github.com/lagarcess/argus/pull/721)
- Approved PR head: `2f3b9eb21ad860c3ff3dcfe559e7829fe05cb2a1`
- Integration parent: `f0a90763b79e5625ac0a4789cdfa171cda023963`
- Squash merge: `3b9313f3dcf80e3ff9eddfcce8818a829a081225`
- Merge time: September 27, 2026, 22:16:02 UTC
- Landed tree: `efd6f6a68401533612aca0249d679c975661d436` (matches approved PR head tree)

PR #721 was already the tip of `codex/private-alpha-next` when this landing
ran. No later integration SHA had recorded a superseding landing for this
change.

## Outcome and remaining work

`focused_discovery_payload_response` and `_classify_question` no longer attach
`error=str(exc)` to DEBUG Loguru records. Both catchers log `error_type` and
`error_origin` (via shared `exception_origin`) and keep returning `None`. A
serializing sink therefore no longer receives the exception string from these
two sites. Other `error=str(exc)` callers, global sink redaction, prompts,
migrations, and hosted configuration stay unchanged.

Linked triage issue [#710](https://github.com/lagarcess/argus/issues/710)
tracks the same two callers. Its named acceptance bar for those catchers is
met by this merge. **Proposed closure of #710 is reported separately and is
not executed by this landing.** Deployed sink exposure remains unconfirmed and
outside the landed scope.

## Accepted evidence

- Focused verification cited on the PR: private-log catcher regression plus
  discovery/knowledge suites and interpreter prompt-freeze (48 cases across the
  listed commands), with `ruff check` clean on the three edited files.
- Exact-head integration CI on merge SHA `3b9313f3`:
  - [CI](https://github.com/lagarcess/argus/actions/runs/36354689575): success
  - [Agent Runtime Regression](https://github.com/lagarcess/argus/actions/runs/36354689608): success
  - [Private Alpha Local Smoke](https://github.com/lagarcess/argus/actions/runs/36354689589): success
- Codex review completed on approved head `2f3b9eb` with no findings.

## Documentation and environment audit

This landing adds the integration register entry and this report. The active
execution board is unchanged: #721 is a bounded debugging-privacy repair, not
a board lane, and board tip reconciliation remains with the documentation
batch (#672). No API contract, OpenAPI, data-model, or product-doc change is
required. The runtime diff adds no environment names, feature flags,
migrations, hosted settings, or tracked-template requirements. No ignored
environment file or secret value was changed.

## Authority boundary

This checkpoint stops at `codex/private-alpha-next`. No main promotion,
deployment, hosted configuration change, customer-data access, paid
evaluation, live provider call, tester exposure, or merge of any other PR is
part of this landing. #646 and #634 were not touched.
