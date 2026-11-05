# Supplied source: Cuadrao Feature and Build Quality Guide

**Received:** October 4, 2026. **Status:** Supporting source, not adopted scope.
**Origin:** Text extracted from the [original DOCX](Cuadrao_Feature_and_Build_Quality_Guide.docx).
Paragraphs and table rows follow document order. Table cells are separated with
` | `. Layout and embedded link targets are not reproduced; consult the original
for those. No source recommendations are executed by this document.

Read [reconciliation](RECONCILIATION.md) before using the source as guidance.

```text
Cuadrao Feature and Build Quality Guide
Recommended scope acceptance criteria and delivery sequence
Prepared 4 October 2026
Cuadrao should connect personal money, household collaboration and premium business administration through one shared foundation. The near-term recommendation is to ship a reliable consumer journey, develop one useful business workflow in parallel and preserve the broader feature inventory without turning it into a launch checklist.
Direction already established
Consumer is mobile first. Start with a tiny TestFlight group, verify the connected journey and then release publicly with continued iteration.
Personal, household and business spaces share identity and reusable services. Membership and permission grants remain separate for each space and object.
Business is a premium offering. Its web release can advance independently while business iOS capabilities incubate in TestFlight.
Own the Cuadrao DGII MCP, fiscal backend and direct DGII integration as an architectural goal. Live issuance depends on separately verified issuer, signing and operating requirements.
How to use this guide
The guide proposes product contracts, engineering acceptance criteria and a delivery sequence. It does not verify the current repository, declare features implemented or commit the team to every recommendation. NOW means essential to a selected launch workflow; LATER means a retained candidate with prerequisites; SKIP FOR LAUNCH means intentionally excluded unless new evidence justifies a scope change.
Keep cash, manual accounts, reviewable imports and DOP or USD useful before relying on bank feeds. WhatsApp receipt intake is an explicit intended channel; Telegram remains a candidate. POS integration is discovery work. Prices, packages, usage limits and household billing have not been chosen.
The main quality requirement
A user must be able to capture a record, correct it, understand its effect, find its evidence and complete the next action without losing money accuracy or privacy. Every added surface must preserve that same behavior. Screen polish, automation and connector breadth should follow this contract.
01 Product scope across three spaces
The product converges when the same person can move between independent contexts without rebuilding their financial history or exposing it to the wrong people. A household invitation, an accountant grant and an employee role are different relationships. The interface must make the active space unambiguous before reading, importing, sharing or acting.
Space | Core user outcome | Initial boundary
Personal | Understand available money, obligations, debt, goals and the next income period | Private records; explicit sharing only
Household | Coordinate selected bills, plans, accounts and evidence | Only intentionally shared objects; no automatic visibility into personal records
Business | Connect customers, money, documents, collections and accountant preparation | Business roles and approvals; no inherited household or employee personal access
Required invariants
Every persisted record, attachment, job, search result and AI retrieval has an explicit space and an authorized actor. A client-side space filter is insufficient.
Billing rights do not imply financial-data access. Viewing an invoice does not imply issuing it, exporting it or sharing it.
Leaving or losing a business role revokes business access without deleting the person's independent consumer account. Ownership transfer and unresolved work have a defined handoff.
Any owner-wide view composes already authorized views and identifies its scope. It does not merge records or treat internal transfers as new income.
Acceptance evidence
Create two businesses, one household and private personal records for the same test identity. Verify reads and writes through UI, API, direct object links, downloads, search, notifications, jobs and AI tools. Revoke a membership during an in-flight action and require a fresh permission check before execution. Include a household member who is also an employee with a narrower role.
Recommended NOW: explicit space selection, clear owner and member lifecycle, a small role matrix and negative authorization tests. Recommended LATER: complex custom roles, consolidated owner dashboards and advanced delegation after the simple permissions model is proven.
02 Shared records and domain contracts
Reuse the existing financial, revision and household foundations where they satisfy the required contracts. Keep the current infrastructure direction until measured constraints justify a change. A reference architecture or vendor feature announcement is not a reason to migrate the product.
Record family | Proposed contract
Identity and grants | User, Space, Membership and PermissionGrant describe actor, scope, purpose, expiry and revocation
Money | Account and Activity retain exact amount, currency, balance basis, source, revision and lifecycle state
Evidence | InboxItem, Document, ImportBatch and SourceRecord retain original content, source IDs, file hash and processing history
Business operations | Customer, Invoice, FiscalDocument, Settlement and Allocation retain independent commercial, fiscal and payment states
Control records | ActionRequest, Approval, JobAttempt and AuditEvent retain intent, actor, expected revision, idempotency key and result
Money and identity rules
Use exact decimal or integer-minor-unit arithmetic with explicit scale and rounding. Preserve original-currency amounts. A translated view records the exchange rate, source, effective date and rounding policy. DOP and USD cannot be added as if they were the same unit. Use stable internal IDs; names, email addresses and provider labels are editable attributes.
Change and retry rules
Mutations carry an expected revision so stale edits are rejected or reconciled deliberately. Externally consequential actions have an idempotency key and a durable state. A timeout creates an uncertain outcome to reconcile, not a reason to blindly issue again. An audit records who changed what and the supporting evidence without storing credentials or unnecessary sensitive payloads.
Acceptance evidence
Property tests must preserve totals across edits, allocation and currency rounding. Repeated import and action requests must yield one intended result. Concurrent edits must not silently overwrite a reviewed amount. Replaying a job after worker failure must preserve external IDs and reconcile any previously accepted external outcome.
Recommended NOW: canonical records, provenance, exact money, revision checks and duplicate safety. Recommended LATER: formal accounting mappings, sophisticated event replay and additional adapter contracts when their workflow requires them.
03 Capture and document intake
Use one intake pipeline for camera capture, file upload, statement import and intended WhatsApp receipt forwarding. Channel adapters identify the source and create an Inbox item; they do not bypass the record, permission or review model. Keep the original document even when extraction fails.
The operating sequence
Identify sender and space → validate the file → preserve the original → detect duplicates → extract proposed fields → show uncertainty → review the proposed record and links → accept or correct → retain evidence. Each step has a durable processing state, a retry policy and an actionable failure reason.
Bind a channel sender to an authenticated user and authorized space. Ask for a target when the route is ambiguous. A forwarded document does not authorize data sharing or financial posting.
Support expected image and PDF types with size limits, safe previews and malicious-content handling. Preserve file hashes, source identifiers and the extraction version.
Separate extracted, confidence-scored and user-accepted fields. Currency, total, tax, issuer, date and references need visible correction paths. Do not silently replace a user's correction during reprocessing.
Handle low-quality photos, multi-page PDFs, informal cash receipts, missing dates, multiple transactions in one file and the same receipt arriving through several channels.
WhatsApp and optional channels
WhatsApp Business API receipt intake is intended Cuadrao scope. Validate sender binding, business onboarding, message and media retention, cost, duplicate deliveries and response permissions. A public broadcast Channel is a separate distribution surface. Telegram, email forwarding, connected mailboxes and Slack are later candidates whose value must justify their operational burden.
Acceptance evidence
Use a labeled corpus of Dominican receipts and statements, including Spanish text, DOP and USD, cash purchases and unclear images. Measure exactness by field, accepted-without-edit rate and correction effort. Test a delayed callback, duplicate webhook, failed upload and permission revocation mid-job. Every failed item must remain findable with its original and next step.
Recommended NOW: camera or file intake, reviewable extraction and explicit WhatsApp intake design or bounded pilot. Recommended LATER: more mail and chat adapters, automatic routing rules and broad attachment-type support.
04 Money imports and reconciliation
Manual and cash records must be first-class. A bank feed is one possible source of evidence; it does not define the complete financial picture. CSV and statement imports need a preview that explains account, period, currency, signs, dates, possible duplicates and opening-balance effects before acceptance.
Import contract
Preserve the source file or row, batch ID, parser version and original identifiers. Show accepted, skipped, duplicate and rejected counts that reconcile to the submitted batch.
Provide mapping for unfamiliar column names and explicit locale handling for dates and decimal separators. A parser must not guess a currency or silently reverse expense signs.
Retain corrections and source history. Reimporting a file, overlapping statement periods or manually entered activity must not create silent duplicates.
Matching contract
Candidate generation may use amount, currency, date, reference and counterparty. Text similarity can expand candidates, but deterministic constraints and explainable scores decide which suggestions reach review. Display why an item is suggested and allow rejection or an explicit manual link. An uncertain match remains an exception.
Represent many-to-many settlement with allocations rather than forcing a one-to-one match. This supports partial receipts, consolidated deposits, fees, refunds and currency differences. Complex matching can remain manual initially; its data model should still avoid future duplication. Do not call an invoice paid merely because a document and a transaction appear similar.
Concrete acceptance case
A DOP 12,000 invoice receives DOP 5,000 cash and DOP 7,000 through a payment provider. The provider deposits DOP 6,900 and keeps DOP 100. The invoice is fully collected; the deposit and fee remain separate evidence. Replaying any import must preserve the same result. No part of the sale, payment and deposit may become three revenues.
Measures and release gate
Measure precision of accepted suggestions, false matches, review time, unexplained differences and exception age on a held-out local corpus. Calibrate thresholds before enabling automatic acceptance. Track changes by currency and document type so easy cases do not hide poor performance on real customer cases.
Recommended NOW: manual entry, trusted imports, one-to-one suggestions and manual allocations. Recommended LATER: learned counterparty aliases, calibrated auto-acceptance and complex automated matching. Automatic acceptance requires a separate evidence-based decision.
05 Sales collections and fiscal boundaries
Choose one initial business workflow before expanding sales features. A practical candidate is customer → invoice draft → review → authorized issue and send → collection evidence → allocation → accountant package. Business records and document organization can be useful while fiscal readiness is still being established.
Commercial records
Keep customer, issuer, line items, prices, quantities, discounts, tax treatment, currency, dates, terms and payment instructions explicit. Draft changes are revisioned. Issued documents have stable identifiers and controlled correction paths. Reusable items, templates, recurring schedules and an installment model are expansion candidates, not prerequisites for a simple first invoice.
Separate state machines
State family | Meaning and required evidence
Commercial | Draft, issued, sent, viewed, overdue, cancelled or corrected; viewing does not prove agreement or payment
Fiscal | Prepared, signed, submitted, accepted, rejected or corrected under the applicable fiscal process; retain response evidence
Payment | Unpaid, partially allocated, paid, refunded or disputed; an attempted charge or unmatched deposit does not establish settlement
Owned fiscal architecture
The intended Cuadrao DGII MCP calls the owned fiscal backend. The backend validates drafts, generates the required payload, requests an authorized signature, controls submission and retries, and reconciles responses through a direct DGII adapter. Signing authority, certificate custody and issuer eligibility must be separately verified. Tool access does not grant regulatory authority.
Do not put private keys, certificate passwords or raw integration secrets in model context or MCP arguments. Keep signed payloads, hashes, submission identifiers, responses and correction links as evidence. Customer-controlled signing and a permitted trust-service adapter require distinct validation. This guide makes no finding of Dominican legal compliance.
Acceptance evidence
Test wrong recipient, changed amount after approval, partial collection, refund, expired customer link, duplicate issue request, rejected fiscal response and uncertain submission timeout. A reminder uses the current outstanding balance and the approved destination. Live fiscal release has its own issuer, signing, certification, recovery and retention checklist.
06 Files customers and accountant handoff
Inbox and retained documents
The Inbox is a work queue; the document library is the retained record. Completing processing removes an item from the queue without losing its original evidence or links. Search, tags, filters, preview and bulk actions should work across the authorized document set. Deletion and replacement account for referenced invoices, closed periods and retention obligations.
A focused customer workspace
A light customer record holds business identity, contacts, required fiscal identifiers, terms and communication preferences, with linked invoices, collections, files and optional projects. Keep it focused on completing business work. External enrichment, broad CRM synchronization and public customer portals should follow actual pilot demand.
Accountant preparation
Produce a versioned period package containing accepted activity, invoice and settlement detail, source documents, mapping choices and outstanding exceptions. Include a manifest with period, space, generation time, currency basis, record counts and export version. Make it clear when source records changed after an export.
Start with an accountant-agreed CSV schema and a predictable document package. Retain stable IDs for round trips, corrections and import diagnostics.
An accountant receives the specific business grant needed to review, annotate or export. Invitations and expiry are separate from sharing a public link.
A successful download proves only file generation. Verify ingestion separately if an accounting adapter is selected, including per-record errors and duplicate-safe retries.
Customer and export link safety
Use purpose-limited links with the appropriate expiry and revocation behavior. Avoid embedding unnecessary personal data in URLs. A recipient-facing invoice view reveals only the intended invoice and customer context. Download authorization must be checked for the underlying file as well as the page.
Acceptance evidence
Export the same closed period twice and reconcile totals and manifests. Correct a record afterward and show the difference. Test a missing receipt, a revoked accountant, a link copied to another browser and a failed export retry. A user must be able to recover their own records without relying on an AI conversation history.
Recommended NOW: evidence retrieval, useful filters, explicit exception status and export. Recommended LATER: recurring export schedules, destination accounting adapters, external portals, semantic document search and deeper CRM features.
07 Reports and useful financial context
Every financial view needs a declared basis. Start with balances, income and spending, obligations, available money, receivables and collections. Business profit, burn and runway should arrive only with definitions and enough complete data to make the numbers useful.
A report contract
Name the metric, period, time zone, scope, currency, conversion policy, exclusions and source freshness. Identify cash-based, invoice-based or another calculation basis.
Provide drilldown to contributing records and evidence. Expose missing documents, unresolved imports and stale connections before presenting a confident conclusion.
Separate actuals from forecasts. Store projection assumptions and make user changes visible. An estimate must not be styled like a posted record.
Use deterministic calculation services. AI can explain their output and cite the contributing records; it should not invent totals from prose or perform authoritative arithmetic.
Consumer and household use
Keep quincena and variable-income planning, bills, debt, goals and commitments coherent with recorded activity. A household view includes only shared records. Reimbursements and internal transfers need explicit treatment so they do not inflate household spending or earnings.
Business use
Useful first views include outstanding invoices, expected collections, upcoming commitments and missing evidence by period. Cash forecasts should disclose known receivables, fixed obligations and assumptions about payment timing. A management view does not become audited financial statements or a filed tax return by adding a professional-looking chart.
Acceptance evidence
Use fixtures with transfers, refunds, split payments, DOP and USD, unpaid invoices, a missing statement and a corrected closed-period record. Reconcile chart values to exported values and drilldown totals. Confirm that changing the report period or space invalidates stale cached data and any AI explanation derived from it.
Recommended NOW: a small set of understandable views with reconciled drilldowns. Recommended LATER: configurable widgets, more advanced forecasts, shareable reports and personalized summaries once the data and permission contract is stable.
08 AI tools and controlled automation
Use AI to find evidence, explain a trend, suggest a category, propose a match, prepare a draft or identify unresolved work. The structured application remains the source of truth and provides a non-chat path to the same task. Every interface uses the same domain services and authorization rules.
The action contract
Read authorized context → construct a typed proposal → validate business rules → obtain the required approval → recheck grants and revisions → execute idempotently → retain the outcome. The proposal names space, affected objects, recipients, exact amounts, currency and consequences. Explain success, failure and uncertainty separately.
Treat receipts, emails, imported descriptions and uploaded instructions as untrusted data. They cannot expand authority, select a new recipient or bypass review.
Preserve user corrections and preferences within their authorized scope. Learned mappings need visible inspection and reset. Do not infer permission from repeated behavior.
External AI access uses a selected space, explicit scopes, identifiable client, expiry or revocation, and server-side approval enforcement. OAuth, MCP, API, SDK and CLI are possible surfaces, not a simultaneous launch obligation.
A custom agent instruction can constrain behavior but cannot override permissions, fiscal rules, retention or approval requirements. Agent-to-agent communication requires bounded purpose and a traceable actor.
How automation may expand
Begin with visible suggestions and read-only summaries. Add a scheduled or event-driven workflow only after its deterministic action contract, error handling and approval policy are proven. Provide an activity view, pause or cancel controls, cost limits and a clear route to resolve stuck work. Long-running agents should resume from durable state rather than repeat completed actions.
Acceptance evidence
Test malicious instructions embedded in a receipt, a request that mixes two spaces, a revoked integration grant, altered amount after approval, repeated tool execution and an upstream timeout. Financial explanations must identify source records and data freshness. Track task completion, user correction, unauthorized-action blocks, cost and model regressions.
Recommended NOW: a narrow set of evidence-grounded, reviewable tasks. Recommended LATER: broader external AI access, memory-driven suggestions, voice and durable agents. Event triggers and autonomous cross-agent workflows need a separately accepted safety and operations plan.
09 Integrations with local fallbacks
Choose adapters by customer job, market coverage and support burden. Each adapter needs consent, scoped access, source IDs, durable cursors, deduplication, replay behavior, revocation and visible degradation. Preserve manual and file-based operation when an integration is unavailable.
Lane | Recommended sequence | Evidence before expansion
Financial records | Cash and manual accounts, then CSV and statement imports | Real local samples, reconciled counts and balances, duplicate tests
Receipt channels | Camera and upload, explicit WhatsApp intake pilot, then selected alternatives | Sender binding, target space, media failure handling, per-item cost
Bank feeds | Later only where useful coverage is proven | Institution and account coverage, consent, refresh reliability, history and support
Payments | Instructions and manual evidence before eligible payment links | Merchant eligibility, currencies, fees, webhook integrity, settlement and refunds
POS | Discover installed systems and customer-approved exports before one read-only adapter | Sales, tenders, taxes, refunds, edits, location IDs and settlement relationships
Accounting | Agreed export format before selected direct sync | Account and tax mappings, per-record acknowledgment, rejects and retry safety
Fiscal | Owned tools and backend with a direct authorized DGII adapter | Issuer route, signature, certification, current formats, response recovery
Context | Only files, mail or calendar needed for a proven task | Minimum scopes, user control, retention, deletion and useful outcomes
POS remains exploratory
Survey pilot businesses before selecting a POS vendor. Retain orders or invoices, items, discounts, taxes, tips, tenders, refunds and deposits as related records. A POS sale does not prove valid fiscal issuance, and a settlement deposit does not create another sale. Building hardware, reselling POS systems and supporting many providers are outside the initial scope.
Provider changes must be survivable
Document rate limits, outages, reconnect paths, schema changes, deletion behavior and commercial exit terms. Retain Cuadrao-owned canonical records and evidence. A partner's acquisition, product retirement or regional restriction should not erase the customer's ability to review and export their records.
10 Interaction quality and product polish
A polished financial product reduces the effort to find, inspect and correct records. Consistency matters across web and mobile, but each surface should fit its task. Business web can support dense review; consumer mobile should make frequent capture and understanding fast.
Patterns worth reusing
Use consistent global search, filters, detail panels, contextual actions and selection states. Preserve useful filters and scroll position when returning from a record.
Provide clear empty, loading, partial, error and stale-data states. A skeleton should not hide an indefinitely failed job. Distinguish saved, processing and accepted results.
Make bulk actions previewable and reversible where possible. Show selected count, scope and per-item failures. A partial batch success must not be reported as complete success.
Use keyboard navigation and accessible labels on web. On mobile, support legible dynamic text, reachable primary actions, reliable focus and a clear back path.
Notifications should identify the triggering record, active space and next step. Group low-value events, avoid duplicate alerts and let users control categories and channels.
Performance should be measured
Define real-device budgets for cold start, first useful screen, search, scrolling, document preview and common mutations. Record p50 and p95 by device, network and dataset size. Optimistic UI requires reconciliation and a correction path; it must not imply that fiscal issuance or payment settlement completed before acknowledgment.
Release evidence
Run end-to-end tasks on the founder's device and representative lower-performance devices with real authentication and realistic data volume. Verify light and dark appearance if supported, long Spanish names, DOP or USD formatting, long invoice references, keyboard-only use and assistive technology basics. Review screenshots and interaction recordings for every changed workflow.
Recommended NOW: consistent navigation, task-complete states, accessible forms and performance instrumentation. Recommended LATER: extensive customization, many shortcut variants, voice, desktop packaging and cosmetic options that do not improve the initial job.
11 Reliability security and operations
Background processing needs the same product care as the visible screen. Imports, extraction, reminders, exports and provider sync must have durable states and clear ownership. The user should know what is happening and the operator should know why it failed.
Required operational behavior
Use bounded retries with backoff and classify transient, permanent and uncertain failures. A dead-letter or equivalent exception queue needs inspection, safe retry and escalation.
Carry a correlation ID from intake through record creation, tool execution, provider calls and notifications. Avoid logging document contents, financial details or secrets unnecessarily.
Validate webhook authenticity and replay behavior. Treat delivery as at least once unless the provider contract establishes otherwise. Preserve enough evidence to reconcile missing callbacks.
Protect files and backups with the same access model as records. Test restore, export and deletion behavior. Document retention and recovery expectations before relying on them.
Keep integrations least-privilege and revocable. Scan dependencies and uploads, patch supported runtimes, and define an incident path for cross-space access or data corruption.
Signals worth watching
Measure queue age, processing latency, failures by stage, duplicate prevention, unmatched balances, stale sources, bounced reminders, export defects and per-space variable cost. Customer-visible incidents require a status and resolution path. Avoid dashboards whose success rate excludes dropped or unprocessed items.
Continuity and exit
Provide a documented export of records and original evidence. Separate the ability to stop billing, revoke access and recover data. Maintain a dependency inventory with provider alternatives and data ownership. A product winddown plan is part of responsible financial-data stewardship, even during an early launch.
Acceptance evidence
Run fault-injection tests for queue worker death, storage failure, duplicate webhook, expired credential, provider rate limit and database restore. Trace one stuck item end to end without privileged guesswork. Recover the core manual workflow during a connector outage. Block release on unresolved corruption, cross-space exposure or duplicate consequential actions.
12 Quality gates for every release
The following are recommended acceptance gates, not claims that the current build passes. Set numerical speed, availability and matching targets from a measured baseline. Invariants such as space isolation, exact totals and duplicate safety should not be weakened to meet a launch date.
Gate | Minimum evidence | Release blocker
Money | Fixtures and property tests for amounts, rounding, transfers, fees, partial allocations and currency separation | Incorrect totals or duplicate revenue
Permissions | Positive and negative tests across all surfaces, file URLs, jobs and revoked grants | Any unauthorized read or action
Imports | Original rows retained; batch counts reconcile; duplicate and overlapping imports tested | Silent drops or duplicate records
Documents | Original recoverable; uncertainty visible; corrections preserved; malformed files tested | Lost evidence or hidden extraction errors
AI actions | Typed proposal, grounded sources, approval and revision checks, adversarial content tests | Authority bypass or untraceable change
Jobs and adapters | Timeout, retry, replay and partial-failure tests with correlated outcomes | Duplicate issue or unreconciled uncertain action
Exports | Counts, totals, selected period and source manifest checked; recipient scope verified | Unusable or overbroad data release
Experience | Connected real-data journey on representative devices and realistic datasets | Cannot complete or recover the core task
Operations | Restore rehearsal, visible exception queue, cost limits and incident ownership | No recovery or unbounded spend
Fiscal if enabled | Current technical and operating requirements independently verified; sandbox and live route approved | Unresolved issuer or signing authority
Evidence must match the claim
A fixture demo proves a screen can render; it does not prove connected authentication, data integrity or live integration. A passing unit test does not establish safe end-to-end issuance. Keep the test run, build identifier, configuration and known limitations attached to each release decision.
When a gate fails, reduce scope or correct the defect. Do not hide a broken capability behind a success message. A consciously manual step is acceptable when the user understands it and the record remains auditable.
13 Golden journeys and regression corpus
Maintain a small set of repeatable end-to-end journeys as the product expands. Run them through real authentication and the supported data path. Add every significant production failure to the regression corpus with privacy-safe fixtures.
Consumer and household
New user creates a personal space, adds DOP cash activity, corrects a mistake and sees the resulting available money and plan. Restarting the app preserves the result.
User imports a USD statement, resolves a duplicate and compares accepted counts and balances. No view silently combines currencies.
Household owner invites a member, shares a selected bill and evidence, changes access and removes the member. Both people's personal records remain private throughout.
Business
An authorized sender forwards a cash receipt through the chosen intake channel. The reviewer corrects extraction, accepts the expense and later retrieves its original.
Owner creates and sends the selected invoice type, records partial collections, handles a fee and produces an accurate outstanding balance. A repeated send or issue request remains safe.
Accountant receives a scoped period package, flags missing evidence and returns a mapping correction. The correction appears in a new export version without erasing the prior one.
Adversarial and failure cases
Include duplicate receipt delivery, corrupted PDF, unknown currency, ambiguous date, two similar transactions, deleted source, revoked user, revoked integration, stale approval, concurrent edits, lost response, delayed webhook, rate-limited provider, crash during export and malicious document instructions. Test both recovery and the message shown to the user.
Corpus management
Label expected fields and relations, document why the answer is correct and separate tuning from held-out evaluation. Track the model, parser, rules and configuration used in each run. Segment quality by language, currency, document source and workflow complexity. Any automatic acceptance policy needs a measurable false-positive budget approved for its consequences.
Recommended NOW: these journeys and critical negative tests. Recommended LATER: larger performance corpora, chaos drills and expanded provider matrices as customer volume and connector diversity grow.
14 Delivery sequence without launch expansion
Work in two delivery tracks over shared foundations. Consumer shipping stays the immediate priority. Business discovery and a bounded web pilot can advance independently, while business iOS remains an incubation surface. Assign owners and limit simultaneous work; this guide does not select dates or staffing.
Stage | Recommended output | Advance when
0 Baseline | Verify existing flows, gaps, permissions and real-data readiness; select business customer and one job | Current behavior is evidenced and launch scope is explicit
1 Foundation | Exact records, space isolation, revision checks, import provenance and durable processing | Critical invariants and recovery tests pass
2 Consumer | Connected mobile journey and tiny TestFlight; fix blocking feedback, then public release | Core task works reliably with real authentication and data
3 Business pilot | Narrow web workflow around capture, money, documents and accountant preparation | Pilot completes the job, exceptions are manageable and value is observed
4 Fiscal lane | Owned backend and tool contract with independently validated issuer and signing route | Fiscal readiness is established for the exact customer and document scope
5 Expansion | Selected collaboration, automation and integrations with measured demand | Retention, accuracy, support burden and unit cost justify the next feature
Parallel work that helps
Research customer workflows, collect consented document samples, define fiscal requirements and design the shared permission model while consumer issues are fixed. Keep business experiments behind explicit boundaries. A discovery should change consumer scope only when it reveals a shared correctness or privacy requirement.
Work that should wait
Broad connector catalogs, complete ERP or accounting replacement, payroll, deep inventory, a new POS system, automatic tax filing, autonomous money movement and many AI execution surfaces should not become launch requirements. Preserve their questions and prerequisites so they are available when evidence supports them.
What to measure
Track first useful outcome, repeat use, accepted and corrected suggestions, time spent on exceptions, successful collections, export usefulness, support time and variable cost. Pricing experiments can follow these results; no amount, trial structure, household payer model or premium plan is selected here.
15 Decisions and research still required
Use this list to turn recommendations into explicit decisions. Record the decision owner, evidence, date, accepted scope and reconsideration trigger. A captured idea should not silently become a promised feature.
Question | Evidence needed | What depends on it
Who is the first business customer | Accessible pilots, repeated pain, source documents, invoice and collection patterns | Business workflow and adapter selection
Does first release issue invoices | Customer job and separate commercial versus fiscal readiness assessment | Sales scope, onboarding and support
Which roles and grants ship first | Owner, associate, accountant and household task walkthroughs | Permission matrix and invite lifecycle
How does WhatsApp intake operate | Official onboarding, sender binding, routing, retention, costs and callback tests | Intake pilot and customer expectations
What is the permitted fiscal arrangement | Current DGII requirements, issuer route, signing authority and qualified local review | Live e-CF release
Which banks or payment services are eligible | Real account coverage, Dominican merchant eligibility, currency and settlement tests | Feed and payment-link commitments
Is a POS adapter valuable now | Pilot installed base and representative export or sandbox records | One read-only sales adapter
What can be reused safely | Repository verification and regression evidence for money, revisions, grants and documents | Implementation plan and effort estimates
What should be charged | Willingness to pay, per-space AI and messaging costs, support effort and retention | Prices, plans, trials and usage allowances
What may act automatically | Task-level consequences, accuracy, review burden and approval policy | Matching and agent autonomy
Research limits
Public feature descriptions can reveal product ideas and explicitly stated mechanisms. They cannot establish hidden backend behavior, current reliability, security assurance or local regulatory eligibility. Verify any reused code's exact license and version before adoption. This guide recommends an independent implementation and has not changed a repository or shared information with a team.
Next planning artifact
Turn only the selected NOW items into tickets. Each ticket should name the user outcome, space and actor, source records, state transition, failure behavior, acceptance evidence and dependency. Keep the remaining catalog as a research backlog rather than estimated launch work.
16 Reusable implementation patterns
These are implementation candidates to evaluate against the existing Cuadrao stack. Keep the architectural boundary when it is useful; do not adopt every library or cloud service that can implement it. No stack migration is selected by this guide.
Typed domain services across surfaces
A validated command and query catalog can serve web, mobile, internal AI and a later public API or MCP. Publish request and response schemas, keep scope enforcement server-side and version external contracts. Generate SDKs only after the contract is stable. Explicitly parse configuration values; the string false must not become truthy simply because it is nonempty.
Asynchronous ingestion and progress
Acknowledge channel events promptly and enqueue durable work. Separate initial backfill, incremental refresh, extraction, matching and export jobs. Give each stage its own retry state and correlate it to the original item. Subscribe to real job progress rather than simulating a percentage. Removing a space or grant must stop the corresponding scheduled work.
Matching and searchable evidence
Normalize text and financial fields before candidate generation. A relational store with vector search and a suitable nearest-neighbor index is one option for semantic candidates; conventional indexes may be sufficient at first. Select embedding dimensions, weights, confidence bands and history windows using the local corpus. Calibrate from reviewed decisions, treat rejects and unmatches as negative evidence and preserve a safe unmatched state.
One document model for web and PDF
Keep rich content in a structured representation that can render consistently into an editor, customer web view and PDF. Test A4 and Letter, long names, page breaks, tax rows, QR codes and missing fonts. Separate preview from issued versions, enforce file authorization and use explicit cache rules for sensitive documents. A render endpoint is only one part of the invoice contract.
Notifications email and links
A shared event dictionary and reusable email components reduce inconsistent wording and event names. Keep inbound document ingestion separate from outbound delivery. Record recipient-level outcomes and partial batch failure. A short-link provider handles presentation; Cuadrao retains authorization, expiry and revocation. Compensate or reconcile if saving the record succeeds but creating its external link fails.
Consent and analytics
Test accept, decline, unset and changed consent states against actual emitted payloads. Define whether a choice stops all events or only removes identity. Keep financial payloads and document IDs out of analytics unless a justified, authorized use requires them. Product events should be consistent across surfaces and tied to meaningful outcomes.
17 Feature catalog for money and evidence
Recommendations for the selected workflow. NOW is a proposed priority, LATER requires evidence and dependencies, and SKIP means skip for launch. These labels do not create delivery commitments.
Capability | Priority | Dependency or scope boundary
Cash and manual accounts; corrected activity | NOW | Exact money, revision history, explicit space
CSV and supported statement import | NOW | Preview, mapping, provenance and deduplication
PDF and screenshot import with AI mapping | LATER | Labeled local samples and reviewable extraction
Camera or file receipts and original retention | NOW | Safe uploads and visible processing states
WhatsApp receipt intake | NOW pilot | Verified setup, sender binding, routing and cost
Telegram and other chat intake | LATER | Demand plus the common channel contract
Email forwarding and connected mailboxes | LATER | Least privilege, retention and duplicate-safe jobs
Tax extraction and mismatch warnings | LATER | Validated local fields; no implied fiscal approval
Suggested matches and manual links | NOW | Explainable evidence and correction path
Many-to-many settlement allocation | NOW model | Simple manual operation can precede automation
Automatic acceptance and alias learning | LATER | Held-out quality evidence and revocable decisions
Document preview, tags and filters | NOW | Scoped retrieval and original preservation
Bulk import and review actions | LATER | Per-item outcomes, safe preview and undo behavior
Document classification and summaries | LATER | Explicit processing settings and visible corrections
Promote a candidate into committed scope only after its user outcome, source records, permission boundary, error behavior, acceptance evidence and operating cost are understood. Preserve a reliable manual path while adding automation.
18 Feature catalog for connections and sales
Recommendations for the selected workflow. NOW is a proposed priority, LATER requires evidence and dependencies, and SKIP means skip for launch. These labels do not create delivery commitments.
Capability | Priority | Dependency or scope boundary
Global search and inspectable natural-language filters | LATER | Permission-safe index and structured fallback
Manual source health and future reconnect controls | NOW design | Staleness, last success and actionable recovery
Direct bank feeds and provider aggregation | LATER | Verified Dominican coverage and support
Provider-specific POS sales adapter | LATER research | Installed-base evidence and nonduplicative sales model
Full inventory or a new POS system | SKIP | Separate customer and operational case required
Customer records and linked collection history | NOW pilot | Minimal required fields and scoped access
Invoice draft, controlled issue and delivery | NOW if selected | Commercial and fiscal readiness kept separate
Web invoice view and downloadable PDF | LATER or pilot | Recipient scope, issued snapshot and render QA
Viewed status and overdue reminders | LATER | Viewing is not acceptance; current balance and approval
Invoice duplication and reusable templates | LATER | Revision-safe copy and required-field review
Private notes and multiple billing recipients | LATER | Exclude private notes; verify every recipient
Recurring invoices and automatic delivery | LATER | Schedule lifecycle, retries and explicit authorization
Payment links and mobile-wallet checkout | LATER | Eligible provider, settlement and refund reconciliation
Promote a candidate into committed scope only after its user outcome, source records, permission boundary, error behavior, acceptance evidence and operating cost are understood. Preserve a reliable manual path while adding automation.
19 Feature catalog for assistance and operations
Recommendations for the selected workflow. NOW is a proposed priority, LATER requires evidence and dependencies, and SKIP means skip for launch. These labels do not create delivery commitments.
Capability | Priority | Dependency or scope boundary
Project time and time-to-invoice | LATER | Pilot demand; billable approval and double-billing prevention
Accountant CSV and evidence package | NOW pilot | Agreed schema, manifest and exceptions
Direct accounting export adapters | LATER | Destination mappings, rejects and acknowledgment
Core financial views and drilldowns | NOW | Defined metric basis, freshness and currency
Configurable dashboard widgets | LATER | Accurate base reports and measured demand
Forecasts, runway and financial stress tests | LATER | Assumptions, completeness and deterministic calculation
Read-only assistance and typed drafts | NOW narrow | Evidence grounding, permissions and review
External AI, MCP, REST, CLI and SDK surfaces | LATER selective | Stable tool contracts and scoped revocable grants
Weekly comparisons and anomaly suggestions | LATER | Low-noise thresholds, named evidence and useful actions
Voice input and audio summaries | LATER | Accessible alternative and privacy or error handling
Scheduled agents with memory and proposals | LATER | Durable execution, approvals, cost and audit
Event agents, custom uploads and agent collaboration | LATER research | Validated operations and explicit safety case
Automatic tax filing and money movement | SKIP | Separate legal, partner and authorization readiness
Promote a candidate into committed scope only after its user outcome, source records, permission boundary, error behavior, acceptance evidence and operating cost are understood. Preserve a reliable manual path while adding automation.
```
