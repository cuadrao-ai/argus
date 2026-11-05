# Supplied vision: Cuadrao consumer and business go to market vision

**Received:** October 4, 2026.
**Origin:** Founder-authored team alignment and business scoping document, dated October 4, 2026, titled *Cuadrao consumer and business go to market vision*. Recorded from a plain-text export, so tables and layout from the original are flattened, often one cell per line.
**Use:** Planning input for the [Cuadrao master plan](../specs/cuadrao-master-plan.md). The source's own wording is kept; only whitespace was normalized. The source separates its adopted decisions from proposals that still need validation, and that distinction carries over. Nothing here asserts that a feature is built, a provider is chosen or a regulatory question is answered. Statements about DGII, PSFE requirements, signing and vendors are the source's claims and were not re-verified for this record.
**Related:** [Product and business architecture source](2026-10-04-cuadrao-product-business-architecture-source.md) · [Cuadrao master plan](../specs/cuadrao-master-plan.md) · [Decision log, October 4 entry](../specs/argus-decision-log.md#october-4-2026-cuadrao-launch-shape).

---

```text
Cuadrao consumer and business go to market vision
Team alignment and business scoping
4 October 2026
We are building one Cuadrao with personal, household and business spaces. Consumer gives people a useful way to organize and manage their money. Business extends the same foundation into the daily financial administration of a small company. The two products share a brand and platform, while serving different jobs and launching on different readiness gates.
What we have decided
Consumer is the immediate shipping focus: a tiny TestFlight group to check onboarding and performance, then a full consumer release and continued iteration.
Personal and household spaces are the consumer experience. Business is a premium space with a connected business administration experience.
Business web can launch on its own schedule. Its mobile capabilities can mature in TestFlight without holding up the consumer release.
One account can participate in multiple spaces. Access must be granted separately for each space; business membership does not expose personal or household information.
Both products can earn revenue. We have withdrawn the idea that consumer must be a free loss leader. Prices and plan limits remain open.
Why this direction is stronger
Consumer lets us ship the product already taking shape and learn from real use. Business adds a timely, concrete entry point: helping Dominican owners keep invoices, receipts, payments and accountant-ready records connected as electronic invoicing becomes mandatory for more taxpayers. The opportunity is broader than issuing an invoice, but the first business workflow must be narrow enough to complete reliably.
What this brief asks the team to do
Protect the consumer launch scope. Start scoping Business today around one customer type and one end-to-end workflow. Reuse the common foundation, define separate access and approval boundaries, and choose the first business pilot only after validating the operational and regulatory requirements.
Status convention: “Decided” records the direction above. “Proposed” identifies scope, packaging or experiments that still need team agreement. Research conclusions have sources and explicit limits on page 6.
Consumer product and launch
Decided: Cuadrao Consumer serves personal and household money management. We should launch a coherent experience people can use repeatedly, then improve it from actual behavior rather than keep expanding the scope before anyone uses it.
The job we are solving
The current mobile specification targets Dominican adults managing cash, disconnected accounts, debt and quincena or variable income. The useful question is concrete: what is already committed, what remains until the next income, and what changes if I make this decision? A household needs the same picture together. The repeated loop is to record, understand, plan, notice change and return. [4]
The launch experience
Proposed acceptance journey: create a personal space, record or import a real transaction through the supported methods, correct it, see the effect on the financial picture, and return to use it again. For households, add an invitation, the right access, a shared record and a clear way to leave or revoke access. Final feature commitments must follow the verified mobile roadmap, not this illustrative journey.
We are initially working within the available data and integrations. Recording or planning a savings allocation is different from moving money into a bank or brokerage account. The longer-term vision of automatic spending, saving and investing remains, but those regulated connections are not prerequisites for this release.
What PR 813 establishes
Draft PR 813 updates the execution board, not runtime code. Native financial, household and authentication foundations have landed. A candidate ran on the founder’s physical iPhone with sample data and authentication disabled; connected real-data journeys and launch acceptance remain open. Sign-in, deletion, document handling and grants still have tracked work. [4]The current specification permits a named private Business space for manual records, while excluding employee workflows, payroll, invoicing and tax accounting. Premium collaborative Business extends that scope. Household sharing is a useful foundation, but business roles, space ownership and production authorization still need definition and implementation.
Consumer go to market
Use a clear landing page: who it helps, the money problem it solves, and a small product preview. The promise should be understandable before someone joins a waitlist.
Recruit a small TestFlight group to test onboarding, reliability, data accuracy and household permissions. Resolve the blocking failures, then move to public release.
Keep feedback and product iteration active after launch. Social content and referrals support distribution; launch does not reduce the product to maintenance.
Use engaged users and household invitations as candidate referral paths. Test whether invited people activate and return rather than assuming invitations will become viral.
Run capped acquisition experiments when useful. Track cost per activated and retained user, alongside signup and install conversion.
Revenue without uncontrolled free usage
Decided: consumer can be monetized. Proposed for evaluation: a bounded trial, paid advanced capabilities, and explicit limits on costly AI or document processing. A household-owner subscription is an option, not a selected policy. Choose packaging using measured usage cost and willingness to pay; do not promise unlimited usage before those economics are understood.
Business product and first customer
Decided: Cuadrao Business is the premium business space. The product ambition is connected business administration for owners who do not have a large back-office team. We will build our own connected experience around Dominican workflows.
The job we are solving
A business owner should be able to capture a sale or expense, find the supporting document, understand whether money was collected or paid, and give the accountant a coherent record. Today those steps can be spread across messages, invoices, bank exports and spreadsheets. Electronic invoicing creates a timely reason to start the conversation; ongoing organization and follow-through give customers a reason to stay.
A concrete candidate workflow
Proposed: a small service business creates an invoice, reviews the details, authorizes issuance through its eligible electronic-invoicing setup, sends it to the customer, matches the eventual payment and exports the supporting record for its accountant. Exceptions stay visible: rejected fiscal documents, missing receipts, partial payments and uncertain matches.
This example deliberately separates the invoice’s fiscal status, its commercial approval and its payment status. An accepted e-CF does not establish that a customer has paid. Reconciliation suggestions need evidence and a correction path.
How customers reach the product
Web workspace for records, approvals, collaborators and deeper review
WhatsApp business conversations for capture, questions and support, with clear confirmation for consequential actions
An authorized API or MCP connection for customers who want to use their own AI tools
Direct assisted service when an owner needs help getting set up or resolving an exception
These are intended channels around one service. We do not need to finish all four before a pilot. A public WhatsApp Channel is not the same interface as two-way business messaging.
What to scope first
Proposed first customer candidates: independent service providers, small professional-service firms, or owners already collecting documents through WhatsApp. Pick one based on access to pilot customers, invoice volume, repeated administration pain, integration burden and willingness to pay. Government pressure establishes a market event; it does not tell us which segment will buy our specific product.
What can progress in parallel
Business records, document capture, reconciliation and accountant collaboration can progress while fiscal onboarding is completed. Live e-CF issuance has its own customer certification and signing gates; becoming a certified service provider is a separate workstream. Tax preparation means organizing and checking the supporting records. Filing a tax return is a distinct authorized action: the initial workflow should hand off to the customer or their accountant, rather than imply automatic filing is already supported.
The first boundary
Start with one complete workflow and a small supported document set. Payroll, inventory, a complete accounting system and every industry-specific tax case should require separate scope decisions. The service should make an accountant’s work easier; a broad promise to replace professional accounting would create a different product and responsibility.
How the products converge
The convergence is a shared financial record and permission model across the different parts of a person’s life. An owner can run a business space, manage a personal space and join a household without maintaining separate identities or exposing everything to every collaborator.
Person
Where they participate
Access boundary
Consumer
Personal and optional household spaces
Only spaces they own or are invited to
Business owner
Business plus their own consumer spaces
Business controls do not grant access to other people’s personal spaces
Business associate
Invited business space; optional independent personal use
Only the business permissions granted to them
Household member
Invited household; optional personal or business use
Household access does not imply business access
Reuse the foundation
Proposed shared components: identity, space membership, scoped records and attachments, transaction capture, search, history, notifications, exports and the interaction layer. Existing money calculations, revision protections, financial records, planning and household-sharing foundations are candidates for reuse. The complete space model and business permission system are not already implemented. Business adds customers and suppliers, fiscal documents, invoice/payment matching, business-specific approvals and accountant collaboration. Shared code reduces duplicate work; it does not remove the need to test those business-specific behaviors.
Keep privacy structural
A person invited to enter numbers for a business should not see the owner’s home finances. Household members should not inherit business access. We need authorization at the data and action level, with explicit switching between spaces, auditable changes, revocation and clear ownership when someone leaves. Recommendations must use only the information the current person is allowed to access.
Let the ecosystem grow from useful invitations
A business owner can invite an associate to help with records. That associate may later use a personal space. A consumer may later create a business space. These are plausible expansion paths within one product, not assumptions that everyone will convert between segments. Each product needs its own reason to be used and paid for.
What makes this defensible
Our proposed advantage is reliable completion of local financial workflows: accurate records, useful permissions, relevant integrations, clear exceptions and support that understands the customer’s context. AI can make these workflows easier to operate. The business should still be valuable if general-purpose assistants become much better.
How we execute both without losing focus
We have one platform and two delivery tracks. Consumer shipping remains the immediate priority. Business scoping can proceed in parallel, and business web does not need to wait for every consumer feature or a business App Store release.
Track
Immediate work
Evidence needed to advance
Consumer
Finish and verify the connected core journey; run a tiny TestFlight
Onboarding succeeds; records remain accurate; permission and stability checks pass
Business
Choose the first customer and workflow; test onboarding and fiscal integration requirements
A pilot customer can complete the workflow safely, with known support responsibilities
Shared platform
Define reusable space, identity and record boundaries
Consumer and business data stay isolated; changes do not break the shipping consumer flow
Proposed consumer acquisition sequence
Clear preview and early-access signup, followed by a small testing group, public consumer launch, continuous product feedback, referrals and measured acquisition experiments. Capture platform interest so Android demand is visible. The earlier Android learning checkpoint remains a planning consideration; no Android release date is committed here.
Proposed business acquisition sequence
Start with direct conversations and assisted pilots around the chosen workflow. Accountants and implementation partners are potential distribution relationships to validate. A founder-led local effort may help with trust and onboarding; travel, staffing and partnerships have not been booked or signed. Demonstrate a completed customer job, document where support was needed, then improve the repeatable onboarding process.
Measure the outcome rather than activity
Consumer: time to first useful record or plan, repeat use, household participation, trial-to-paid conversion, support load and variable cost per active user
Business: time to first completed workflow, document acceptance and exception rates, reconciliation accuracy, customer time saved, repeat monthly use and support cost
Platform: failures across spaces, permission defects, recovery time and cost of shared services
These are proposed measures, not agreed numerical targets. Set thresholds with the team after the first baseline. Customer willingness to pay, retention and contribution margin remain hypotheses until measured.
Protect a real allocation of effort
Assign a launch owner and a business-discovery owner, even if one person initially holds both roles. Limit work in progress. Business discoveries should change the shared foundation when necessary, but optional business scope should not continuously reopen the consumer release. Public launch also needs ongoing engineering and support capacity.
Research decisions and launch boundaries
Electronic invoicing creates a specific opening
DGII Notice 06-26 grants small, micro and unclassified taxpayers covered by the notice six additional months from 15 May 2026, implying 15 November 2026. This is a specific taxpayer-group deadline, not one date for every Dominican business. We should verify each pilot customer’s classification and current status before making a compliance promise. [1]
Own the direct DGII integration
DGII’s published response to JeFact supports customers using software from a provider that is not yet certified as a PSFE. Customers still follow their own electronic-issuer route, and DGII allowed shared service URLs in that example. Our chosen direction is to build Cuadrao’s own DGII backend and expose authorized operations through our MCP interface. The response supports the direct-integration route; it does not by itself settle our foreign-company structure, signing arrangements or every customer’s eligibility. The response was verified on 3 October 2026. [2]
An MCP server is an interface through which an AI client requests operations. It does not itself provide issuer authorization, digital signatures, invoice correctness, secure key custody or regulatory approval. Those responsibilities belong in the underlying service and its onboarding and control processes.
The launch gate is the actual operating arrangement
Before live issuance, establish the customer’s issuer authorization and certification route, signing authority, certificate control, supported document flows, error handling and record retention. The foreign-company question has been submitted to DGII; our company-registration and operating assumptions should remain explicit until we receive a substantive answer or qualified local advice. [3]
Do not assume that encrypted custody of a customer’s signing certificate is automatically permitted. Customer-controlled signing or an appropriately authorized signing service must be assessed against the applicable requirements. A certified provider integration remains an optional fallback if it makes a safe pilot faster; no partner has been selected in this brief. DGII’s certificate-operating guidance is an input to this design. [6]
TestFlight and production have different commercial roles
TestFlight supports beta iteration; participation cannot be charged for, and its in-app purchases use the test environment without charging testers. A public consumer release can monetize under App Store rules. Business web has its own release path, but charging for access to a TestFlight beta is not a workaround. [5]
Build an independent implementation
Our delivery plan is an independent Cuadrao implementation. Any third-party code reuse requires a review of the applicable license and obligations for the exact files and version.
Keep the longer vision separate from launch claims
The broader Cuadrao direction still includes conventional, own-brand financial services and authorized money automation over time. Bank accounts, cards, investing and cross-border money movement depend on partners and approvals that have not been secured. Consumer and business administration can establish useful daily workflows while that longer path develops.
Business scoping decisions for today
The output of today’s session should be a small, testable business scope with named owners and evidence gates. The goal is to agree what we can deliver first and what must be true before a customer relies on it.
Choose the first customer
Select one initial segment and identify accessible pilot candidates. Record the current workaround, frequency of the problem, buyer and reason to switch.
Choose the first completed job
Select one workflow from intake to an auditable outcome. Define supported document types, payment scenarios, exception handling and what remains manual.
Define roles and approvals
Decide what owners, associates and accountants can view, enter, correct, approve and export. Keep household and personal permissions independent.
Choose the integration and signing route
Assign ownership for issuer onboarding, DGII testing, certificate handling, retries and fiscal status. Record unresolved foreign-provider questions and the fallback path.
Choose pilot channels and economics
Pick the minimum intake and support channels. Estimate AI, messaging, storage and human-support costs. Set a bounded commercial experiment without committing to an untested price.
Set separate release gates
Consumer advances on its verified mobile journey and beta results. Business advances on its own safe, complete pilot workflow. Agree who evaluates each gate.
Sources and implementation reference
[1] DGII Notice 06 26 — taxpayer deadline extension
[2] DGII community — JeFact use by other taxpayers
[3] Our submitted question — foreign noncertified software provider
[4] Draft PR 813 and pinned mobile execution board
Mobile specification at PR 813 revision
[5] Apple TestFlight overview
Apple Developer Program License Agreement section 7 4
[6] DGII CA5198 — digital certificate operating models
```
