# Facturación checkpoint handoff: review draft

**HOLD: prepared for the user's final review. Do not send to the orchestrator until
explicit checkpoint clearance.** This document does not assign backend work,
authorize a merge, deploy, migration or activation, or certify hosted readiness.

Date: 26 October 2026.
Branch: `codex/frontend-design-after-home-20261024`.
Exact reviewed code SHA: `22b12a6b74bbc66c5bf005b2f63318554861235a`.
The later docs-only commit, if any, does not change that executable baseline.
Preview: `http://127.0.0.1:4387/biz?invoicePreview=seeded&view=invoicing`.

## Read first

- [Current design and behavior guide](../reports/invoicing-preview-20261026.md):
  complete interaction inventory, including hidden controls, scopes and empty states.
- [Shared design patterns](../../.agent/designs/cuadrao-business-app/DESIGN.md).
- `web/components/business-app/invoicing/`: current UI and local models.

Keep the frontend's approved behavior while replacing local adapters with durable
contracts. Engineering owns route and storage choices. Return only unresolved
product decisions with a recommendation; do not require the user to referee API names.

## 1. Implemented versus connected

| Capability | Current proof | Remaining owner/dependency |
| --- | --- | --- |
| Invoice workspace, stage tabs, customer/schedule views | Interactive frontend with synthetic fixtures | Frontend connects authoritative query/state; backend supplies it |
| Business identity | Existing selected-Business context | Confirm authorization and legal snapshot source for issuing |
| Four-step editor and partial draft save | Local state, exact preview calculations, validation | Backend draft/customer persistence, versioning, validation |
| Search, filters, counts, metrics and numbered pages | Local arrays, sorting and slicing | Backend shared query/count/aggregation and data-change signal |
| Fiscal issuance and correction state machines | Local reducers and explicit outcome fixtures | Fiscal operation linkage, reconciliation, provider outcomes |
| Official files and verification | Unavailable slots | Secure canonical XML/PDF and verification retrieval |
| Email preparation/customer HTML | Local prepared data and browser print | One delivery owner, generated files, real outcomes and retries |
| Partial payments | Local allocation model | Durable allocations, evidence, authorization, concurrency |
| Customers and archiving | Local IDs, snapshots, archive/restore | Business-scoped persistence and archive policy |
| Schedules | Local template/settings and planned dates | Worker, occurrence identity, timezone, readiness and run history |
| Setup-card navigation | Working links into existing flows | Derived durable completion; no checkbox-as-truth |
| Activity | Concise local facts | Real events, actor/time and secure linked evidence |
| Exports, selection, saved views, URL restoration | Not implemented for this surface | Separate frontend/API scope; do not advertise as ready |

No invoice/customer/payment/schedule fetch is connected in this component directory.
No production fiscal capability follows from the mock UI being enabled locally.

## 2. Existing backend footholds, not completed wiring

This checkout contains the following fiscal groundwork:

| Existing route | Existing request boundary | Integration caution |
| --- | --- | --- |
| GET/PATCH `/business/fiscal-profile` | Fiscal profile contract | Not yet the UI's complete readiness/completion source |
| POST `/business/fiscal-operations` | `FiscalPrepare.case_id` | Case-based preparation, not generic customer/invoice CRUD |
| GET `/business/fiscal-operations/{operation_id}` | Operation ID | UI must map a stable invoice to its operation |
| POST `/business/fiscal-operations/{operation_id}/submit` | `FiscalSubmit.payload_digest` | Preserve validated digest and idempotent operation lifecycle |
| GET `/business/fiscal-operations/{operation_id}/artifacts/{kind}` | XML/PDF kind | Authorization and availability remain required |
| POST `/webhooks/fiscal-sandbox/emission` | Authenticated sandbox observation | Sandbox evidence is not production acceptance |

Sources: `src/argus/api/routers/business_fiscal.py`,
`business_fiscal_operations.py`, and the fiscal-sandbox domain contracts/services.
Existing generic drafts/cases must be reconciled with the invoice domain before
reuse; a similar endpoint name is not a field contract. Review the current integration
branch at pickup, since this inventory is tied to the code baseline above.

