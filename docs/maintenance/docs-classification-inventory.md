# Docs Classification Inventory

## Summary

Snapshot note: refreshed for `codex/private-alpha-next` after P2.0/P2.1 landed
and after the evidence-aware loop was reclassified as source thesis for the
decision memo. Refreshed again 2026-07-07 after the Gate A/B loop, the B4
language-gate retirement, and execution realism landed — see the 2026-07-07 pass
below and the updated rows for the moved/resolved docs.

2026-07-23 pass: the interim slate was reconciled after graph range, account
security, Usage, and capability truth landed. The completed chart-range design
and plan plus the capability-truth design moved to `docs/archive/`; pointer
stubs preserve old links. The duplicate active P2.1 audit was replaced with its
existing archive pointer. The next founder-selected pillar is **Argus always
progresses**, ready for specification only.

2026-10-18 pass: the legacy agent-docs cleanup removed the agent working notes,
the old agent rule and workflow files, the intake-agent instructions and the
handoff templates. Their rows are gone from the table below, and the prior banner pass
lists them by count only.

Current source ownership is defined in
[documentation authority](../DOCUMENTATION_AUTHORITY.md). Read the MVEE for
approved experience and the explicitly assigned package for implementation
scope. The inventory below classifies documents; it does not assign work or
maintain a second priority order. Earlier dated passes above are history.

Quarantine branches are reference material only. Do not broad cherry-pick
runtime work from `codex/private-alpha-next-quarantine-fc231e8`; promote only
small, reviewed, revertable slices.

Release-discipline note: `docs/specs/private-alpha-ci-cd-sota.md` remains the
release-gate reference. It does not own Private Alpha Next product sequencing.

Archive pass: high-confidence stale private-alpha specs and completed checkpoint
docs were moved from `docs/specs/` to `docs/archive/` so active agents do not
mistake them for current command sources.

