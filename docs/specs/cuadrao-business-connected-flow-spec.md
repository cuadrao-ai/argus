# Cuadrao Business — connected invoice-to-accountant flow and first fiscal-engine milestone

**Repository publication, October 7, 2026 (America/Chicago).** Lucas approved this design, the E0 implementation plan and task-by-task independent review. Counsel may publish and land this documentation-only PR when clean. Lucas will coordinate the existing Business agent for implementation. This publication dispatches no implementation and authorizes no hosted change. See the [decision record](argus-decision-log.md#october-7-2026-business-connected-flow-and-offline-e0-plan).

Source date retained: 2026-10-08. The source research dates below are preserved as supplied, not newly verified by this publication. Status: founder-approved design and [E0 implementation plan](cuadrao-business-e0-implementation-plan.md). Lucas selected task-by-task independent review and will coordinate execution. Verified official-index/format findings are distinguished from uninspected XSD semantics. This document dispatches no implementation or external operation.

## 1. Product intent and scope

The owner describes or captures a business event. Cuadrao prepares a draft from source documents, existing records and facts that the owner supplies. Cuadrao first attempts safe resolution within the policy in section 3. The owner decides the remaining questions. The owner reviews the result. The owner approves the action that affects business records or external systems.

The fiscal engine uses fixed rules to calculate amounts and validate the document. When authorized, replaceable signing and transport components process the fiscal document. Cuadrao links fiscal status, customer delivery, collection, evidence and the accountant package. Cuadrao keeps these results separate.

The product serves an owner who manages business money, customers, invoices, collections, expenses and documents. Research has not yet validated the first pilot customer, pricing, accountant format or detailed customer segment. The monthly search for missing documents remains a hypothesis. Personal, Household and Business spaces share identity. Each space requires separate ownership and access controls.

Manual forms and AI conversations use the same typed domain contracts, validation rules and approval process. AI may suggest facts with their sources and uncertainty. AI may not invent customer or tax data. AI may not calculate authoritative amounts. AI may not grant itself consent. AI may not approve actions. AI may not bypass permissions. The owner can complete the work without AI.

Success means fewer repeated decisions and a complete owner task with records that support each result. This spec does not claim frontier performance or a complete pilot.

**Approved first offline milestone:** within the existing Python backend, turn explicitly synthetic customer/invoice input into a deterministic unsigned XML artifact and local validation/evidence results for one supported profile. Type 31 B2B service invoice is the proposed starting profile, pending authoritative profile selection. No persistence integration, credentials, network calls, certificate handling, live fiscal-number allocation/use, cash effects, customer delivery or production issuance.

**Future scope:** isolated persisted capture-to-expense; customer/invoice records; actual payments and allocations; period review and accountant package; authorized signing/submission and delivery; broader fiscal profiles and controlled automation. These are separate deliveries with their own acceptance, not bundled into the offline milestone.

**Proposed E0 profile for written review:** Type 31 B2B service invoice, DOP, positive tax-exclusive lines explicitly assigned 18%, with no discounts, retentions, additional taxes or FX. This is a deliberately restricted synthetic fixture profile, not a claim that all services use that tax treatment. Unsupported combinations fail closed. The exact required/conditional-field matrix and rounding sequence are locked under P0 below before renderer/profile implementation.

## 2. Roadmap across the three lines

### Marketing

**Next milestone.** A signup on the real HTTPS site creates one stored record. An inquiry reaches the existing hola mailbox. Branding, contact text, privacy text and availability claims have approval. The marketing team proves recovery from provider failures. The team verifies retries, redirects and rollback.

**Next milestone after that.** The site converts qualified visitors into pilot participants. It explains the connected Business workflow. It states Consumer availability accurately.

**Owner and dependencies.** Marketing owns implementation and release evidence. Lucas supplies factual acceptance, product acceptance and external approvals. Marketing uses a separate release with a defined scope. That release must not unintentionally publish all integration work.

### Consumer

**Next milestone.** Lucas accepts the personal money flow on a physical phone. Evidence identifies the exact commit, build and environment. The test proves that data remains after the app restarts. The test also proves recovery.

**Next milestone after that.** Consumer proves hosted schema, API and authentication behavior. A useful small TestFlight follows when distribution prerequisites are complete. Household readiness, guest readiness and account deletion keep their separate acceptance gates.

**Owner and dependencies.** Consumer owns the release candidate and shared migration sequence. Apple enrollment and company work can proceed alongside local tests and hosted preparation.

### Business

**Next milestone.** Business completes the isolated owner flow: capture, review, one expense, reload, search and source retrieval. Business supplies proof for each result. The offline fiscal-engine milestone proceeds in parallel.

**Next milestone after that.** A customer validates one connected period of invoices, collections and expenses. The customer also validates the accountant package. Live fiscal processing requires separate authorization and acceptance.

**Owner and dependencies.** Business owns domain behavior and user outcomes. Business and Consumer jointly review shared contracts. Consumer coordinates the exact shared migration order and release boundary. The teams use one recorded migration order.

The owned fiscal engine remains part of Business. It does not replace customer, money, expense, collection or accountant functions. Lucas selected the valid first owner-only capture flow. That flow does not deliver the complete pilot promise. Existing invoice tracking and customer research need not wait for live fiscal issuance. No provider has been selected. This build decision does not authorize a contract, certificate custody or live issuance.

## 3. Must-not-miss Business flow map

This section specifies required behavior for each named actor. It does not transfer system responsibilities to the owner.

| Stage | Meaning |
|---|---|
| E0 | Offline fiscal engine. |
| B1 | Capture with verified space isolation. |
| B2 | Connected period pilot. |
| L | Later authorized fiscal processing and live expansion. |

These stages show dependencies. They do not authorize changes to another agent's assignment.

### Resolve-first policy

Cuadrao attempts safe, deterministic normalization before it asks the owner to resolve an exception. Each normalization must preserve meaning. Cuadrao also attempts recoverable operations that already have authorization. Each automatic action requires an explicit policy for allowed inputs, permitted changes, evidence, attempt limits and stop conditions. No policy means no automatic action.

Cuadrao records the original input, the applied rule and each change. Cuadrao preserves canonical record identity and original evidence. Normalization applies only to draft input. Approved, signed and submitted artifacts remain immutable.

Cuadrao must not silently change amounts, tax classification, customer identity, recipient identity, payment allocations or an approved invoice revision. Calculation from confirmed inputs is normal computation. It does not authorize changes to conflicting source facts. A required field remains unresolved without source evidence. Cuadrao must not guess fiscally significant identifier digits or dates.

An ambiguous match produces candidates with evidence. Cuadrao must not silently commit a candidate link or cash effect. Semantic corrections create a new revision. That revision requires the appropriate approval. After any change, Cuadrao rechecks permissions and approval validity before further action.

Cuadrao reports three distinct outcomes:

- **Resolved with evidence/history.** The permitted action completed. History contains the input, rule, changes, attempts and evidence.
- **Proposed fix requiring user decision.** Cuadrao explains the proposed change and supporting evidence. The owner decides before commitment.
- **Unresolved/blocked.** Cuadrao explains the reason and the next action.

The owner sees the smallest set of remaining actionable exceptions. History retains all original validation findings and attempts, including failed attempts. Cuadrao does not hide failures. Cuadrao must not claim success without durable evidence. E0 evidence remains explicitly synthetic and offline.

Transient retries retain a stable operation identity. The retry policy limits attempts and elapsed time. An unknown external outcome requires status reconciliation before any permitted retry. Cuadrao must not blindly resubmit or create new keys to force success. A timeout or status poll does not prove that an invoice was not issued.

E0 resolution tests cover deterministic safe normalization and full reporting of remaining errors only. E0 does not execute network recovery or autonomous AI correction. Existing E0 state tests use simulations only. Advanced matching and operational recovery remain later milestones. This policy enables neither autonomous tax advice nor live issuance.

### Domain vocabulary

These definitions control terminology in the revised flows. UI labels, API names and technical identifiers keep their exact spelling.

| Term | Meaning in this spec |
|---|---|
| Invoice | A document that records an amount billed to a customer. It does not prove payment or fiscal acceptance. |
| Fiscal engine | The Cuadrao component that calculates and validates fiscal documents using fixed, versioned rules. |
| Signature | A digital signature used to verify a document's origin and integrity. It does not prove fiscal acceptance. |
| Fiscal status | The tax authority's processing result for a submitted fiscal document. Local validation is a separate result. |
| Payment | A transfer of money. Payment terms alone do not prove this transfer. |
| Collection | Money received from a customer. A collection can pay all or part of an invoice. |
| Allocation | A record that assigns part or all of a payment to an invoice. It does not create another cash movement. |
| Source document | The original file that supports a business record, such as a receipt or an externally issued invoice. |
| Business space | The ownership and access boundary for business records. Shared identity does not prove isolation from other spaces. |
| Actor | A person or system that requests an action. |
| Revision | A specific version of a document or record. |
| Artifact | A generated file, such as unsigned XML or signed XML. |
| Digest | A hash of exact input or file contents. The system uses it to detect changes. |
| Profile | The supported document type and its field, calculation and validation rules. |
| Reconciliation | A check that resolves record differences or confirms an uncertain external result. |
| Accountant package | A versioned set of records, source documents, totals and unresolved items for an accountant. It is not a tax filing. |
| Normalization | A documented format change that preserves the input's meaning. It does not correct missing or conflicting business facts. |

### 3.1 Business readiness and roles

Stage: B1. Expanded roles come later.

1. The owner selects the correct Business space.
2. Cuadrao shows available capabilities.
3. Cuadrao shows missing setup.
4. Cuadrao rechecks actor permissions for reads, writes, jobs, source downloads and exports.
5. Initial access covers the owner only.
6. This scope does not imply existing access grants for accountants or staff.

### 3.2 Customer and invoice draft

Stage: E0 uses synthetic data. B2 adds stored records.

1. Cuadrao identifies the customer or creates the customer record within the current task.
2. Cuadrao retains issuer facts, buyer facts, dates, invoice lines, currency and source references.
3. Cuadrao shows missing facts.
4. Cuadrao shows conflicting facts.
5. Cuadrao tracks externally issued invoices without claiming that Cuadrao issued them.
6. Cuadrao applies the resolve-first policy before presenting the remaining exceptions.
7. Missing required fields remain unresolved without source evidence.

### 3.3 Review and approval

Stage: E0 tests domain guards. B2 adds the UI.

1. Cuadrao shows a document preview.
2. Cuadrao shows the exact calculated totals.
3. Cuadrao shows the sources for the proposed facts.
4. Cuadrao shows uncertainty and the proposed effect.
5. The owner reviews the proposed action.
6. Cuadrao binds approval to the actor, space, revision, artifact digest, input digest and action scope.
7. A changed revision requires new approval.

### 3.4 Validation, signing and submission

Stage: E0 provides validation and interface contracts. L adds real adapters.

1. The fiscal engine validates the selected profile and its rules.
2. Cuadrao retains unsigned and signed artifacts separately.
3. Cuadrao submits only an eligible approved revision through an authorized adapter.
4. Cuadrao shows local validation separately from the external result.

### 3.5 Rejection, uncertain result and correction

Stage: E0 tests simulated guards. L adds the official workflow.

1. Cuadrao first applies the resolve-first policy within existing authorization.
2. Cuadrao preserves the evidence.
3. A timeout can leave the external result unknown.
4. Cuadrao completes status reconciliation before any permitted resubmission.
5. Corrections after issuance follow verified profile rules.
6. Cuadrao preserves the original references.
7. Cuadrao explains remaining errors and the next action.

### 3.6 Customer delivery

Stage: B2 tracks external delivery. L adds delivery of documents that Cuadrao issues.

1. Cuadrao records the intended recipient and channel.
2. Cuadrao records separate queued, sent, delivered and failed results.
3. Provider evidence supports each recorded delivery result.
4. Cuadrao retries delivery without a duplicate send.
5. Official profile verification determines the required order of fiscal processing and delivery.

### 3.7 Collections and allocations

Stage: B2.

1. Cuadrao records each full or partial collection once.
2. Cuadrao allocates the collection to one or more invoices.
3. Cuadrao calculates the remaining balance from invoice, adjustment and allocation records.
4. Cuadrao shows collections with no allocation.
5. Cuadrao rejects currency mismatches explicitly.
6. Cuadrao rejects allocations that exceed the permitted amount explicitly.

### 3.8 Expenses and source intake

Stage: B1.

1. Cuadrao retains original file bytes from web intake and verified WhatsApp intake.
2. The owner can review the record manually.
3. Cuadrao requires consent for each receipt before AI preparation.
4. Correction, repeated processing and restart produce exactly one expense.
5. Business tests prove source retrieval.
6. Business tests prove that Cuadrao denies unauthorized access.

### 3.9 Reconciliation, refunds and reversals

Stage: B2 provides core behavior. Complex cases come later.

1. Cuadrao links evidence to existing money records without recording the same cash twice.
2. Cuadrao shows uncertain matches.
3. Cuadrao permits correction with a retained history.
4. Cuadrao records refunds and reversals as separate linked money actions.
5. These actions do not silently change an invoice or fiscal result.
6. Ambiguous matches show candidates and evidence without committing a link or cash effect.

### 3.10 Period review and accountant handoff

Stage: B2.

1. The owner selects the period and Business space.
2. The owner reviews missing source documents, unmatched money, invoice status, payment status and exceptions.
3. Cuadrao produces the agreed accountant package with a version identifier.
4. The package contains a manifest, source documents, totals and unresolved items.
5. Business supplies proof that an accountant can use the package.
6. An export is not a tax filing.

### 3.11 Daily exceptions and search

Stage: B1 provides retrieval. B2 adds connected actions.

1. Cuadrao shows failed preparation, missing facts, overdue balances and unresolved matches.
2. Search opens records with source evidence only when the actor has access permission.
3. Conversation proposes the same domain action as the manual UI.
4. Conversation shows the action's evidence and result.
5. Cuadrao presents remaining actionable exceptions after permitted resolution attempts.
6. The owner can inspect all original findings and attempts in history.

### Acceptance across all flows

Business supplies completion evidence for each applicable check:

- Stored data remains correct after reload.
- Revision history remains available.
- Duplicate requests do not repeat effects.
- Processing recovers after restart.
- Cuadrao checks writes against stale versions.
- Cuadrao denies actions without permission.
- Source documents remain available to authorized actors.
- The UI clearly shows empty, loading and error states.
- Completion claims match the evidence.
- Automatic resolution stays within its explicit policy and existing authorization.
- History distinguishes resolved actions, proposed fixes and unresolved or blocked items.
- Cuadrao preserves original findings when it reduces the visible exception list.
- Every change triggers permission and approval checks before further action.
- Unknown external outcomes block blind retries and replacement operation keys.

Cuadrao must not show success instead of a confirmed stored effect or an explicitly labeled simulation.

**Language check.** The revised flows use short active sentences, named actors and consistent terms. Sentence lengths and requirement preservation were checked. The [Issue 9 PDF](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf) and [official About page](https://www.asd-ste100.org/about.html) returned access errors. Full dictionary and part-of-speech checks remain incomplete. Domain terms in the glossary require that review before any full compliance claim. This edit does not approve implementation.

## 4. Architecture and existing foundations

Use a focused fiscal domain module under the existing `src/argus/domain` Python backend. Proposed boundary: `domain/fiscal` with typed input/profile definitions, decimal calculation, deterministic XML rendering, local schema/rule validation, evidence artifacts and signer/transport protocols. Names are design suggestions, not newly created files or public API commitments.

This is preferred to (a) embedding fiscal logic in a UI/provider integration, which couples domain truth to a vendor, or (b) deploying a separate fiscal service now, which adds operational boundaries before the local contract is proven. Keep the module separable through typed ports without creating a new runtime or cash ledger.

| Component | Contract and responsibility |
|---|---|
| Input normalizer | Explicit synthetic mode, profile identifier, revision, issuer/customer snapshots, currency, lines and source references. Apply the resolve-first policy before rejection. Reject input that remains incomplete, ambiguous or unsupported; never silently coerce a profile. |
| Decimal calculator | Parse decimal strings; reject binary-float input and nonfinite values. Compute line/tax/document amounts under a pinned profile ruleset. Rounding stages, precision and supported tax treatments must be sourced, versioned and tested before claiming profile support. |
| Profile registry | One supported profile initially. Bundle official schema dependencies and rule provenance; record original URL, retrieval date, declared version and actual file hashes. Same named version with different bytes is a different source artifact. |
| XML renderer | Stable element/attribute ordering, encoding, decimal/date formats and escaping; immutable versioned unsigned bytes. Same normalized input/revision plus renderer/profile/rules versions yields identical bytes and digest. No wall-clock/random values inside the deterministic payload. |
| Validator | Separate input/domain-rule and XSD results, with structured code, field path and source-rule reference. Local parser has external entities and network resolution disabled; schemas resolve from the pinned bundle only. |
| Evidence builder | Input/revision digest, profile/rules/schema/renderer versions and hashes, computed amounts, unsigned artifact hash, validation findings and synthetic-mode marker. Execution timestamps live in a separate run envelope. |
| Signer port | Receives an eligible immutable artifact and explicit signing context; returns a distinct signed artifact and verification evidence, failure or unavailable. E0 default is unavailable. Tests may return unmistakably simulated outcomes; no production signature claim. |
| DGII transport port | Submit/status-reconcile contracts carry stable operation identity, document/artifact digest and attempt evidence; distinguish pending, known rejection, known acceptance and unknown outcome. E0 has unavailable adapter plus test doubles only. |

Re-use the existing MoneyService/repository idempotency and revision foundations when Business integration is ready. Today inspected MoneyService reads accounts by user and enforces personal behavior; it cannot be called for Business merely by attaching a label. A reviewed space-aware extension/adapter must use the owned Business contract. Invoice payment allocations reference canonical money activities; they do not record the same cash a second time. Invoice outstanding balance derives from invoice/adjustment/allocation facts, not a separately editable status or cached second truth.

Re-use document capture, original-byte retention, digests, draft versions and consent boundaries through their eventual space-scoped contracts. The inspected snapshot stores originals in Postgres; private-storage work is separate lane work. Persistent customer/invoice/approval/artifact models are later integration work after the owned Business-space contract and migration ordering are established. `user_id` scoping or a free-text `space_id` does not prove same-owner Personal/Business isolation.

Profile constraints from the official-source handoff: eNCF is authority-authorized fiscal numbering, separate from an internal invoice ID. Type 31 purchaser RNC format permits 9/11 digits; fixtures do not establish issuer/buyer validity. `TipoPago` describes payment terms, not observed collection. Offline execution does not justify setting `IndicadorEnvioDiferido`. General item arithmetic is quantity × price − discount + surcharge; the proposed profile rejects discount/surcharge combinations. For positive amounts the cited rounding rule maps to Decimal `ROUND_HALF_UP`; unit prices may carry four decimals. P0 must settle the applicable rounding stages and field precision, rather than rounding every input early. Tolerances must never become invented balancing adjustments. Signing date/time belongs to the future signing operation; do not fabricate a signature or sign-time assertion in unsigned E0 output.

## 5. Independent state and evidence

Cuadrao keeps the following state dimensions separate.

| Dimension | Proposed internal states and evidence |
|---|---|
| Document revision | An approved snapshot is immutable. New edits create a new revision. Cuadrao retains links to superseded and correcting revisions. |
| Approval | States are unapproved, approved for a named action, and invalidated or revoked where permitted. Approval identifies the exact revision, digest, actor and space. Approval alone does not issue a document or make a payment. |
| Validation | States are not run, failed and passed for named schema, rules and profile hashes. An XSD pass is one validation result. |
| Signature | States are not requested, unavailable, failed, and signed and verified. Synthetic test outcomes carry a simulated label. Signed bytes have their own hash. |
| Submission/fiscal | States are not submitted, queued, processing/pending, unknown outcome, rejected, accepted and conditionally accepted. Cuadrao preserves the authority's actual code and response alongside these categories. Conditional acceptance remains distinct from unconditional acceptance. Exact transition and action rules require later official verification. |
| Delivery | States are not requested, queued, sent, confirmed delivered and failed/unknown. Provider acceptance does not prove recipient receipt. |
| Payment | Views are unpaid, partially paid, paid, overpaid/credit or disputed. These views derive from supported money, allocation and adjustment records. B2 defines the exact policies. |

### Required state controls

- Cuadrao must not silently change an approved revision.
- Later changes remove that revision's eligibility for processing.
- The owner must review the changed revision.
- Signing and transport results apply only to the submitted artifact digest.
- Transport acceptance does not imply fiscal acceptance.
- Fiscal acceptance does not imply customer delivery or collection.
- The same operation identity and input return the same effect and evidence.
- Changed input with the same operation identity causes a conflict.
- An unknown external result blocks a new submission until authoritative reconciliation determines the permitted next action.
- Cuadrao must not create a new operation key to bypass this control.
- Approved, signed and submitted artifacts remain immutable during resolution attempts.
- A semantic correction creates a new revision with the appropriate approval requirement.
- Cuadrao rechecks permissions and approval validity after every change.
- Transient retries use stable operation identity within explicit attempt and time limits.
- A timeout or status poll does not prove that issuance failed.

Validation failures before submission can produce a new draft revision. Corrections after signing, submission or acceptance must preserve original evidence. These corrections must follow verified rules for the profile.

The recovered diagram does not establish cancellation rules, credit-note rules, delivery order or production eligibility. Unsupported correction and live-delivery decisions remain blocked until the official rules are documented.

## 6. E0 acceptance and completion evidence

E0 is complete only when all items below are demonstrated at a named commit, with an offline reproducible command and retained artifacts. This spec does not claim any have been implemented.

1. One explicitly named synthetic profile fixture passes typed-input, decimal-total, supported business-rule and unsigned-preparation checks. The official format requires signing date/time and a digital signature for issued e-CF; E0 is an unsigned preparation artifact, not an issued document. Keep four distinct results: unsigned-preparation checks; any validation permissible against the unmodified official schema; full signed-envelope validation (not performed in E0); and actual DGII acceptance (not requested in E0). Inspect the official XSD before deciding which schema checks apply. Preserve raw validator failures; do not filter required-signature failures into a full-schema pass, add a fake Signature, or label a modified XSD official.
2. Repeated runs with identical inputs and pinned versions produce byte-identical unsigned XML and matching digest. A changed amount/customer/revision produces a different artifact and cannot reuse approval. XML escaping/Unicode and stable numeric/date formatting are covered.
3. An independent expected-results fixture covers the supported rounding/tax cases, including half-cent boundaries and permitted four-decimal unit-price input without premature rounding. Reject unsupported profiles, unassigned tax treatment, discounts/retentions/additional taxes/FX outside the proposed profile, missing required facts, invalid precision, nonfinite/binary-float amounts and totals inconsistent with the deterministic calculation. The explicit 18% fixture assignment is not an automatic tax-classification rule; exact field limits and rounding sequence are pinned under P0.
4. Negative fixtures distinguish input, business-rule and schema failures with actionable field-level findings. A tampered artifact/schema or missing dependency fails closed. No network schema/entity resolution is possible.
5. State tests prove stale/unapproved revision denial, mismatched artifact-digest denial, duplicate operation behavior, changed-input conflict, known rejection, pending/unknown reconciliation and prevention of blind resubmission. All remote outcomes are labeled simulated.
6. Default signer/transport return unavailable. No credentials, certificates, production customer/issuer data, live fiscal-number reservation, database migrations, database writes, customer messages or money effects are used. Fixtures use marked synthetic identifiers solely for offline validation and cannot route to a live issuer.
7. Test execution blocks outbound network and succeeds with no credentials or external services. Importing the module has no environment-dependent/network/database side effects. Exported evidence states “synthetic / unsigned / not submitted / no fiscal acceptance.”
8. Completion packet contains exact commit, command/environment, source manifest with real hashes, normalized synthetic input, expected arithmetic, unsigned XML, validation report, artifact digest and test report. Review distinguishes implemented code, local proof and deferred integration; no hosted/production claim.

### E0 resolve-first acceptance cases

These cases add offline proof requirements. They do not authorize live recovery or autonomous AI correction.

| Case | Required result |
|---|---|
| Safe format normalization | A documented canonical rule ignores JSON layout whitespace outside string values. Identical parsed fields produce identical unsigned XML. Evidence retains both original inputs and the applied rule. No field value, identifier or date changes. |
| Conflicting supplied total | Confirmed lines produce a calculated total that differs from the supplied total. Cuadrao retains both values and their sources. Cuadrao reports the conflict for a user decision. It does not overwrite the supplied total or claim validation success. |
| Missing RNC | A required purchaser RNC has no source evidence. Cuadrao reports the missing field and requests evidence. It does not invent digits or infer identity. |
| Ambiguous customer | A supplied synthetic case contains two plausible customer candidates. Cuadrao reports the candidates and their evidence. It commits no customer link, allocation or cash effect. E0 does not implement an advanced matching service. |
| Unknown submission result | A simulated timeout leaves issuance unknown. Cuadrao reports the block and required status reconciliation. It neither resubmits nor creates a replacement key. E0 performs no network call or recovery execution. |
| Complete error history | Safe normalization resolves one format issue while a required field remains missing. Cuadrao reports the remaining actionable exception. History retains the resolved issue, missing-field finding, changes and every attempt. |

Each case proves its outcome category, retained evidence and applicable permission and approval checks. Simulated state tests do not prove production persistence, live recovery or fiscal acceptance.

The module can be useful before live certification or supplier selection. It does not establish customer issuer authorization, Cuadrao provider eligibility, permitted signing/custody, DGII connectivity or legal production readiness.

## 7. Evidence register and limits

### Product, code and lane evidence

- Founder/delegated directions through this review: connected Business money/customers/collections/documents; owner-only capture first; own engine with replaceable signing/transport; manual and AI preparation share domain truth. The design and implementation plan are approved; Lucas retains execution coordination.
- Local snapshot inspected at `a7a45b1f115cdbccee50562fa69936fbe29c69d8`, checkout `/Users/garces/.codex/worktrees/baaf/private-alpha-next`. Cached integration inspected earlier at `ee4acd50e85a19328a04161c005a6b0cd2b7f4c5`; no fetch/live deployment verification. These are source snapshots, not current release guarantees.
- `docs/specs/cuadrao-master-plan.md`: full product/fiscal scope; recorded Oct 4 partner-first live path with owned backend parallel; identity/space target and current limitations. `docs/research/2026-10-04-cuadrao-product-business-architecture-source.md`: broader architecture and owned fiscal infrastructure. Later founder instructions govern the proposed owned-engine milestone; they do not select/cancel a provider or authorize live operations.
- `src/argus/domain/recording/money_service.py` (class at line 23), `money_schemas.py`, `money_plan.py`, `money_storage.py`: shared money commands, planning, revisions/idempotency; existing personal boundary requires deliberate Business integration.
- `src/argus/domain/ingestion/documents/models.py` (`DocumentDraft` at line 120), `service.py` (capture/digest at lines 143–184; consent/preparation thereafter), `store_postgres.py`: source-backed draft and original storage foundations. These do not prove the newer private-storage or Business-isolation slices are delivered.
- Counsel/lane assessment: local/merged work differs from hosted acceptance; Business isolation slices 1–3 were reported in progress. This spec makes no fresh GitHub, CI, hosted, Meta or phone-install claim.
- **“Cuadrao: who does what?”**, Oct 5 PNG and one-page PDF, recovered by the parent's separate worker. That supplied reconstruction—not a new inspection here—shows invoice details → engine XML → authorized signer → engine signed XML → DGII status, with separate customer delivery/collections. It assigns responsibility, not exhaustive production states. Original artifact identity should remain attached to the parent review; no filename/id was invented here.

### Interaction references

Observed on 2026-10-08 in the user's Safari second tab, via recorded Mobbin flows. Screenshots show interaction patterns, not persisted behavior, permission enforcement or current live product guarantees.

| Exact reference | Inspected evidence and limit |
|---|---|
| Creating customers | Opening customer list and creation drawer; not all nine screens. |
| Creating an invoice | Editor, inline customer selection, populated items/totals, Create & Send and list entry; some of 16 screens skipped/unloaded. |
| Marking an invoice as paid | Five stages including manual paid date, Paid state, activity and list; no partial allocation proof. |
| Re-matching a file | Three stages: source preview, retry/analyzing/pending and manual transaction selector; no successful match demonstrated. |
| Exporting transactions | Selection/readiness, CSV/XLSX/email options, progress, completion/download; exported package not opened. |
| Sharing a URL | Adjacent three-screen row: expiration choices and copied-link feedback; access/revocation untested. |

Useful patterns: contextual drawers, inline related-record creation, source beside editable facts, visible activity, exception queues, explicit export completion. Uninspected catalogue flows include receipt upload, expense creation, recurring invoices, reminders, cancellation, customer portal, bank connection, reports and roles. They are not claimed as reviewed. Cuadrao's orchestration, Dominican fiscal states and connected money model are its own design requirements.

### Official-source findings and narrow implementation prerequisite

- [DGII e-CF documentation index](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/documentacionSobreE-CF.aspx), directly inspected 2026-10-08: identifies the official format, signing guidance and Type 31 XSD. The index is a discovery source, not evidence of exact XSD semantics.
- [Official e-CF Format V1.0 PDF](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Formatos%20XML/Formato%20Comprobante%20Fiscal%20Electr%C3%B3nico%20%28e-CF%29%20V1.0.pdf), directly inspected 2026-10-08, cover October 2025: identifies Type 31 as Factura de Crédito Fiscal Electrónica. Section 2 and its mandatory-content table require signing date/time and digital signature for issued e-CF. The research handoff identifies the fields as FechaHoraFirma and Signature. Its change history explicitly includes changes without a version-number change; source bytes must therefore be pinned as well as labels.
- [Official Type 31 XSD link](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Documentaci%C3%B3n%20T%C3%A9cnica%20%28XSD%29/e-CF%2031%20v.1.0.xsd): index/link verified, bytes and imports not inspected. The research worker reported XML-reader rejection and HTTP 403 on direct retrieval. No checksum, optional-signature assertion or unsigned full-XSD pass is established.
- Official-source researcher handoff received 2026-10-08: [types and structure](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/TipoyEstructurae-CF.aspx), the Format PDF above, [Technical Report §§11.1.2–13](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Informe%20y%20Descripci%C3%B3n%20T%C3%A9cnica/Informe%20T%C3%A9cnico%20e-CF%20v1.0.pdf), and [issuer certification procedure](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Documentaciones%20Proceso%20de%20Certificaci%C3%B3n%20FE/Proceso%20de%20Certificacion%20para%20ser%20Emisor%20Electronico.pdf). The handoff supports the profile constraints above, reports signature timestamp format `dd-MM-AAAA HH:mm:ss` at GMT−4, and distinguishes processing, accepted, rejected and conditionally accepted fiscal states. These documents were researched by that worker; only the index/Format PDF were also opened by this spec author. Raw XSD bytes/checksums remain outstanding.
- Official certification Excel test data is obtained through the authenticated issuer portal according to that handoff. No downloaded official test set or example was verified. E0 fixtures must be labeled **Cuadrao synthetic cases**, never DGII certification cases.

**Prerequisite P0 — owner: Business fiscal implementation agent, reviewed by the technical reviewer.** Before implementing the Type 31 renderer/profile rules or claiming profile support, obtain and inspect the unmodified official XSD plus imports, pin exact bytes/checksums and retrieval URLs/dates, and map the format's required/conditional fields and supported service/tax/rounding subset to cited sections. Produce a short support matrix and an unsigned-vs-signed validation experiment with the raw validator result. Identify whether any unsigned schema validation is permissible without changing the official schema. Keep local preparation validation distinctly named if it uses a project-owned structural check. Exact signature/canonicalization requirements belong to the later real-signer milestone and must be independently source-verified then. If official bytes remain unavailable, report P0 blocked; do not replace them with an invented schema or signature. This prerequisite may be resolved during read-only planning/source-lock work; it does not block review of this written architecture.

Profile-specific status, correction and live-delivery sequencing require official verification before their production implementations. No legal eligibility, certificate custody or provider selection is established by these technical references.

## 8. Review decisions and handoff

Review the connected journey, E0 boundary and proposed Type 31 service profile. Agents own technical source verification, profile support matrix, exact tests and integration/migration analysis. Lucas owns product acceptance and later consequential/external approvals; customer/accountant research supplies pilot format and sequencing evidence.

Self-review: broader roadmap is distinguished from E0; same-owner isolation is not claimed; approval, fiscal, delivery and cash states are separate; offline validation is not certification; no exact DGII rules/checksums are invented; deferred work has explicit gates. The issued-document signature requirement is recorded, while uninspected XSD semantics remain P0. Lucas locked the resolve-first design after the draft review. The separate E0 implementation plan and task-by-task independent review are approved. Lucas will coordinate the existing Business agent before implementation starts.