Do not introduce competing customer, invoice or payment stores. Reconcile these
requirements with the existing Business customer/invoice/allocation milestones.
Update API_CONTRACT, OpenAPI and DATA_MODEL together when that implementation lands.

## 3. Required domain contracts

These are required meanings, not newly invented API field names.

### Identity, drafts and concurrent work

- Every invoice, customer, schedule, allocation, correction and asset has a stable
  identity and Business ownership. Check authorization on every operation, not just
  when opening the list. URLs and fixture IDs grant no access.
- A saved draft retains partial items, customer input, dates, currency, notes,
  instructions and email preparation across reloads and sessions. Incomplete drafts
  can save; issuance cannot bypass validation. Do not create invalid customers as a
  side effect of partial draft saving.
- Preserve issuer/customer snapshots on issued documents. Editing a contact must not
  rewrite the historical document. Define draft refresh behavior explicitly.
- Version checks detect stale concurrent edits and preserve the user's attempted work.
  Idempotency prevents duplicate retries. These solve different problems and both
  are needed. Do not silently overwrite another user's edit.
- Archive hides a customer from new selection without deleting invoice evidence.
  Define the effect on active schedules; require an explicit safe resolution.

### Money and document generation

- Original currency is explicit and independent of country. The current preview uses
  DOP/USD/EUR; expansion of the supported currency catalogue is a separate decision.
- Quantities, unit prices, discounts, tax bases, rounding and totals require exact
  arithmetic. Validate the line-discount-before-tax preview model against the actual
  fiscal document contract before issuing. Preview math is not fiscal approval.
- Invoice document type is chosen per invoice, with an explicit schedule default if
  needed. It is not customer metadata. E31/E32 are the first visible choices; other
  document types should not appear without their required fields and rules.
- Validate identification, issuer readiness, certificate, numbering and document
  eligibility server-side. Formatting an RNC/CED is not registry or ownership proof.
- Canonical signed XML, official PDF, verification details and their availability
  belong to the invoice. Secure retrieval must preserve Business permissions.
  Browser print and the email mock attachment are not substitutes.

### Independent lifecycle states

Keep issuance, fiscal outcome, delivery, settlement and corrections independent.
Submitted is not accepted; issued is not emailed; emailed is not paid. Model
processing, accepted, accepted-with-observations, rejected, failed and uncertain
outcomes with a useful next action.

Issuance retries reuse the operation identity. On a timeout or uncertain response,
reconcile before allowing another submission. UI refreshes, double clicks and delayed
callbacks cannot create a second fiscal document. Preserve the validated payload
relationship rather than issuing a silently changed draft.

### Delivery

Choose exactly one owner for email delivery. Store To, up to five Cc recipients and
the separate 500-character message with the draft. Sending requires actual assets
and a confirmed outcome; preparation is not sending. Resend the existing invoice,
never reissue it. Define retry identity, failure recovery and delivery timestamps.
Any future public recipient link needs explicit expiry/revocation and access rules;
it must not expose internal notes or the wider Business.

### Payments and corrections

- Basic partial payments are in the pilot. Persist amount, currency, date, method,
  reference/evidence and allocation to the original invoice. Allocation retries must
  be idempotent and concurrent allocations must not overdraw the balance.
- Payment recording is not collection processing. An invoice and its payment must
  not count as two sales. Do not infer paid from fiscal acceptance or email delivery.
- Preserve originals and link credit/debit notes with reason, exact amount, attempts
  and provider outcomes. Full cancellation, partial credit and debit adjustment are
  distinct commands. The initial UI paths are E34 and E33 respectively.
- Submission remains pending. Failed/uncertain correction must retain the original
  state and support safe recovery. Only a confirmed full cancellation enters Anuladas.
  A partial credit equal to the invoice total is not automatically cancellation.
- Full cancellation uses remaining creditable value, not merely unpaid balance.
  Keep payments. If a credit makes collected value exceed net billed value, represent
  customer credit explicitly; do not fabricate a refund or negative pending payment.
