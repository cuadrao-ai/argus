# Constitution reconciliation

**Status:** Settled documentation disposition, October 4, 2026. The founder
authorized applying the existing decisions and principles to their canonical
owners. Baseline matches [README](README.md).
**Decision rule:** An explicit founder lock governs conflicting source proposals.
A newer source file is not automatically a newer decision. Preserve source text,
record the difference, and update only the canonical owner after approval.

This table records completed documentation reconciliation. C6 and C9 are resolved
by keeping unselected mechanisms and research outside the adopted principles;
the underlying product choices remain open. No live provider, schema or deployment
is authorized here. The [principles index](PRINCIPLES.md) links to the updated owners.

| ID | Source tension | Governing evidence | Disposition and destination |
| --- | --- | --- | --- |
| C1 | Architecture and Quality §2 allow translated currency views with rate provenance. | [October 4 currency lock](../../specs/argus-decision-log.md#currency) | **Retain lock.** Cuadrao does not convert currencies or show blended totals. Preserve original values. Charts use one currency; cross-currency plan payments record both actual bank amounts. Keep translation text in the originals as superseded input. MVEE owns experience; API/data contracts own implementation. |
| C2 | Architecture and Quality §5 describe an owned backend and direct DGII route; GTM discusses a bridge as a fallback. | [October 4 fiscal route](../../specs/argus-decision-log.md#fiscal-route) | **Retain lock.** A certified partner is the route to live issuance. Owned fiscal tooling is the parallel direction. Own records and adapter boundaries; do not imply a provider is selected or direct issuance is live. Architecture and an assigned business spec own the eventual contracts. |
| C3 | Quality §§10, 16 discuss shared email/notification infrastructure. | [October 2 lane locks](../../specs/argus-decision-log.md#october-2-2026-cuadrao-lane-locks); [native design guide](../../../.agent/designs/cuadrao/DESIGN.md) | **Retain scoped lock.** Consumer Updates uses inbox and opted-in push; keep Por correo removed. Email authentication/recovery remains. Household invitation email is outside the current pass. Business invoice delivery requires its own approved contract. A shared delivery service does not authorize another notification channel. |
| C4 | The quality catalog labels WhatsApp intake NOW/pilot, and global search, voice and several imports LATER. | [Launch decisions](../../specs/argus-decision-log.md#october-4-2026-cuadrao-launch-shape); [consumer tracker](https://github.com/lagarcess/argus/issues/817) | **Retain assigned scope.** These are recommendations for a selected workflow. They do not add a WhatsApp launch gate or demote already approved consumer journeys. The Grok voice provider choice does not prove implementation or settle its launch scope. Gmail remains open; Plaid is kept for the named segments. Scope decisions belong in the MVEE and assigned issues. |
| C5 | The quality guide's shared-platform acceptance spans households and multiple businesses. | [Launch shape](../../specs/argus-decision-log.md#launch-shape); [space-model timing](../../specs/argus-decision-log.md#october-4-2026-cuadrao-launch-shape) | **Retain lock; scope tests by capability.** Public consumer iOS contains personal and household spaces. Business web has its own delivery path; thin business iOS goes only to its testers. Complete the approved space-model work before consumer TestFlight without requiring a full business product. The timing lock does not approve every proposed entity or role matrix. |
| C6 | The architecture and quality guides propose entities, action envelopes, jobs, search and external tool surfaces. | [Authority map](../../DOCUMENTATION_AUTHORITY.md); existing [architecture](../../ARCHITECTURE.md), [API](../../API_CONTRACT.md) and [data model](../../DATA_MODEL.md) | **Resolved as proposals.** Adopt durable boundaries separately from a particular table, framework or queue. The Cuadrao chat contract needs its own scoped decision; this package neither creates another active runtime nor treats the old runtime as the decided future architecture. External tools get no new access from this document. |
| C7 | Retained originals/evidence can be read as indefinite storage. | [Data model](../../DATA_MODEL.md); [account-deletion decisions](../../specs/argus-decision-log.md#october-2-2026-cuadrao-lane-locks) | **Reconcile with existing policy.** Keep sources through processing and recovery within approved retention/deletion rules. Do not promise immutable retention that would defeat account deletion. Any business-specific retention exception needs a scoped legal and product decision. |
| C8 | Broad quality gates and feature lists could turn every future capability into a launch requirement. | [Quality source](QUALITY-SOURCE.md), introductory status and §14; [execution manifest](../../specs/argus-execution-board.md) | **Resolved by capability.** Apply money, authorization and privacy checks wherever relevant. Apply fiscal, connector and business checks only to the assigned capability. Baseline performance and model quality before choosing numeric thresholds. The guide does not create a new release schedule. |
| C9 | Originals contain regulatory dates, signing routes, vendor claims, pricing ideas and technology comparisons. | Each original's source/status notes; [master plan](../../specs/cuadrao-master-plan.md) | **Research or hypothesis.** Preserve attribution and date. Revalidate time-sensitive facts before a legal, procurement or release decision. Do not promote them to timeless principles or claim this upload validates compliance. Commercial prices and unresolved fiscal, payment and POS provider choices remain open; the October 4 AI provider selections remain locked. |

## How changes reach the canon

1. Select a principle and cite its source section and reconciliation ID.
2. Find the existing owner in the authority map. Change that owner; other documents link to it.
3. If the change contradicts a founder lock, show the old rule, proposed rule and practical impact for an explicit decision. Do not infer approval from this upload.
4. For a new technical contract, document the schema, permission boundary and acceptance evidence in its assigned slice before code changes.
5. Link the adopted rule back here and mark the proposal adopted or superseded. Leave the originals untouched.

The canonical documentation pass is recorded in the [principles index](PRINCIPLES.md).
It preserves C1–C5, incorporates the applicable C7–C8 principles, and keeps C6 and
C9 proposals out of current contracts. Business pricing, the fiscal provider,
the full space model, Gmail import and Cuadrao agent architecture remain open.
