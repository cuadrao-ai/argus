# Cuadrao: product and engineering handoff

**Snapshot: 27 October 2026, 14:36 UTC. Local draft; publication awaits Lucas.**
Repository checked at `da8dfc7ebdaca5dc0b81b298b45d3fec1bc6c283` on
`codex/private-alpha-next`. This is a concise Business continuation checkpoint,
linked from the execution board. It supplements the older dated status there;
it does not replace API/data/design contracts, reopen Consumer work, assign a
new implementation lane, or certify launch readiness.

## Start here with any AI provider

1. Read [AGENTS.md](../AGENTS.md), the [authority map](DOCUMENTATION_AUTHORITY.md)
   and the [execution board](specs/argus-execution-board.md). Read dates before
   treating a historical hold or completion claim as current. This checkpoint
   carries Lucas's 27 October direction; older handoffs remain dated evidence.
2. Read [PRODUCT](PRODUCT.md), the [MVEE](specs/argus-minimum-viable-ecosystem-experience.md)
   and the [connected Business flow](specs/cuadrao-business-connected-flow-spec.md).
   Preserve the existing product; omission here does not retire approved scope.
3. Follow the real [Business app DESIGN.md](../.agent/designs/cuadrao-business-app/DESIGN.md),
   [native tokens](../.agent/designs/cuadrao/DESIGN.md) and
   [marketing DESIGN.md](../.agent/designs/cuadrao-business/DESIGN.md).
   Reuse approved components, tokens and interactions, not lookalike rewrites.
4. Read [ARCHITECTURE](ARCHITECTURE.md), [API_CONTRACT](API_CONTRACT.md),
   [OpenAPI](api/openapi.yaml), [DATA_MODEL](DATA_MODEL.md) and the relevant
   [core flow](CORE_FLOWS.md). Backend state is authoritative. Never invent
   progress, financial totals, paid state or available actions in the client.
5. For the assigned surface, start from the
   [invoice handoff](handoffs/invoicing-design-checkpoint-20261026.md),
   [invoice behavior inventory](reports/invoicing-preview-20261026.md),
   [Reception handoff](handoffs/reception-design-checkpoint-20261026.md) or
   [Home handoff](handoffs/home-shell-working.md). Their preview baselines are
   design evidence; the status below accounts for subsequent integration.
6. Fetch integration once, record its SHA, inspect the relevant PR and coordinate
   with its current owner before editing. Use an isolated checkout, one job per
   PR, and the existing review/release gates. Never overwrite newer shared files
   with an old design checkout. Docs-only work needs no setup or environment write.

## Product direction and surface boundaries

Cuadrao is Spanish-first finance software for the Dominican Republic. Business
connects **customer → invoice → payment → remaining balance** with **incoming
document → extraction/review → owner approval → connected records/export**.
Reliable evidence and one consistent financial truth matter more than a polished
mock. Consumer and household remain part of the wider approved ecosystem; this
Business checkpoint neither restarts their lanes nor claims current phone proof.

| Surface | Settled job |
| --- | --- |
| Home / Inicio | What needs attention; still needs polish and approved visual parity. |
| Registros | Financial records, original evidence, review/approval, all-match totals, saved views and export. |
| Facturación | Draft creation/editing, invoice detail, customer-facing invoice, outgoing delivery, collection and recurring billing. |
| Bandeja / Recepción | What arrived, channel/sender, processing, exceptions and destination. Inbound belongs here. |
| Activity | Who changed what and when; shared audit history is not inbox organization. |
| Settings | Businesses, team, identity, intake and provider configuration. |

Carry these settled constraints into implementation:

- One query drives table rows, count, full-result totals and export. Keep currencies
  separate and invoice/payment effects counted once. Review records cannot look
  like finalized money. Saved views remember approved filters/columns and open on
  page 1. Use stable ordering, numbered 25/50/100 pagination and visible refresh.
- Registros cards are automatic; configurable metric widget preferences are retired.
- Archive changes inbox visibility only. Preserve originals, linked drafts/records,
  financial state and unresolved attention. Archive is shared and permissioned;
  seen/unseen is personal. Bulk changes need per-item results and safe failed-only retry.
- Appending supporting evidence must not extract again, create another expense or
  alter payment state. Matching evidence to an existing record is distinct from
  bank-payment allocation. Never classify every greeting as an expense.
- Text-only messaging notes are desired future intake, distinct from current notes
  attached to Registros records. The older receipts-only implementation is not proof
  of standalone note support or permission to enable it.

## What is accomplished, and what the evidence actually proves

**Merged** means code is on integration. **Deployed** means a named staging release
contains it. **Hosted-proven** applies only to the exercised journey. **Preview-only**
means synthetic/local interaction. **Missing** means an identified implementation
gap; **unknown** means evidence has not established the result.