- Resolve payment/correction races atomically. Ignore duplicate/stale outcome events.

## 4. Query, totals and pagination contract

One authorized query definition must drive rows, matching count, financial totals
and eventual filtered exports: Business, date basis, period, stage, search, currency,
overdue condition and supported sort. Pagination limits rows, not counts or totals.

Search currently covers customer name, invoice reference and invoice notes locally.
Backend search must cover the full authorized result set, not just a loaded page.
Do not silently claim attachment-content search. The broader Records search contract
includes document identifiers and remains a separate connected requirement.

Todo means all available dates, including records older than one year. Keep direct
numbered-page navigation and page sizes 25/50/100; do not fetch every record at once.
Evaluate indexed offset queries with a deterministic sort ending in a unique ID,
including ties and nulls. Do not replace approved navigation with cursor-only access
without explaining the user-visible change.

Search/filter/sort/page-size changes reset page 1. Density does not. Future URL
restoration must preserve Business/query/page and a stable row return anchor. Named
views, if later added, open page 1 rather than saving page 17.

A deterministic order does not prevent changing-data drift. Identify a reliable
version/invalidation signal and design refresh/recovery against it. New rows must
not silently shift the page someone is reading. A deleted final row or invalid page
needs recovery; do not keep a database transaction open during browsing.

### Summary and tab scope

Stage counts are currently Business + period totals; table search/currency further
narrow the selected tab. Keep that difference explicit in implementation and QA.
Cards appear only in Todas, below controls, and summarize all matching eligible
issued invoices. Currency amounts remain separate. There is no duplicate currency
selector or card click filter. The overflow dossier only reveals more currencies.

Facturado is net of confirmed debit/credit adjustments. Cobrado is allocated cash
recording. Por cobrar is outstanding balance. Do not force their equation by hiding
customer credits. Table Total currently represents the original invoice amount;
resolve how adjustments are disclosed so its difference from Facturado is intelligible.

Draft and uncertain issuance exclusion must be explained where material. The local
model counts exclusions but the card UI does not render that explanation yet.
Unknown/unavailable values remain unknown. Zero is valid only for a known result,
including a confirmed empty selected-currency result. Loading and failure need their
own stable layouts; they are not zero results.

Exports are not implemented here. When introduced, distinguish all matching results
from explicit selected IDs. Period-only export is insufficient for arbitrary filters.
Capture scope and generation time; decide request-time versus processing-time data
and use a consistent captured/read result. Reusing filters alone does not reproduce
an earlier screen after edits. No large frozen-session system is implied.

## 5. Setup progress and recurring drafts

The three cold-start cards navigate to existing Business details, customer creation
and invoice creation. Their completion must derive automatically from valid saved
facts for that Business: saved required Business details, an eligible saved customer,
and a saved first draft. Opening a card does not complete it. Unknown/loading is not
complete. Existing validated data should count without making the user repeat it.

Progress must survive reload, sessions and device changes, and stay isolated by
Business. It is derived progress, not a separate manually saved checklist and not
implicit autosave for every underlying form. The first draft replaces the first-use
view; this does not prove fiscal readiness or prevent later draft creation while
setup is incomplete. Actual issuance still checks readiness at submission.

Programadas defaults to generating drafts. Persist an independent template copy,
customer ID, cadence, start/anchor date, timezone, mode and paused state. Define
month-end/leap-year behavior and missed-run handling. A planned date is not a run.
Each occurrence needs a unique idempotent identity and a real outcome/history.

Automatic issuance requires explicit opt-in and verified setup, permissions and
certificate at every run. Changes in eligibility, archived customers or revoked
access must produce a recoverable stopped/blocked state, not silent issuing. Delivery
is a separately governed consequence. Schedules do not charge a payment method.

## 6. Hosted acceptance before declaring the flow complete

All rows below are **pending hosted proof**, even where local model tests exist.
Backend owns durable truth; frontend owns faithful controls, copy and recovery;
integration QA proves the actual connected result at the authorized deployed SHA.

