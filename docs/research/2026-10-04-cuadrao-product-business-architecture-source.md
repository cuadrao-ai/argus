# Supplied blueprint: Cuadrao Product and Business Architecture

**Received:** October 4, 2026.
**Origin:** Founder-authored 16-page blueprint, dated October 4, 2026, titled *Cuadrao Product and Business Architecture*. Recorded from a plain-text export, so tables, page headers and layout from the original are flattened, often one cell per line. Page numbers cited in the master plan refer to the original document.
**Use:** Planning input for the [Cuadrao master plan](../specs/cuadrao-master-plan.md). The source's own wording is kept; only whitespace was normalized. The source separates its adopted decisions from proposals that still need validation, and that distinction carries over. Nothing here asserts that a feature is built, a provider is chosen or a regulatory question is answered. Statements about DGII, PSFE requirements, signing and vendors are the source's claims and were not re-verified for this record.
**Related:** [Go to market vision source](2026-10-04-cuadrao-gtm-vision-source.md) · [Cuadrao master plan](../specs/cuadrao-master-plan.md) · [Decision log, October 4 entry](../specs/argus-decision-log.md#october-4-2026-cuadrao-launch-shape).

---

```text
Cuadrao Product andBusiness Architecture
One product for personal money, households and business
Cuadrao should let a person manage their own money, collaborate on household finances and operate a business through separate spaces. Shared services make the product coherent; explicit permissions keep each space private. The business experience should connect money, sales and documents, with useful AI available across the workflow.
This blueprint describes the proposed Cuadrao design. It is not a verified inventory of features already shipped. The decisions below are adopted direction; the module details, data model, integrations and sequencing that follow are proposals to validate before implementation.
Decisions already adopted
Build one Cuadrao spanning personal, household and business use, with a premium business offering and a consumer experience that can earn revenue in its own right.
Keep a person’s personal space independent of their roles as business owner, employee, accountant or household member. Sharing belongs to a selected space and authorized objects.
Start consumer distribution with a small TestFlight group, then use public consumer feedback. Business web can launch independently while the business iOS experience remains in TestFlight.
Reuse the consumer foundations where they fit. Business collaboration, integrations and agent execution require their own implementation and validation.
Own the Cuadrao DGII MCP, fiscal backend and direct DGII integration as an architectural goal. This is Cuadrao tooling to build, not an official DGII MCP or an implemented capability.
Product center of gravity
For the Dominican Republic, useful daily work begins with cash, manual bank accounts, DOP and USD, receipt and statement imports, customer records, collections and accountant preparation. WhatsApp Business API receipt forwarding is an intended capture channel; Telegram is a candidate. These integrations still need implementation. No local bank-feed coverage is assumed. Fiscal issuance has its own readiness requirements.
How to use this blueprint
Pages 2–5 define spaces and eight connected modules. Pages 6–9 describe AI, architecture, data and workflows. Pages 10–12 cover connectors, the business model and release decisions. Pages 13–16 separate tax-independent launch work, the tax product, certification tracks and the proposed owned fiscal and signing architecture.
Open commercial choices: consumer and business prices, household billing, AI allowances, paid service packages and upgrade boundaries have not been selected.
02  Spaces and permission boundaries
A user identity can belong to several spaces without merging them. A personal space is private by default. A household space contains only the accounts, plans and records its members intentionally share. A business space holds the business’s customers, operational records and documents.
Space
Core work
Access rule
Personal
Accounts, spending, budgets, goals, debt, commitments and projections
Only the person and specifically authorized access
Household
Shared bills, selected accounts, goals and household documents
Member grants scoped to the household and selected objects
Business
Money, customers, invoices, collections and accountant preparation
Owner-defined roles and object permissions
Roles belong to a space
A business owner can administer the business without gaining access to an employee’s personal money. An employee can capture a receipt or manage assigned customers without receiving blanket access to every account. An accountant can review and export approved business records under a specific grant. Household membership creates no business access. One person may hold different roles in different businesses.
The proposed role system should start with a few understandable presets, then resolve them into permissions such as account read, document upload, invoice draft, invoice issue and export. Separate access to an object from authority to act on it. Support time-limited accountant access, revocation and an audit of permission changes.
Shared services without shared visibility
Reuse identity, account and activity primitives, exact-money calculations, documents, revisions, idempotency and household grants where their behavior fits the business requirements.
Keep each record’s space explicit in storage, queries, search indexes, file access, background jobs and AI retrieval. A space selector in the interface is not sufficient isolation.
Treat a transfer between personal and business accounts as two explicitly authorized records linked by a transfer relationship. A combined owner dashboard must use grants and avoid duplicate totals.
Membership and billing are separate
A billing administrator should not automatically receive access to financial content. Invitations, joining, leaving, ownership transfer and data export need clear lifecycle rules. Removing someone from a business must preserve their independent personal space. If household billing is introduced, define who pays, which benefits are shared and what happens when membership changes before charging for it.
03  Money and document capture
Module 1  Accounts and transactions
Support cash, bank and other relevant account types with an explicit currency and balance basis. Start with manual activity and reviewable CSV or statement imports. Add read-only financial connections only after provider coverage, consent, data quality and operational support are proven for the target market.
The workspace should support search, filters, categories, merchant or counterparty names, tags, notes, attachments and recurring-item suggestions. Categories can be proposed automatically but must preserve user corrections. DOP and USD balances remain separate unless a view deliberately translates them using a named rate, date and rounding method.
Each import needs a batch, source file or provider reference, original row, parser version and review state. A preview should reveal detected duplicates, uncertain dates, sign conventions, currency assumptions and opening-balance effects before records are accepted. Re-importing the same statement must not silently create a second set of activity.
Bank activity is one source of evidence. Cash entries, manual records, sales documents, e-CF records and settlement evidence also matter. Canonical operational records should retain their provenance and correction history; bank rows alone cannot define the whole business.
Module 2  Document inbox
Use one processing queue for receipts, invoices, statements and other evidence. Camera and file upload, WhatsApp Business API receipt forwarding and any later Telegram integration must feed this same pipeline. WhatsApp is an intended channel, not an implemented claim; Telegram remains under consideration. Email forwarding and connected Gmail or Outlook are additional adapter options.
Link each external sender to an authenticated Cuadrao identity and require an explicit target space or a previously authorized routing rule. Resolve ambiguity before processing into personal, household or business records. Validate file type and size, scan for malicious content, detect duplicates and retain the original safely. A forwarded message must not grant access or permission to post.
Extraction should propose document type, issuer, date, currency, totals, taxes and references while retaining the original file. Keep extracted fields, confidence and user-accepted fields distinct. Low-quality images, informal receipts, duplicate forwards and documents containing several transactions must reach a visible review queue.
Matching should suggest links to activity, invoices or settlements based on amount, date, currency, reference and counterparty. Support one document linked to several records and several documents supporting one record. A possible match must not be shown as reconciled until the required review is complete.
The normal operating loop
Capture → extract → detect duplicates → propose record and links → review exceptions → approve → retain evidence. Track unresolved items by age, reason and owner. The intended benefit is less manual entry and faster exception review, which must be measured rather than assumed.
04  Sales customers and fiscal readiness
Module 3  Invoices and collections
The proposed sales record contains customer, issuer, line items, quantities, prices, discounts, tax treatment, currency, issue date, due date and payment instructions. Drafts support revision. Issued documents need stable identifiers and a controlled correction path. PDF delivery and a hosted customer view are optional output surfaces over the same record.
Keep commercial states such as draft, issued, sent, viewed, overdue or cancelled separate from payment state. A viewed link does not prove acceptance; a payment attempt does not prove settlement. Support partial payments, credits, refunds and disputed balances. Reminder schedules should respect recipient consent, customer context and the owner’s approval policy.
Recurring invoice schedules, numbering rules and payment links are useful follow-ons once basic issue, collect and correct flows are reliable. Payment-provider selection must depend on Dominican merchant eligibility, currency, settlement, fees and support. Do not presume that a particular provider is available to every customer.
Module 5  Customers and light CRM
Maintain the customer’s business name, contacts, communication preferences, tax or fiscal identifiers when required, addresses and default terms. Show linked invoices, payments, files and optional projects. Keep this focused on revenue work and collections; a full sales pipeline or marketing platform is outside the first scope.
Customer portals, external enrichment and broader CRM sync are optional. Customer-facing links need restricted scope, expiry or revocation as appropriate, and a clear distinction between a private document and a reusable public page. Avoid enriching personal data simply because a connector can supply it.
Fiscal capability has a separate release gate
A commercial invoice, an e-CF submission and money received are different records with different states. Store fiscal identifiers, submission attempts, acknowledgments, acceptance or rejection responses and correction references without overwriting the commercial history. Use the current DGII formats and technical specifications when implementing this boundary [1].
Before enabling live issuance, confirm the issuer’s onboarding and certification route, the applicable provider model, customer responsibilities, test evidence and support process. Resolve customer-controlled signing versus any legally permitted delegated service. Encrypted certificate storage by itself does not settle the legal or security requirements for custody [6]. Do not present Cuadrao as an authorized fiscal provider, licensed bank or complete accounting system without the necessary basis.
05  Work files reporting and accountant preparation
Module 4  Projects and time
For service businesses, link customer → project → time entry → invoice item. Allow manual entries and an optional timer, with date, contributor, description, billable status and an agreed rate. Approval should precede billing; invoicing must not bill the same entry twice. This module is optional and should follow demonstrated demand rather than delay the core money, sales and documents experience.
Module 6  Vault
The Vault is the long-term document library. The Inbox is the processing queue. A receipt can finish processing and remain in the Vault, linked to its activity and customer. Contracts, statements, licenses and other files need tags, search, versioning where appropriate, bulk handling and clear retention rules.
Preserve original evidence, file integrity and who supplied it. Downloads and shared links must enforce the same space and object grants as the interface. A document deletion or replacement should account for retention requirements and references from issued records or accountant packages. AI search must return only files the requesting identity may access.
Module 7  Reports and management views
Provide cash position, income and spending, receivables aging, collections, upcoming commitments and trend views. Profit, burn and runway can be proposed later, but every metric needs a definition, date range, currency basis, exclusions and completeness indicator. Show whether a view uses cash movement, invoices or another basis. Label projections and assumptions separately from actuals.
A report should drill down to its contributing records and documents. It should identify unreconciled activity, missing evidence and stale connections. Never add DOP and USD directly, count an internal transfer as revenue or describe a management view as audited financial statements. AI may explain an already calculated report; deterministic services calculate its numbers.
Module 8  Accountant preparation
Prepare a reviewable period package: categorized activity, invoice and settlement detail, document links, reconciliation exceptions and an export manifest. Let an accountant request missing evidence or correct mappings with visible history. Export versions should record the period, selected scope, preparation time and whether records changed afterward.
Start with agreed CSV and document formats. Direct accounting adapters can follow when a target accountant’s workflow warrants them. Mappings to external accounts, tax codes and tracking dimensions belong to each business and destination. A successful file export is not proof of a successful import, completed reconciliation or filed tax return.
06  AI actions and the trust boundary
AI should help across the product: locate a receipt, explain a cash trend, propose categories, prepare an invoice, suggest a match, draft a reminder or assemble an accountant package. The same tasks should remain available through structured screens. Chat is another interface to the product, not a separate database or privileged execution path.
Read reason propose approve execute
Read only records visible to the authenticated user in the selected space. Return source links and the data’s freshness when explaining a result.
Generate a typed proposal containing affected objects, intended changes, amounts, recipients and consequences. Validate it against deterministic business rules.
Apply the same action permissions and approval requirements as the UI. Recheck grants, object revisions and critical values immediately before execution.
Execute through canonical backend tools and retain actor identity, proposal, approval, result and correlation identifiers. Expose success, failure or uncertain outcome clearly.
Examples of proposed tools
Tool family
Useful action
Required control
Money
Search activity; propose categories; create a cash draft
Space and account scope; exact arithmetic; review before posting
Documents
Extract fields; suggest matches; link evidence
Untrusted-content handling; file access; duplicate detection
Sales
Create invoice draft; send an approved reminder
Customer and object scope; recipient and amount review
Preparation
Calculate a report; assemble an export
Defined metric basis; authorized destination and period
External assistants and automation
Expose selected capabilities through an authenticated MCP server and versioned API. External AI clients and automation services should use explicit grants, with object-level read and write scopes, selected spaces, revocation and expiration. Treat OAuth, API keys, SDKs and a CLI as alternative integration surfaces, not commitments to ship them all.
An external assistant must act under its identifiable client and the authorizing user’s permissions. It cannot borrow owner authority or bypass approvals. The owned Cuadrao DGII MCP should expose fiscal schema retrieval, draft validation, approved e-CF submission, status polling and acknowledgment retrieval through the owned fiscal backend. Tax-filing tools remain a future, separately verified scope. Prefer narrow grants; set usage limits from cost and abuse evidence.
Operational safety
Use idempotency keys and durable action states so retries cannot duplicate invoices, messages or records. Handle timeouts as uncertain outcomes until reconciled. Treat document and message content as data, never as instructions that grant authority. Test prompt injection, cross-space leakage, revoked access, stale approvals and duplicate execution before launch.
07  Architecture with a shared backend
Use one canonical permission and action layer for every interface. The owned Cuadrao DGII MCP calls the owned fiscal backend, which uses a direct DGII adapter when authorized and ready. Signing remains a separate compliant service or customer-controlled responsibility.
Figure 1  Proposed logical architecture. Cuadrao owns its DGII tool interface and fiscal backend; all surfaces share permissions, approvals and canonical records.
Reuse the current foundations deliberately
The existing Render and Supabase direction is the starting point for validation, rather than a decision to migrate infrastructure. Assess the reusable account and activity model, exact-money behavior, revisions, idempotency, household grants, documents and drafts. Personal budgets, goals, debt, commitments and projections should remain coherent as business functionality grows.
Runtime responsibilities
Keep request validation and permissions close to domain services. Use durable jobs for extraction, imports, provider synchronization, reminders and exports. Record delivery attempts, retry state and final outcomes. Store original documents separately from extracted data, with protected access and retention policies. Search indexes and caches must inherit the same space boundaries.
Reliability before automation breadth
Observe queue delays, failed imports, duplicate prevention, reconciliation differences, provider errors and per-space costs. Establish backup restoration, incident handling and an operational route for stuck work. Degraded connectors should leave the core manual workflow usable. The full agent runtime and connector ecosystem are proposed capabilities, not implemented infrastructure claims.
08  Canonical data model
The following conceptual model defines relationships and invariants, not a final database schema. Stable records should carry space ID, provenance, timestamps, actor, revision and lifecycle state where applicable.
Figure 2  Proposed record relationships. Links describe relationships and evidence; they do not grant access to another space.
Money and allocation rules
Represent money as an exact amount with currency. Use integer minor units where suitable or fixed-precision decimals with an explicit scale; never binary floating point for posted money. Save exchange-rate value, source, effective time and rounding policy when conversion occurs. Preserve original-currency amounts alongside translated views.
An Allocation assigns an exact amount between settlement evidence and an invoice or activity record. This supports many-to-many matches, partial receipts, one deposit covering several invoices, fees and FX differences. Require allocations and adjustments to balance to the recorded amount under the declared currency rules. Unexplained differences remain exceptions.
Source evidence and state are first class
ImportBatch and SourceRecord retain original rows, files, hashes and external IDs. POS records need merchant, source, location and record identifiers, with revisions for late edits. DocumentLink records evidence and review status. Commercial, fiscal and settlement states remain independent. Reports derive from approved operational records; an accounting adapter may map them into formal books under a separate contract.
09  Workflows that prove the model
A receipt from capture to accepted expense
A member uploads a photo or sends it through an authorized channel. Cuadrao identifies the target space, stores the original and creates an Inbox item. Extraction proposes fields; matching searches only eligible records. The reviewer resolves duplicates and uncertain amounts, accepts or edits the draft, then links the evidence. Cash receipts can create a manual expense without waiting for a bank feed.
A customer invoice through partial collection
An owner prepares an invoice, reviews customer, currency, amounts and terms, then issues and sends it through an allowed channel. Fiscal submission runs only when that capability and issuer are ready. A collection reminder uses the current outstanding balance. The customer’s payment evidence is matched and allocated; a failed provider attempt stays separate from a settled receipt.
Illustrative example: a DOP 12,000 invoice receives DOP 5,000 in cash and a DOP 7,000 customer payment through a provider. If the provider settles DOP 6,900 after a DOP 100 fee, the invoice can be fully allocated while the deposit and fee remain distinct records. The fee must not appear as an unpaid DOP 100 customer balance. Currency differences require their own explicit conversion and adjustment records.
Statement import and period reconciliation
Upload a statement or CSV, identify the account and period, preview rows and review currency, date and sign assumptions. Dedupe against previous imports and existing manual entries. Confirm accepted records, then compare statement totals and opening or closing balances where supplied. Keep unresolved differences visible. A source correction creates a traceable revision rather than silently rewriting a closed period.
Shared household bill without private data leakage
A member adds an agreed bill in the household space and links only the permitted payment evidence. Personal activity remains private unless explicitly shared. A reimbursement can link two authorized records without duplicating household spending. When a member leaves, their personal space survives and household access is revoked according to the agreed retention policy.
Accountant handoff and return
Select the business and period, review missing documents and unreconciled activity, then prepare a versioned export with a manifest. Grant the accountant only the required access. Record mapping corrections and questions against the relevant records. If an external accounting system is used, verify destination acknowledgment and track rejected records without duplicating successful ones.
Each workflow needs tests for duplicate delivery, retries after timeout, revoked permissions, concurrent edits, cancelled actions and incomplete data. A demo with fixture data is not release evidence.
10  Connector priorities for the Dominican market
These phases are prioritization proposals, not delivery commitments. Start with integrations that complete a local workflow. Add a provider only after validating coverage, authorization, data quality, support burden and cost.
Category
Proposed MVP
Phase 2 candidates
Phase 3 options
Money and sales inputs
Cash, manual accounts, CSV and statement import; POS export discovery
Verified bank feeds; one read-only POS adapter for pilot demand
Additional providers and merchant systems
Document capture
Camera and upload; WhatsApp Business API intake design and pilot
Telegram candidate; forwarding email; Gmail or Outlook
Additional approved chat, storage and document sources
Payment outputs
Payment instructions; manual evidence and collection tracking
Eligible payment links with webhook and settlement reconciliation
Partner-led money execution after separate approval
Accounting and fiscal
Accountant CSV and document package; fiscal discovery and tests
Selected accounting adapter; live e-CF only after readiness checks
Broader mappings and jurisdiction support
AI and context
Own interface over a small set of validated actions
Scoped MCP or API pilot; selected calendar or file context
Broader AI clients, automation tools and context adapters
POS integration is a discovery lane
Propose a vendor-neutral, read-only sales source. Survey 5–10 pilot businesses about their installed POS, validate customer-approved exports, then select one API adapter. Alegra has a documented Dominican POS and public API [3a, 3b]. Odoo is a candidate for merchants already using it, subject to plan and deployment constraints [4]. Toast is a benchmark; its published market list does not establish Dominican availability [5]. No partnership or reseller arrangement is assumed.
Preserve orders or invoices, items, taxes, discounts, tips, tenders, refunds and later deposits as linked records. A sale, its collection and its bank deposit must not become three revenues. Cash remains cash; card settlement may be net of fees. Verify read access, change and refund coverage, test data, polling or backfill, quotas and commercial terms. Imported sales do not establish e-CF validity.
Contracts and fallbacks
Every adapter needs consent, scoped access, source IDs, durable sync state, deduplication, retry handling and revocation. Keep manual and file workflows usable when a connector fails. Add calendar, files, CRM or other context only for a proven task. Building or distributing POS hardware and a broad connector catalog are outside the initial commitment.
11  Business model and distribution
Cuadrao’s commercial model should reflect the value of each space and the cost of serving it. Consumer use can be a sustainable paid product. Business premium can charge for operational value, collaboration and controlled automation. The prices, bundles and allowances remain open.
Offer to test
Value to validate
Commercial choices still open
Personal
Clarity, planning, useful assistance and reliable capture
Free versus paid boundaries; subscription price; AI allowance
Household
Shared bills, plans and selected records with privacy
Who pays; member entitlement; household package or add-on
Business premium
Collections, documents, preparation and team workflows
Per-space versus seat pricing; usage limits; premium features
Optional human service
Setup, migration, exception handling and guided preparation
Scope, turnaround, fee and capacity limits
A realistic early service model
Founder-led support can help users import their first statement, organize documents and resolve exceptions. Keep the service explicit and bounded. Record time per customer, case volume and what can be automated safely. If billing or onboarding initially uses a human operational fallback, define reconciliation, access, renewal tracking and failure recovery before relying on it.
Track AI, document extraction, storage, messaging, provider and human-support costs by customer or space. Use warnings and enforceable limits before offering heavy automated work. Any overage, service charge or recurring commitment must be clear to the customer. Avoid promises of unlimited AI or unlimited manual service until costs support them.
Distribution and channel roles
Use the website to explain and sell the product, the consumer app for everyday value, and business web for longer operational tasks. WhatsApp Business API should support receipt forwarding into the Inbox alongside private service conversations and approved business messages. Telegram is a possible additional capture channel. Public broadcast Channels are a separate distribution choice, not the receipt-processing interface.
Cuadrao’s own assistant can be the default guided experience. External AI integrations should widen access to the same authorized actions once the API and permission model are ready. Human service is a fallback or a priced offer, not hidden unbounded labor.
What would demonstrate repeat value
Measure first useful outcome, repeated weekly use, accepted matches, unresolved exceptions, collection progress, export completeness, retention, support time and contribution margin. More linked records may improve matching and reduce admin work, but that benefit must be demonstrated with user outcomes. It is not an established competitive advantage.
12  Release sequence and decisions to resolve
The current baseline and the proposed expansion
The earlier specification’s business concept was a private owner experience with manual accounts. Invoicing, employees, payroll and tax were outside that scope. Collaboration and the broader business experience require new acceptance criteria. Existing previews and fixtures are not proof that the space backend or agent runtime is finished.
Checkpoint
Evidence required before advancing
Consumer pilot
A small TestFlight group completes personal and household flows, including invitations and revocation; feedback is captured
Consumer public release
Core reliability and privacy checks pass; public feedback can be handled; paid value is testable
Business web release
Selected owner workflows work with real records; permissions, imports, recovery and support are verified
Business iOS release
Business-specific mobile flows pass their own TestFlight validation; web can proceed independently
Fiscal or money execution
Applicable legal route, provider eligibility, security, operational controls and end-to-end evidence are established
Decisions before committing a business build
Select the first customer segment and one complete money, sales and documents workflow. Decide whether invoice issuance belongs in the first business release or follows it.
Approve the initial role and permission matrix, shared-account rules, export rights and account ownership lifecycle.
Choose the commercial experiments for consumer, household and business; set enforceable cost limits and define human service scope.
Resolve the live fiscal route, issuer onboarding and signing responsibilities before promising compliant issuance. Verify each required local connector independently.
Boundaries that keep the first scope credible
Full ERP, payroll, broad inventory, automatic tax filing, formal accounting replacement and autonomous money movement are outside the first scope. Longer-term payments or transfers should be partner-led and separately authorized, with legal and operational readiness. This blueprint does not select a new infrastructure vendor or establish a launch date.
Primary implementation references
Primary sources for fiscal, distribution and integration constraints. They do not establish that Cuadrao features are implemented. Checked 4 October 2026.
[1] DGII  Current e-CF technical documentation and certification materials
[2] Apple Developer  TestFlight beta distribution and feedback
[3a] Alegra  Dominican POS offering
[3b] Alegra  Public invoice API
[4] Odoo  External API access and security
[5] Toast  Integration process and supported markets
[6] DGII  CA5198 certificate custody and signing models
13  Business can launch before the tax initiative
Core business work does not need to wait for fiscal issuance or tax filing. Issuance creates a sales fiscal document; filing reports the taxpayer’s applicable obligations for a period. Select a useful subset and ship when its own reliability, permission and support requirements pass. These are proposed independent lanes, not an implemented feature inventory or a commitment to include everything in the first release.
Product lane
Can proceed before fiscal issuance
Separate release requirements
Money and operations
Cash, manual accounts, CSV and statement imports, categorization and reconciliation
Exact money, provenance, duplicate prevention, review and recovery
Capture and documents
Receipt capture, intended WhatsApp intake, Inbox matching, Vault and document search
Sender linking, space routing, provider setup, file safety and access controls
Customer and collection work
Customer records, quotes and non-fiscal drafts; tracking valid existing invoices and receipts
Clear document labels, authorized reminders and accurate payment allocation
Reports and accountant handoff
Management reports, exception review, period packages and accountant exports
Defined metrics, completeness warnings, accountant mappings and controlled sharing
Live fiscal issuance
Its absence need not block the lanes above; keep issuance disabled until ready
Issuer onboarding, applicable certification route, valid signing and DGII acceptance tests
Tax preparation and filing
Records readiness and preparation can begin; declaration submission is a separate service
Applicable obligations, qualified review, authority, approved submission and official proof
Commercial work without false fiscal claims
A quote or non-fiscal draft must not be presented as a valid fiscal receipt. Tracking an invoice already validly issued by the business or another system does not authorize Cuadrao to issue a replacement NCF or e-CF. Import the source identifier, document and status; preserve the issuer’s record and handle corrections through its valid route.
How the tax product starts
Explore the first taxpayer segment with a qualified Dominican tax professional. Identify its actual obligations, periods, source records, exceptions and existing filing process. An e-CF does not eliminate every reporting or declaration obligation; requirements depend on the taxpayer and transaction [7].
Start with records readiness: gather evidence, reconcile, identify gaps and produce a reviewable package for the customer’s accountant. A paid assisted-tax service is an option to validate with a qualified professional, a written scope, clear fees and defined responsibility. Do not promise automatic filing or tax representation as part of the initial product.
14  Own the fiscal workflow and tax product
Owning Cuadrao’s verticals means controlling its records, product experience, business rules and service workflow. Reducing dependence on Alegra or Alanube is an independence goal. No vendor contract, required bridge or replacement deadline is assumed. Preparation can proceed in parallel; a PSFE decision must not hold up the tax-independent business lanes.
Proposed stages toward independence
Own the operating core first. Keep intake, OCR, matching, canonical records, reporting, permissions and UI under Cuadrao’s control. An Alegra POS connection can remain an optional sales-source adapter for customers who use it, without becoming a dependency of Cuadrao Business.
Own the fiscal backend and Cuadrao DGII MCP. Implement versioned e-CF validation, direct DGII requests, durable submissions, status and acknowledgments with identity, scope, approval and audit controls. DGII describes individual issuer certification using non-certified-provider software [10]; validate that route for Cuadrao and each pilot. Confirm operating-entity eligibility and compliant signing [1, 6, 8]. Keep private keys and certificate passwords outside model and MCP payloads. Optional bridges remain replaceable; regulated signing requirements remain.
Evaluate Cuadrao’s own PSFE route as a separate stage if it fits the commercial model. Owning software or an MCP interface does not itself make Cuadrao an authorized provider. Provider authorization and each customer’s issuer requirements remain explicit readiness checks [8].
Build validated tax preparation. Use versioned rules and form definitions with effective dates, taxpayer applicability, deterministic calculations, validation cases and professional review. Preserve each period’s evidence, mapping decisions and corrections. Start with a narrow obligation set rather than claiming coverage of all taxes.
Add authorized filing only after proving the legal, technical and operational route. DGII documents declaration submission through its Virtual Office; the e-CF API is not proof of a general filing API [9]. Keep an approved professional or taxpayer submission step until a supported integration is verified. Filing tools in the Cuadrao DGII MCP are future scope.
Controls for the first assisted filing workflow
Separate preparation, review, approval and submission. Verify the mandate and permitted access; an e-CF role is not assumed to authorize return filing. Present the taxpayer, period, form, amounts, annexes and assumptions for approval. The taxpayer or authorized professional files through a supported DGII channel. Retain the declaration, official acknowledgment, payment authorization where issued and audit trail. Track submitted, validated or accepted, and error states; payment remains separate.
Corrections need their own reviewed amendment workflow and proof of submission. Track requests for missing evidence, unresolved exceptions, deadlines and service responsibility. Do not claim a return is filed merely because Cuadrao prepared a file or sent it to an accountant. Bank services, POS hardware, full ERP and unrestricted autonomous tax action are outside this ownership plan.
Additional primary tax references
[7] DGII  e-CF FAQ including reporting obligations and exceptions
[8] DGII  Electronic invoicing routes and authorization
[9] DGII  Interactive declaration through the Virtual Office
[10] DGII  Individual issuer certification during provider transition
15  Parallel product and certification tracks
Customer issuer pilots can use the full individual certification route before Cuadrao becomes a PSFE [10]. Business operations and accountant preparation can progress in parallel. The DGII question about a foreign, non-certified software provider still had no response when checked on 4 October 2026 at 16:32 UTC [20]. Operating-entity eligibility, hosting and certificate custody remain separate issues; the pilot route is not blanket approval for that business model.
Track
When it can progress
Evidence required
Business product
Independently of fiscal certification
Selected workflows pass product, permission and operational checks
Customer issuers
Before Cuadrao PSFE status, through the applicable full route
Each customer completes its own tests and receives issuer authorization
Cuadrao PSFE
After applicant and customer prerequisites are met
Cuadrao applicant is an issuer; at least three successful customer issuers; complete dossier and provider tests
Full customer issuer pilot sequence
Confirm RNC, Virtual Office access, NCF eligibility, the linked representative, tax digital certificate, suitable software and applicable tax-compliance requirements. Submit FI-GDF-016. After the portal invitation, register the actual provider, software, version and authentication, reception and commercial-approval URLs. Sign and upload the application XML. Complete DGII data tests, realistic e-CF and commercial-approval simulations, PDF representation approval and inbound communication tests. Register production URLs, sign the integrity declaration and pass the taxpayer-status check. Activate production only after issuer authorization [13].
Prepare the Cuadrao PSFE dossier
Applicant prerequisites: RNC activity covering software sale or development, existing e-CF issuer status, at least three successfully certified customer issuers, and current tax obligations and formal duties. The three-client evidence precedes the application [11, 12].
Operating evidence: traceable logs and change control, backup and recovery procedures, an active institutional website, current security and continuity policies, a public data-protection policy under Law 172-13, support channels with response commitments, and a designated DGII contact [11, 12].
Application documents: completed and signed FI-GDF-017, also sealed for a legal entity, plus the required policies and contact details. Provide a current security certification if held; the checklist does not make ISO 27001 mandatory [11, 12].
Application and timing
Submit the package through a DGII office or the published facturacionelectronica@dgii.gov.do route. Follow the Virtual Office invitation to the Certification Portal, complete pre-certification tests and sign the integrity declaration. DGII lists a free application service and a 10-business-day response time; that is not an end-to-end certification or launch guarantee [11, 12].
[11] DGII  Current PSFE service requirements and procedure
[12] DGII  CA4409 provider authorization checklist
[13] DGII  Full electronic issuer certification process
[20] DGII  Open question on a foreign non-certified software provider
16  Signing infrastructure and vendor independence
Cuadrao should own the fiscal service and DGII MCP: authenticate the actor, validate data, generate e-CF XML, control sequencing and retries, request an approved signature, submit directly to DGII and reconcile the final status. A regulated signing adapter can supply the trust service without owning Cuadrao’s financial records or product workflow.
Viafirma and AVANSI are a candidate to evaluate
INDOTEL Resolution 070-2022 documents AVANSI S.R.L. authorization for certificate services and management of signature-creation data [14]; INDOTEL’s trust list also lists AVANSI [18]. Verify the exact counterparty, current authorization and service scope. The located conformity certificate expired on 1 April 2026 [19]; request updated evidence. That certificate’s expiry does not by itself establish that the separate authorization has been revoked.
The published Dominican tax-certificate profile describes secure delivery of a .p12 file, no retained private-key copy and no HSM storage for that profile [15]. Viafirma Fortress separately documents an unattended signing API [16]. A tax certificate purchase therefore does not establish a compliant hosted signing service. The exact Dominican custody product, contract and DGII compatibility still need proof.
Required proof before selecting a signing service
Legal and contractual fit: confirm the DGII-permitted SaaS interconnection route and obtain evidence that certificate use and e-CF signing occur on the authorized entity’s infrastructure. Otherwise, assess the distinct customer-controlled or own-authorization route [6].
Technical fit: obtain vendor-approved sandbox access [17]. Exercise API authentication, certificate selection, signature execution and signed-document retrieval [16]. Test e-CF XML and the authentication seed end to end with DGII. Generic XML signing support does not prove the required DGII signature profile works.
Security and operations: prove tenant isolation, authorized signing, auditability, expiry, revocation, retry safety and incident response. The backend uses securely stored integration credentials. Private keys and certificate passwords stay outside model context and MCP payloads; the model cannot request arbitrary signatures.
Commercial fit: confirm hosted-service and API pricing, certificate issuance and renewal, onboarding, usage limits, response commitments, support, liability and termination/export rights. No hosted API tariff or vendor agreement is assumed.
Preserve the ability to change providers
Keep the canonical invoice, generated XML, signed output, content hash, submission IDs and DGII responses in Cuadrao-controlled records. Store only the necessary provider references. A replacement adapter must preserve idempotency, evidence and customer authorizations; it does not imply that private keys can be exported or moved freely.
Alegra may remain a customer-selected POS source, and a fiscal bridge could be evaluated independently. Neither should define the Cuadrao DGII MCP contract. Independence from Alegra or Alanube’s fiscal stack still leaves a regulated trust-service dependency unless Cuadrao separately qualifies to provide that service.
[14] INDOTEL  Resolution 070-2022 concerning AVANSI
[15] Viafirma Dominicana  Tax certificate policy
[16] Viafirma Fortress  Unattended signing API
[17] Viafirma Fortress  Demo access process
[18] INDOTEL  Trusted service list
[19] INDOTEL  Located AVANSI conformity certificate
```