2026-07-07 pass: after the Gate A/B loop (#140/#142/#153/#146), the B4
language-gate retirement (#154, #174-177), and execution realism (#130/#178)
landed, four more docs moved to `docs/archive/`: the two completed P2.1 specs
(`private-alpha-next-p2.1-capability-audit.md`,
`private-alpha-next-p2.1a-capability-registry-impl.md`) and the two
self-declared-historical top-level docs (`PRODUCTION_READINESS_AUDIT.md`,
`ARGUS_SYSTEM_STEERING.md`). The two completed P1 superpowers plans
(`2026-06-19-p1-evidence-decision-spine.md`,
`2026-06-20-p1-red-audit-recovery.md`) received historical banners in place.
`docs/CONVERSATIONAL_RUNTIME.md` is resolved as an active runtime-contract doc,
not a stale one. `docs/QA_CONVERSATIONAL_TRANSCRIPTS.md` is likewise resolved as
the active manual browser-QA script (its "legacy orchestrator path?" flag was
unfounded) and refreshed with a status banner plus Spanish and language-mismatch
transcripts.

2026-07-08 pass: `docs/specs/private-alpha-next-refine-to-version.md` moved to
`docs/archive/private-alpha-next-refine-to-version.md` after issue #141 / PR
#148 shipped. A one-line pointer stub remains at the original path for existing
roadmap links.

## Inventory

| File | Classification | Rationale | Recommended next action | Notes / possible stale references |
| :--- | :--- | :--- | :--- | :--- |
| `AGENTS.md` | canon | Root level agent instructions and canon pointer. | None | Current |
| `docs/DOCUMENTATION_AUTHORITY.md` | authority map | Owns document precedence and assignment boundaries. | Start here for source ownership. | Current |
| `docs/specs/argus-minimum-viable-ecosystem-experience.md` | approved experience | Owns the founder-approved ecosystem experience. | Define technical scope before implementation. | Current direction, not a shipped inventory |
| `docs/PRODUCT.md` | canon | Defined as canon product source of truth. | None | Current |
| `docs/ARCHITECTURE.md` | canon | Defined as canon architecture source of truth. | None | Current |
| `docs/API_CONTRACT.md` | canon | Defined as canon API contract source of truth. | None | Current |
| `docs/DATA_MODEL.md` | canon | Defined as canon data model source of truth. | None | Current |
| `.agent/designs/argus/DESIGN.md` | canon | Explicitly listed as canon design source of truth. | None | Current |
| `docs/specs/argus-answers-that-stay-true-roadmap.md` | historical compatibility pointer | Links the archived answers board and carried-work history. | Follow documentation authority for current ownership; do not dispatch from the archived queue. | Archived 2026-09-26 |
| `docs/archive/2026-09-17-argus-grounded-finance-roadmap.md` | archived | Grounded-finance board; every item shipped to production `a9286b21` on 2026-09-17. Pointer stub remains in `docs/specs/`. | Historical reference only; open ends moved to the active board. | Archived 2026-09-18 |
| `docs/archive/2026-09-05-argus-active-roadmap.md` | archived | Board before grounded finance; landed work remains valid history. Pointer stub remains in `docs/specs/`. | Historical reference only. | Archived 2026-09-18 |
| `docs/archive/private-alpha-interim-roadmap.md` | archived | Interim pivot slate; completed with the 2026-08-05 production promotion. | Historical reference only. | Archived 2026-08-06 |
| `docs/specs/private-alpha-next-roadmap.md` | superseded reference | P2 history, execution-realism contract, and slice provenance. | Read for provenance; do not take work from it. | Superseded 2026-08-06 |
| `docs/specs/private-alpha-next-decision-memo.md` | historical compatibility pointer | Links archived strategic and technical rationale. | Read relevant historical contracts for a named assignment; approved experience belongs to the MVEE. | Archived 2026-09-26 |
| `docs/specs/private-alpha-ci-cd-sota.md` | release-discipline reference | Completed CI/CD SOTA plan; still owns canary, manifest, Render validation, and deployment discipline. | Use for release gates, not product sequencing. | Completed/reference |
| `docs/PRIVATE_LAUNCH_RUNBOOK.md` | release-discipline reference | Operational gate for controlled private-alpha validation and launch steps. | Keep as operator runbook. | Current release ops |
| `docs/release-manifests/TEMPLATE.md` | release-discipline reference | Template for candidate SHA, env fingerprint, evidence, approver, and rollback target. | Use when producing a candidate manifest. | Current release ops |
| `docs/specs/private-alpha-next-integration.md` | active staging/process context | Records integration-lane branch mechanics, quarantine rules, closed work, Jules boundaries, and P0 reintegration process. | Keep as staging/process context. | Current context, not command doc |
| `docs/archive/private-alpha-conversation-trust.md` | archived historical evidence / completed checkpoint | Marked as merged and deployed checkpoint; useful for conversation-trust design context but not current execution scope. | Keep archived for branch archaeology. | Completed |
| `docs/archive/private-alpha-status-action-parity-audit.md` | archived historical evidence / implemented slice | Implemented and locally verified; useful as artifact lifecycle evidence but not current execution scope. | Keep archived for branch archaeology. | Completed |
| `docs/archive/private-alpha-next-refine-to-version.md` | archived historical evidence / implemented slice | Shipped in issue #141 / PR #148; A1b/A2 sequencing now belongs to the active roadmap. | Keep archived for branch archaeology. | Moved 2026-07-08; pointer stub remains in `docs/specs/` |
| `docs/archive/2026-07-19-adaptive-result-chart-range-design.md` | archived historical evidence / implemented slice | Issue #250 / PR #264 shipped and passed founder-visible browser QA. | Keep archived; pointer stub remains at the former spec path. | Moved 2026-07-23 |
| `docs/archive/2026-07-19-adaptive-result-chart-range-implementation.md` | archived historical evidence / completed plan | Issue #250 / PR #264 completed the plan. | Keep archived; pointer stub remains at the former plan path. | Moved 2026-07-23 |
| `docs/archive/2026-07-22-capability-truth-executable-boundary-design.md` | archived historical evidence / implemented slice | Issue #241 / PR #266 shipped the executable capability boundary and passed founder-visible browser QA. | Keep archived; pointer stub remains at the former spec path. | Moved 2026-07-23 |
| `docs/archive/private-alpha-interim-issue-roadmap-2026-07-21.md` | archived superseded planning | The issue/wave dependency plan was retired when founder outcomes became the active sequencing unit. | Keep for issue-link compatibility and planning archaeology. | Active roadmap owns current selection |
| `docs/archive/private-alpha-readiness-orchestration.md` | archived branch-specific context | Coordination note for `codex/private-alpha-readiness-clean`; not the current Private Alpha Next roadmap. | Keep archived for readiness-lane archaeology. | Readiness lane |
| `docs/archive/private-alpha-controlled-readiness-panel.md` | archived branch/lane-specific context | Controlled-alpha readiness panel for readiness decisions; useful evidence but not the active roadmap. | Keep archived for readiness-lane archaeology. | Readiness lane |
| `docs/archive/private-alpha-performance-readiness-audit.md` | archived branch/lane-specific context | Supporting performance addendum for the controlled readiness slice. | Keep archived for readiness-lane archaeology. | Readiness lane |
| `docs/specs/evidence-aware-idea-loop.md` | source thesis / strategic background | Source product thesis for the durable idea loop. It directly informed `docs/specs/private-alpha-next-decision-memo.md`, now preserved as archived rationale. | Keep in `docs/specs/` with a clear source-thesis banner; do not treat as the active sequencing doc. | Provenance for the archived decision memo |
| `docs/archive/research-lab-thesis.md` | archived historical evidence | Earlier Research Lab thesis draft. It is retained for context and refined by `docs/specs/evidence-aware-idea-loop.md`, which then informed the decision memo. | Keep archived for product archaeology. | Superseded by evidence-aware source thesis and current decision memo |
| `docs/archive/private-alpha-backtest-execution-capacity.md` | archived historical evidence | Draft from 2026-06-05; later release/runtime docs own active deployment discipline and architecture truth. | Keep archived for runtime-capacity archaeology. | Historical capacity draft |
| `docs/archive/agent-architecture.md` | archived historical evidence | Proposed architecture from 2026-04-29. Predates the conversation trust milestone. | Keep archived for architecture archaeology. | Stale date |
| `docs/CONVERSATIONAL_RUNTIME.md` | active runtime-contract doc | Owns the conversational runtime contract (artifact spine, action events, typed-prose composition). Kept current through #178; complements, not superseded by, `docs/ARCHITECTURE.md`. | Keep active. Resolved 2026-07-07. |  |
| `docs/archive/LAUNCH_GATE_FINAL_CLOSURE_PLAN.md` | archived/superseded | Explicitly marked "> Historical plan. This document records an earlier launch-closure checklist and should not be treated as the current milestone source of truth." | Archived under `docs/archive/`; use `docs/archive/private-alpha-conversation-trust.md` for the completed trust checkpoint and `docs/specs/private-alpha-ci-cd-sota.md` for release-gate discipline. | Explicitly stale. |
| `docs/archive/ARGUS_SYSTEM_STEERING.md` | historical evidence | "Pre-private-launch steering reference... planning reference, not an implementation ticket" from 2026-05-19. | Moved to `docs/archive/` (2026-07-07); carries its historical banner. |  |
| `docs/QA_CONVERSATIONAL_TRANSCRIPTS.md` | active QA process | Canonical manual browser-QA script for the conversational runtime; matches current runtime contracts (start command, action chips, result actions, provider/metric rules). The "legacy orchestrator path?" worry was unfounded. | Keep active. Resolved + refreshed 2026-07-07 (status banner + Spanish/language-mismatch transcripts). |  |
| `docs/archive/PRODUCTION_READINESS_AUDIT.md` | historical evidence | Audit for `codex/production-readiness-gap-implementation` from 2026-05-05. | Moved to `docs/archive/` (2026-07-07); carries its historical banner. |  |
| `.agent/ownership/README.md` | unclear/needs owner decision | Active ownership rules. | Clarify if ownership docs are "canon". |  |
| `docs/maintenance/dead-code-candidates.md` | maintenance | Inventory of dead code candidates. | Keep updated as codebase evolves. | |
| `docs/maintenance/docs-classification-inventory.md` | maintenance | This file. | Keep updated as docs evolve. | |
| `docs/maintenance/i18n-key-audit.md` | maintenance | Inventory of i18n keys. | Keep updated as keys are added/removed. | |
| `docs/maintenance/language-enablement-checklist.md` | maintenance | Checklist for language enablement. | Track progress of language support. | |
| `docs/maintenance/large-file-modularity-inventory.md` | maintenance | Inventory of large files for modularity. | Keep updated as refactoring occurs. | |
| `docs/maintenance/spanish-readiness-inventory.md` | maintenance | Inventory of Spanish readiness. | Keep updated as translations progress. | |


## Prior Banner Pass Summary

This records a previous docs-janitor pass. It is not the active source order;
use the inventory table above for current classification.

### Files that already carry or were recommended for historical treatment:
- `docs/ARGUS_SYSTEM_STEERING.md` -> AGENTS.md, docs/specs/private-alpha-next-integration.md
- `docs/PRODUCTION_READINESS_AUDIT.md` -> docs/archive/private-alpha-conversation-trust.md
- `docs/archive/agent-architecture.md` -> docs/ARCHITECTURE.md
- 16 more files, since removed in the 2026-10-18 legacy agent-docs cleanup

### Files that already carry or were recommended for superseded treatment:
- `docs/archive/LAUNCH_GATE_FINAL_CLOSURE_PLAN.md` -> docs/archive/private-alpha-conversation-trust.md

### Files intentionally skipped (unclear/needs owner decision):
- `docs/CONVERSATIONAL_RUNTIME.md`
- `docs/QA_CONVERSATIONAL_TRANSCRIPTS.md`
- `.agent/ownership/README.md`
- 12 more files, since removed in the 2026-10-18 legacy agent-docs cleanup

## Out of scope observations

*   The vendored agent skills were excluded from this inventory and were later removed in the legacy agent-docs cleanup.
*   `docs/archive/research-lab-thesis.md` already carries its own historical/refined status banner from the active evidence-aware idea-loop spec and did not need a second Jules banner pass.