| Check | Required result |
| --- | --- |
| Partial draft save/reload | Same draft ID and unfinished fields return; no invalid customer created |
| Two editors | Stale save is detected; attempted changes preserved; no silent overwrite |
| Duplicate save/issue | Repeated operation creates one logical result |
| Uncertain issuance | Reconciliation prevents duplicate issuance and presents a safe next action |
| Fiscal outcomes | Accepted/observed/rejected/failed/pending are distinct from delivery/payment |
| Invalid fiscal data | Server blocks issue without discarding the draft or inventing verified identity |
| Files | Authorized user retrieves the correct official XML/PDF; revoked/wrong Business denied |
| Email | Preparation sends nothing; actual send has one owner; resend uses same invoice |
| Partial payments | 40 then 60 against 100 leaves 60 then 0; duplicate allocation does not count twice |
| Credits/debits | Pending/failed do not prematurely alter outcome; confirmed adjustment applies once |
| Full cancellation | Original preserved; only confirmed cancellation enters Anuladas |
| Credit after payment | Customer credit/refund distinction remains visible and mathematically correct |
| Customer archive | History/snapshots preserved; new picker excludes archived customer; schedules handled |
| Setup completion | Saved facts drive checks across reload/Business switch; visits alone do not |
| Recurring drafts | Month-end/leap-year/timezone run creates one draft; pause prevents execution |
| Automatic issuance | Explicit opt-in plus current readiness; revoked readiness blocks the run |
| Query consistency | Count, totals and rows agree across filters and multiple pages; currencies separate |
| All-time | Records older than a year included without loading every record |
| Pagination | Direct-page reload, equal sort values, last-row deletion and concurrent changes recover |
| Empty/error/loading | Known zero, no results, unknown values and failure never masquerade as each other |
| Future exports | Cross-page filtered result scope and generation time match the stated contract |
| Recipient/print output | No editing markers or internal data; correct branding, amounts and legal identity |
| Activity | Real actor, timestamp and linked record; no UI-created audit history |

## 7. Remaining decisions and ownership

These should be resolved during integration without reopening the visual layout:

1. Backend/integration: reconcile existing fiscal-case operations with the invoice
   model and readiness profile; supply the actual field/endpoint mapping.
2. Product + design: make summary exclusions and original-versus-adjusted amounts
   understandable. Recommendation: quiet contextual information and correction
   details, not another dashboard card or false zero.
3. Backend/product: choose delivery ownership and schedule timezone/missed-run policy.
   Recommendation: one delivery owner and one explicit Business scheduling timezone.
4. Frontend: request loading/error recovery, URL/Back restoration, broader navigation
   unsaved guards and actual asset/download states. Saved views, configurable columns
   and exports need their own scoped work; they are not completed here.
5. QA/release: hosted checks, safe migration/flag rollout and exact deployed SHA proof
   remain distinct from design approval and local test success.

## 8. Evidence and dispatch hold

The behavior guide records prior local browser evidence and its limits. This handoff
was reviewed against the exact code baseline above, without backend changes.
Fresh local verification against this code baseline: **60 tests passed, 0 failed**
across seven files in 2.61 seconds:

```sh
cd web
bun test __tests__/invoicing-preview.test.ts __tests__/invoicing-panel.dom.test.tsx __tests__/customer-preview.test.ts __tests__/customer-preview.dom.test.tsx __tests__/schedule-preview.test.ts __tests__/invoice-results-summary.test.ts __tests__/business-date-picker.dom.test.tsx
```

These are local model/DOM checks, not provider or hosted calls. Documentation link
checks and `git diff --check` also pass. No fresh full-browser sweep, full-build pass or hosted acceptance is
claimed by this document.

At clearance, attach this handoff, the behavior guide, exact checkpoint SHA and local
proof to the orchestrator. Ask it to acknowledge the backend requirements, add them
to its plan and identify unresolved dependencies. **Do not dispatch now.** No
acknowledgment has been requested or claimed for this draft.