| Capability | State and limits at this snapshot |
| --- | --- |
| Business identity, workspace and access | Persistence/roles in #1385/#1386 and client wiring [#1393](https://github.com/lagarcess/argus/pull/1393) merged and included in the staging release below. Normal QA owner entry was hosted-proven; all team/invitation variants were not rehearsed by that release. |
| Registros reporting and annotations | [#1388](https://github.com/lagarcess/argus/pull/1388)/[#1389](https://github.com/lagarcess/argus/pull/1389) merged and deployed. Hosted read, retained evidence and current-note save/reload/replay passed. Full query/export/permission acceptance is not established by that small smoke. |
| Invoice drafts, customers and fiscal linkage | [#1392](https://github.com/lagarcess/argus/pull/1392)/[#1394](https://github.com/lagarcess/argus/pull/1394) merged and deployed. Saved revisions and existing fiscal-operation wiring exist; this release rehearsal issued no invoice and proved no collection or customer delivery. |
| Fiscal operation journal | [#1381](https://github.com/lagarcess/argus/pull/1381) merged and deployed. Bounded sandbox lifecycle exists, not unrestricted product issuance or production activation. |
| New Bandeja design | [#1395](https://github.com/lagarcess/argus/pull/1395), merge `af5d14a20`, is included in staging. New organization UI is development/mock gated: archive/seen/undo are in-memory and queries describe loaded arrivals. Hosted Bandeja visibility does not prove those durable semantics. See the Reception handoff's backend checkpoint. |
| Messaging receipt intake | Earlier synthetic PDF hosted run reached the QA Business with one extraction/draft, exact original and both replies, per coordinator handback. Account-access change resolved the permission error with the same token/media. Duplicate resend was not tested in that run. Reading is currently off. |
| Standalone text-only intake notes | Missing. Existing Registros current notes are implemented and were hosted-proven; they are a different feature. |
| Marketing sign-in | Reviewed content `247cec6ed` lacked wiring. Repair [#1396](https://github.com/lagarcess/argus/pull/1396) merged at `da8dfc7eb` with tested staging-host navigation. PR handback awaits post-merge gates and a pinned deployment. Deployed repair and Lucas's visible result remain unknown here. No new Marketing migration was needed. |
| Invoice empty-state parity | [#1397](https://github.com/lagarcess/argus/pull/1397), head `15ad10172`, is open with reported exact-head review/visual evidence and conditional merge approval. Approved illustrations/create/reset actions are not yet established in the deployed app. No repair deployment is approved by that handback. |
| Home and deployed presentation | Home month-close/open-items fixture routes previously returned 404. #1397 reports local fixture proof, explicitly outside its product diff. Lucas also reports staging visual regressions. The designer handed the populated-table regression to the orchestrator, which acknowledged ownership of a separate authorized restoration using approved styling; completion is unverified, not a missing product decision. Full approved presentation remains unresolved. Backend tests do not prove visual parity. |
| Payments, sending, schedules and corrections | Invoice contracts explicitly create no payment/allocation, email-send or schedule record. Partial/full collection, delivery, recurrence and correction journeys remain scoped work; preview success or provider qualification does not implement them. |

### Staging release evidence

At **13:53:57 UTC on 27 October**, the sole release executor reported API and web
live at `af5d14a20926248da59e89d7b1194fd58c5fe3ac`, health HTTP 200, maintenance
off, schema/RLS checks passed and existing data counts preserved. Six migrations
were applied and verified through `20261027024830`:

| Version | Purpose |
| --- | --- |
| `20261024095154` | Fiscal sandbox operations |
| `20261025182039` | Membership roles |
| `20261025223500` | Workspace persistence |
| `20261026013716` | Saved report views |
| `20261026095000` | Registros preferences/current notes |
| `20261027024830` | Invoice editor |

Normal QA owner login, Bandeja, Registros, retained messaging receipt/original and
durable current-note save/reload/replay passed. Source download bytes/hash were
verified, but the embedded PDF canvas was blank in headless capture. A read-only
guard blocked a name-prompt seen-state POST. These limits remain evidence limits.

Source is **local-only**, inspected for this draft:
`migration-preflight/final-release-handback.json` in the coordinator's
`2026-10-27/task` workspace. The useful findings are summarized above so another
provider does not need that machine. Raw payloads, account identifiers, login
information, backups and private screenshots are deliberately not copied here.
Earlier intake and fiscal qualification findings below are coordinator-reported
handoff evidence, not independently rerun in this docs task.

### Fiscal and intake boundaries that must survive the handoff

Existing sandbox qualification succeeded for E31/E32 with XML/PDF evidence; later
debit and partial/remaining/full credit stories also passed qualification. Earlier
artifact-repair edge cases were not a blanket sandbox failure. Qualification is
not implemented application support for those flows.

Use **saved validated invoice revision → existing idempotent fiscal-operation
journal → status reconciliation → authenticated XML/PDF**. Keep issuance, fiscal
acceptance, delivery and payment separate. Reconcile an uncertain response before
any further contact; never issue again to repair a missing PDF.

The [current invoice contract](API_CONTRACT.md#business-customers-and-invoice-editor)
and [payload validation](../src/argus/domain/business/invoicing/preparation.py)
require DOP, DO issuer matching the configured identity, reserved E31/E32 number,
explicit goods/services and taxable/exempt classification, 18/16/0 percent tax,
tax-excluded price, cash/credit and income type. USD/EUR and tax-included drafts
can save but cannot prepare for issue. Preserve the documented length and rounding
refusals; do not silently truncate or infer missing fiscal facts.

`CUADRAO_BUSINESS_INVOICING_ENABLED`, `CUADRAO_FISCAL_SANDBOX_ENABLED` and
`CUADRAO_FISCAL_SANDBOX_CONTACT_ENABLED` default off. The
[sandbox decision](decisions/2026-10-24-fiscal-sandbox.md) and
[configuration](../src/argus/domain/business/fiscal_sandbox/config.py) own the
protected manifest and activation boundary. Code defaults are not a readback of
hosted flag values. This task neither activates providers nor changes credentials.

The prior messaging permission failure is resolved; do not reopen a blanket
provider-support blocker. The minimum necessary grant is still unestablished;
the broader grant was temporarily retained through pilot verification. Keep live
reading off unless separately authorized. Enabling fresh intake is distinct from
showing the retained receipt and requires its own scoped proof.

## Prioritized continuation and acceptance

All approved scope remains tracked in the linked contracts/handoffs. This ordering
does not silently shrink it. Roles below are responsibility boundaries, not fresh
dispatches; confirm the active person and file ownership with the orchestrator.

| Priority / owner | Next outcome and concrete acceptance |
| --- | --- |
| 1. Orchestrator + design lane + release owner | One cohesive synthetic QA owner Business demo. Resolve the known visual regressions against approved checkpoints; verify normal entry, attention → arrival → original → record/current note and honest invoice states at the exact deployed SHA. Prove approved artwork/actions at desktop/phone sizes. Keep unsupported flows visibly unavailable. Fresh intake, approvals or issuance require separate authorization. |
| 2. Existing Business backend/client owners | Wire and rehearse every approved checkpoint. Show reload/second-session persistence, live permissions, stale-edit handling and idempotent retry; one query across rows/count/totals/export, separate currencies, no duplicated financial effects, saved-view page reset and stable pagination. Preserve the invoice design baseline `22b12a6b7` and checkpoint `c9951c58d` through the linked handoff, rather than restoring stale shared files. |
| 2. Reception backend/client owners, coordinated centrally | Implement the handoff's durable shared archive and personal seen contracts. Prove teammate archive visibility, personal isolation, permission revocation, per-item bulk failures/retries and unchanged original/draft/record/payment state. Archived unresolved items must still contribute to attention. |
| 2. Shared money/allocation owner with bank matcher owner | One allocation milestone for partial/full payments, retry/concurrency and bank-matcher side effects. Prove remaining balance, no over-allocation and no invoice/payment double counting. Reuse the [bank matching contract](contracts/business-bank-matching.md) and [ledger assessment](reports/payment-ledger-reuse-assessment.md); do not create a second paid-state mechanism. |
| 2. Fiscal and delivery owners | Persist correction linkage and preserve originals; keep credits/debits/cancellation separate from refunds. Rehearse uncertain-result recovery and authenticated artifacts. Use one Cuadrao-owned email delivery path through the existing transactional mail service, once; no duplicate provider notifications. Show actual send outcomes/retry identity before calling delivery complete. Recurrence needs durable occurrence identity, readiness and run history. |
| 3. Orchestrator | Multi-Business seeded demo after the cohesive single-Business loop. Demonstrate switching and isolation without widening access or replacing the priority-one acceptance. |
| Deferred. Lucas + repository coordinator | Move repositories into the Cuadrao organization after the demo with Jose. Timing may be later today/tomorrow, otherwise next week; no date is committed. Repository transfer/migration needs a separate explicit assignment. No move is authorized now. |

Owner financial approval remains separate from preparer work. Lucas/the designated
coordinator controls merge and release decisions; the assigned release executor
owns approved staging actions. Marketing has its own release. Do not duplicate
the design lane's repairs, restart closed lanes, delete another lane's source or
evidence, run provider probes, change grants/tokens, or touch production from this
handoff. Production activation, customer sending and live fiscal actions require
their own explicit scope and approval.

Lucas is pausing/archiving the design lane to conserve usage; the orchestrator
continues stabilization and owns the handed-off restoration. This is not an
instruction to delete that lane's checkout or evidence.

**Publication hold:** Lucas requested this documentation stay local until he asks
for it to be posted. No push, PR opening, repository move, merge or deployment is
authorized by this draft. The next owner should obtain that later publication
instruction and refresh the bounded status before posting it.
