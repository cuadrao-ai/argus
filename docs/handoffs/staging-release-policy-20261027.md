# Staging release policy addendum, 2026-10-27

This portable handoff supplements the existing release roadmap. It grants no
publication, hosting, migration, credential, permission, or provider authority.

## Release rules

- Approved UI normally releases directly after its implementation and acceptance
  gates pass. A merge or deployment alone does not establish delivery.
- Every temporary flag records its owner, concrete risk, current value, and an
  expiry or removal criterion. Do not keep approved, connected UI hidden without
  a named reason. Do not remove a gate that would expose simulated persistence.
- A small Business-scoped rollout needs a specific risk and a canonical scope.
  A global boolean is not a Business-scoped rollout.
- Shadows must be side-effect-free. No hidden writes, paid/model/provider work,
  sends, permissions, or invented progress may run behind a shadow.
- Migrations need proven mixed-version compatibility or an approved coordinated
  recovery plan with verified backup, write hold, release order, and readback.
  Migration approval does not authorize API/web releases or configuration changes.
- Acceptance uses normal login, correct account/Business/grant, actual deployed
  API/web SHAs, observed routes and active behavior. Record saved configuration
  separately from newly verified running or compiled behavior.
- Accept the entire approved checkpoint, including subpages and controls. Hidden,
  unwired, example-only, or locally simulated features remain delivery gaps.
- Keep existing authorization, consent, safe retry, exact money, and provider
  controls. A frontend gate is not the security boundary.
- Marketing sign-in remains staging-host-only. No production destination or
  deployment is inferred.

## Current application and authority

This policy was drafted at local commit `269ac3519`; its former proposed editing
bundle is historical. The later parser-only #1400 repair and editing activation
completed: API `dffee6925`, web `c74221f69`, both invoice editing flags on, one QA
customer/incomplete draft saved, reloaded and retried exactly without duplicates.
Fiscal service/contact remain off. See the [current checkpoint](../START_HERE.md)
and [gate ledger](../reports/staging-checkpoint-gates-20261027.md) for boundaries.

The earlier review found no safe gate-only product fix. Missing durable contracts
still cannot be solved by exposing mock controls. The completed editing bundle
does not authorize fiscal preparation/submission, payments, schedules, sending,
credential or callback/manifest changes. Preserve saved records on rollback.

Flags must also name their activation authority and removal criteria; distinguish
source defaults, saved settings and observed running/compiled behavior. Ordinary
UI releases remain the default once implementation and normal-login acceptance
pass, while consequential provider and authorization boundaries remain explicit.
Documentation publication/merge is authorized. Further implementation, migration,
release and provider actions need their own existing or new scoped authority.
