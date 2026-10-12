# Argus minimum viable ecosystem experience

**Status:** Founder-approved experience direction, recorded September 26, 2026.
**Latest reconciled founder locks:** October 4, 2026: consumer/business launch
boundary and no-conversion currency rule. Earlier experience locks remain within
that boundary; the [decision log](argus-decision-log.md) records their provenance.
**Audience:** Product, design, engineering, and collaborating agents.
**Decision source:** Founder conversation approving the ecosystem structure and asking to lock it into a document, including information ingestion.
**Purpose:** Define the smallest cohesive ecosystem, its surfaces, and the movement of information between them. This is an experience specification, not an implementation schedule or a claim of shipped capability.

## 1. The product decision

**Argus helps people understand where they stand, keep their money organized, and know what to do next.**

The initial audience is people living in the Dominican Republic. Cash, disconnected banks, documents, and manual records are normal starting conditions. Argus should remain useful under those conditions.

We are testing a minimum viable ecosystem, not restricting the product to one calculator or one narrow financial obligation. People can enter through different needs: understanding spending, organizing accounts, managing debt, saving toward something, or comparing financial alternatives. Their activity should improve the same financial picture.

The strongest recurring pain point is not yet established. This breadth is intentional: observe what people use, what brings them back, and which connected experiences deserve expansion or removal. Do not present the proposed differentiation as proven market demand.

The reinforcing experience is:

**Record → understand → plan → notice change → return and update.**

Not everyone must complete every step or use every surface. Each surface must be useful on its own and make the others more useful.

### Relationship to existing documents

Use [documentation authority](../DOCUMENTATION_AUTHORITY.md) for the reading order,
document ownership, historical pointers, and assigned-package reconciliation.

This document owns the founder-approved pivot experience described here. Argus is
an agent-first financial ecosystem: conversation is the intended primary way to
get things done across its surfaces. Simple manual controls remain a complete
alternative. The existing research/backtest-oriented chat is reusable
infrastructure, not the finished ecosystem conversational architecture.

Existing production documentation continues to describe current implementation and operational safeguards. This document does not assert that the pivot is implemented, silently rewrite release gates, authorize deployment, or establish an engineering sequence. Older chat-primary scope statements should not be used to erase this explicitly approved future experience. Implementation work must reconcile relevant contracts and product documentation explicitly.

Wave sequencing and engineering breakdown are deliberately outside this document, except for explicit founder sequencing decisions recorded below. The guest access boundary is locked below; the exact registration and return-to-action flow still needs its technical contract.

### Consumer and business launch boundary

The October 4 launch decision narrows the public consumer iPhone release to
personal and household spaces. It starts with an invite-only TestFlight, then a
public release. Earlier Business and Custom space sketches below remain future
experience references; they do not add entries to that public consumer build.

Business is a separate full web service. Its thin iPhone experience covers
capture, quick approvals and where money stands, and goes only to business
TestFlight testers. Consumer completion does not require the full business
workflow. The approved space-model work precedes consumer TestFlight; the exact
schema, roles and migration steps still require their assigned contracts.

The [October 4 decisions](argus-decision-log.md#october-4-2026-cuadrao-launch-shape)
record provider selections and delivery direction. Source catalogs labeled NOW
or LATER do not replace assigned scope or establish new release prerequisites.
The [execution manifest](argus-execution-board.md) owns delivery status.

### 1.1 Locked audience and experience emphasis

**Founder approval, September 26, 2026:** Following the social-research discussion, the founder explicitly approved the proposed niche and ecosystem emphasis with “Yes you got it lock it.” This section is the canonical decision; supporting research retains its provenance and does not own approved scope.

Design first for **Dominican adults juggling cash, bank accounts, and debt, who already try to organize their money but cannot confidently tell what remains after their commitments.** Income may arrive by quincena, commissions, remittances, or other variable sources. This is a design focus, not an eligibility rule or a requirement that everyone have every account type.

The experience promise is:

> Know what is already committed, what remains until your next income, and how your choices change that.

Lock these refinements into the ecosystem:

- **Home connects recorded position with the upcoming financial period.** The populated view leads with recorded net worth, followed by near-term commitments and a clearly separate cash projection. Distinguish received versus expected income, show the period and included accounts, and retain asset/debt detail.
- **Budgets, debt payments, and goals share the same financial picture.** They must not independently allocate the same money. Match completed activity against its planned commitment rather than subtracting both.
- **Each confirmed entry reduces future effort.** Reuse relevant confirmed context, match later imports, preserve corrections, and make returning easier than reconstructing the picture elsewhere.
- **Tracking and decisions reinforce each other.** Existing Argus calculations and explanations use the recorded context to explore consequences; hypothetical scenarios never silently become actual financial activity.
- **Preserve ecosystem breadth and open chat.** Market questions, investing, and historical comparisons remain accessible without a debt-repayment gate or prescribed life-stage sequence.
- **Support personal and household finances together.** A person can invite their partner and combine shared accounts, responsibilities, and plans while retaining individual accounts. Household collaboration is part of the minimum ecosystem; section 12 owns its experience and sharing boundaries.

An account balance is not the same as money remaining after commitments. Show the estimate's period, included obligations, source freshness, currency, and assumptions. Expected income does not increase the current actual balance. Timing matters: a positive end-of-period estimate must not hide a shortfall before an earlier bill is due. When information is missing, make that visible instead of presenting an unconditional “safe to spend” number.

Approval locks the product direction, not a claim that demand or retention has already been proven. Learn which uncertainties users resolve, which inputs are burdensome, and which real decisions bring them back.

### 1.2 Private iPhone delivery: the immediate finish line

**Founder-locked September 28, 2026.** Deliver the agreed financial ecosystem on
the founder's physical iPhone, using the existing user account and real, durable
data over the internet. It must work away from the development computer. The
founder must be able to hand the phone to someone and demonstrate working
journeys. Simulator screens, sample figures, isolated API tests and merged
components do not establish this outcome.

For this September 28 private-device checkpoint, public App Store publication is
not required. The later [consumer launch boundary](#consumer-and-business-launch-boundary)
adds TestFlight and public release after that checkpoint. Select and verify an appropriate
signed private installation route. Real data means deliberately entered or
authorized data; it does not authorize copying production data into tests.

The ecosystem conversational-runtime redesign remains deferred for this first
private delivery. Preserve and connect the existing supported Argus capabilities;
do not imply that the old chat can perform the new financial actions. Full
agent-first MVEE completion additionally requires the conversational actions and
voice paths described below. This named exception must remain visible: the
private iPhone milestone is not permission to quietly drop other financial,
household, ingestion or planning requirements.

Voice dictation, transcription and spoken conversation remain approved scope.
Their financial-action interpretation shares the deferred runtime dependency;
audio capture or playback alone must not be reported as complete voice actions.

### 1.3 Complete scope checklist

This is the scope index for delivery planning. The linked sections own detailed
behavior; do not maintain another competing feature definition or use this table
as a claim of implementation. A package must identify what it completes and what
remains outstanding. Explicit later/experimental items stay distinguished below.

| Area | Required coverage | Detailed owner |
| --- | --- | --- |
| Access | Existing identity; sign-in, registration, confirmation/resend, recovery/reset, secure session refresh and relaunch, logout/account switching, browser-to-app transitions, guest chat and registration with return to action | [Guest boundary](#guest-access-and-registration); existing API/auth contracts |
| iPhone experience | Home, Accounts, Argus, Plan, Search, Updates and Profile; native navigation; English/es-419; persistent themes; accessibility, keyboard and physical-device acceptance | [Platforms and navigation](#2-product-character-and-platforms) |
| Accounts and assets | Cash, checking, savings, investments, cards/debts, optional vehicles/property/other assets; known/zero/unknown; nickname/date/institution; relevant debt terms; estimates, ownership shares and linked debt; create/reopen/edit/archive/restore | [Accounts](#accounts-organize-the-financial-facts) |
| Activity | Expense, income, transfer, payment and refund; categories/notes; corrections, removal/undo/recovery, history and consistent linked movements | [Activity](#account-activity-and-balance-checks); [refunds](#refunds-corrections-and-adjustments) |
| Reconciliation | Recorded versus observed balance; explicit gaps/adjustments; missing and earlier activity; per-account inclusion review; statement overlap; no invented activity or duplicate money | [Balance checks](#account-activity-and-balance-checks); [trust requirements](#5-shared-ingestion-and-trust-requirements) |
| Home | Assets/debts/net worth by currency, cash/debt breakdown, freshness/unknowns, recent activity, upcoming commitments, expected versus received income, cash forecast, shortfalls, Record and resume review | [Home](#home-understand-where-i-stand) |
| Plan | Budgets, savings goals, debt plans, recurring/occasional obligations and variable income; funding/dates; actual versus projected progress; shared allocation and matching actual entries to commitments | [Plan](#plan-decide-what-i-want-to-change) |
| Spaces | Public consumer uses Personal and Household; Business and Custom sketches remain outside that launch boundary. Broader space behavior includes create/rename/archive/restore, constrained deletion/recovery, account moves with history and linked-record review | [Spaces](#financial-spaces); [account moves](#reassigning-accounts-between-spaces) |
| Household | Share-link, code and QR invitations under section 12, acceptance/expiry/revocation, separate identities, explicit sharing/editing rights, joint records, private contributions, shared plans, leave/remove semantics and no indirect disclosure | [Household](#12-household-collaboration-approved-minimum-capacity) |
| Intake | Manual, text, voice, supported PDFs/structured files/images, photos/scans/screenshots; editable drafts, source preview, destination/currency/date review, uncertainty/duplicates, batch confirmation, resume and manual fallback | [Ingestion](#4-information-ingestion-one-destination-several-entry-methods) |
| Argus | Inherit finance explanations, research, calculations, simulations, comparisons and evidence; permitted personal/shared context; confirmed record/plan actions through shared services; distinguish hypothetical and actual | [Argus](#argus-ask-understand-and-get-things-done); [runtime sequence](#agentic-ecosystem-direction-and-sequence) |
| Voice | xAI direction; dictation/transcription, spoken replies, interruption/cancellation, editable interpretation, text handoff, confirmation, permission/consent/retention and latency/cost acceptance | [Voice](#43-speak-to-argus); architecture's provider contract |
| Search and continuity | Accounts, activity, plans/goals, documents, conversations, saved answers/analyses; real previews, origin-preserving return, recents/drafts, archive/recovery and defined Temporary chat | [Search](#search-find-what-i-already-know); [chat recovery](#temporary-chat-and-conversation-recovery) |
| Updates | Persistent inbox, deadlines/thresholds/milestones, scheduled summaries, review/freshness needs and relevant changed conditions; explanation, action link, preferences and private notification previews | [Updates](#updates-tell-me-when-something-deserves-attention) |
| Profile and control | Personal details/avatar/photo; App/Account/Support grouping; language/themes, response preferences, controlled personalization, security/sessions, usage, help, export/deletion/recovery and retention | [Profile](#profile-control-argus); existing product availability |
| Charts | Useful polished financial summaries, scrubbing, dates/units/currency, gaps/unknowns, themes/accessibility and physical-device performance; render canonical facts | [Design quality](#native-quality-and-tester-feedback); architecture's chart direction |
| Operational delivery | Signed physical-phone build, reachable authenticated API, configured integrations, migrations, durable storage, backups/restoration, monitoring, safe updates/rollback and real-account acceptance | [Infrastructure](#14-infrastructure-and-cost-constraints); [acceptance](#15-connected-acceptance-and-delivery-discipline) |

Fixed category identities and localized default labels must preserve reporting
when renamed; approved Business/Custom labels must not create a competing
financial taxonomy. Detailed category/API contracts remain implementation work.
Supported investment holdings are a later extension of recorded investment value,
not a reason to postpone basic investment accounts.

### 1.4 Infrastructure and cost constraints

**Founder-locked:** reuse Render and the existing Supabase project on the current
plan. A second Supabase project or paid upgrade is not a prerequisite. Preserve
the existing user identity, chats, profiles, research and backtests; add financial
tables with explicit authorization and appropriate access policies. Separate
tables do not isolate shared authentication settings, database resources or
migration effects. Use additive compatible migrations and validate existing
behavior, backups and restoration before hosted changes.

Retain a modular monolith with clear domain owners and shared services for manual
and future conversational actions. Native clients call the authenticated API
over HTTPS; the web frontend is not their required intermediary. Reuse current
background execution and add separate compute only for demonstrated workloads,
not one server per product pillar. Do not create separate financial ledgers or
chat brains per client. Measure actual capacity before proposing spending;
upgrades and hosted changes need explicit authorization.

Preserve the existing production Argus web app and its useful services. New
capabilities require deliberate rollout/configuration. Whether the private build
uses a separate Render deployment or the compatible existing API deployment
requires a bounded deployment decision; sharing Supabase is settled and must not
be reopened as an automatic second-project requirement.

Production delivery includes secure secrets, HTTPS, verified authentication
links, required jobs and selected email/document/voice/notification integrations.
Physical-device identity, signing and installation must be addressed early,
alongside a reachable backend, rather than discovered after feature development.
No provider secret belongs in the client, chat transcript or repository.

### 1.5 Connected acceptance and delivery discipline

The following must work on the physical iPhone over the internet with durable
records, including relaunch, failed requests and authorized household variants:

1. Record everyday activity; Accounts, budget, Home and relevant Updates agree.
2. Import a supported statement; preview the source, resolve uncertainty and
   duplicates, confirm, inspect the resulting records and resume interrupted work.
3. Explore a financial choice using inherited Argus capabilities; save the chosen
   plan manually during the runtime deferral, record progress and revisit it.
4. Open a meaningful update, inspect its source and make a supported correction
   or action; dependent views reflect it.
5. Invite a partner and perform shared journeys while private information stays
   private and shared money is counted once.

After the deferred runtime is implemented, repeat supported actions through text
and voice using the same service contracts and confirmation boundaries. Do not
waive that eventual parity or pretend it was proven by manual acceptance.

One integrated iPhone build is the product under construction. Parallel work
packages serve complete user outcomes against accepted shared contracts, with
one owner per domain/branch and explicit dependencies. Integrate frequently and
inspect actual journeys early. Keep necessary engineering breakdown underneath
the product view; report demonstrated capabilities, gaps and blockers rather
than agent counts, screenshots or passing component tests as product completion.

Use one maintained execution plan derived from this MVEE, including verified
reuse/missing-work inventory, dependency map, owners, decisions and acceptance.
Avoid fragmented documentation PRs, duplicate proof implementations, indefinite
review loops and environments created without actionable assignments. Existing
review proportionality and release gates remain applicable. No timeline or
flawless-delivery promise is established here.

**Stop remains in force:** this publication records the founder's requirements.
It does not resume stopped agents, implementation, providers, deployments,
migrations, paid services or the previously paused execution goal. A restart
requires explicit founder instruction.

### 1.6 Holds, later work and unresolved decisions

- **Web remake:** frozen. Spend no resources on its implementation or polish now.
  Preserve the polished existing web as the reuse/design reference. A later
  marketing/download page may coexist with it; replacing web with a landing page
  is not decided and is not required for private iPhone delivery.
- **Android:** remains an intended native product; its next delivery assignment
  follows explicit prioritization and must not displace the immediate iPhone
  outcome. Existing work is preserved.
- **Agentic runtime:** deferred as described above; shared financial services
  must support its later inheritance without duplicating rules.
- **Plaid sandbox:** available as a future ingestion/core-loop development aid;
  credential validation is not a working bank connection. It must feed the same
  recording/review flow, not revive a competing connector proof or ledger.
- **Conditional integrations:** Dominican bank access, browser-assisted access,
  wallet-triggered capture, automated listing valuations and financial-product
  discovery remain exploratory. Licensed access, valuation validity and actual
  coverage need evidence. They are not prerequisites for a useful private build.
- **Watchlist:** its saved-symbol purpose, freshness, sourcing and possible
  research-to-backtest handoff remain queued product/technical questions.
- **Monetization:** preserve the original monetization/flywheel rationale as
  future input; do not allocate free/paid features prematurely. RevenueCat mobile
  and Lemon Squeezy web remain candidates to evaluate, not current delivery work.
- **Analytics and sharing:** preserve existing operational telemetry. New
  ecosystem PostHog work follows proven core loops. Growth sharing remains parked
  until actual user sharing preferences are understood; it is distinct from
  required household collaboration.
- **Decisions still needed:** supported initial formats/OCR provider; upload
  limit, encrypted-file handling and file/audio retention; household editing,
  departure and recovery details; notification channels/scheduling; Temporary
  chat/context and memory handling; app identity/distribution and hosted rollout.
  Ask when the named contract actually needs the decision, not as blanket setup.

### 1.7 Founder delivery concerns

The founder explicitly identified months lost building disconnected pieces,
repeatedly incomplete scope inventories, excessive web allocation, unnecessary
infrastructure cost, idle environments, fragmented lanes and PR ceremony, and
design quality requiring repeated personal intervention. These concerns are
delivery constraints, not new product modules. Foundations must converge on a
usable assembled experience; the founder must not have to reconstruct product
status from agent reports. Maintain honest completion claims and the complete
scope above when producing assignments or status reports.

## 2. Product character and platforms

- Retain the current Argus visual identity and typography. The founder rejected replacing it with a new visual identity.
- Feel elegant, modern, crisp, calm, and trustworthy: a personal financial control room with the reassurance of a citadel.
- Optimize for a phone and natural, one-handed flows. Avoid shrinking a desktop dashboard onto mobile.
- Native iOS and Android apps are the intended mobile products, not PWA shells. Web remains a useful product surface. The [interface stacks are founder-locked](../ARCHITECTURE.md#approved-platform-direction); detailed client contracts and delivery sequencing remain separate decisions.
- Use progressive disclosure: clear summaries first, details when requested. Avoid walls of charts, dense tables, decorative widgets, and unnecessary setup.
- Preserve Spanish and English support, with the Dominican audience informing language and examples.
- Apply the [currency rule](#currency-rule) to every financial summary and input path.

### Currency rule

Founder-locked October 4, 2026. Cuadrao never converts currencies or shows a
blended total. Every account retains its own currency. Home shows a separate
total for each currency, with the person's primary currency first. They choose
that preference at onboarding and can change it later.

Charts and comparisons show one currency at a time, with a switcher when needed.
Plans keep a fixed currency. For a payment from an account in another currency,
the person records both amounts exactly as their bank charged them. Cuadrao does
not supply an exchange rate. The founder's design lane owns the final screens;
this rule does not assert the posting contract is implemented.

### Navigation

Primary navigation: **Home · Accounts · Argus · Plan · Search**.

Use a refined floating glass treatment on mobile, simple recognizable icons, and the Argus logo for the central chat destination. Visible labels need not sit beside every icon, but controls require accessible names and a clear selected state. Adapt the glass treatment to platform capabilities; a web approximation is not proof of native system behavior.

The bar may compact or recede while scrolling and return when needed. Movement must not make navigation difficult to recover, obscure input, or ignore reduced-motion settings.

Updates and profile live in the header outside the primary bar on financial surfaces. Chat uses its dedicated conversation controls described below. Profile opens app/account settings; Home owns the personal financial overview. Keep the chat header restrained: no redundant “Ask Argus” title or duplicate top-left branding over the branded cold start. Home may retain the wordmark; other surfaces use clear destination titles.

### Native quality and tester feedback

Founder-reported tester feedback: the pivot is too wordy, lacks useful transaction
icons/charts, loses Search context when opening chat, does not preview a selected
file, and sends Back to unrelated nested Settings. These are acceptance failures
to address, not polish that can remain indefinitely behind “foundation” work.

Use concise labels, recognizable activity icons and meaningful visual summaries;
put extended explanation on demand. Preserve the locked Argus identity and calm
progressive disclosure. Charts need canonical data, honest gaps, touch scrubbing,
scroll compatibility, correct dates/units, accessible alternatives and measured
device performance. A visually attractive fixture is not connected chart proof.

Evaluate native document scanning, file/photo selection, actual document/image
previews, share-to-Argus intake and suitable on-device preprocessing as parts of
the assigned journeys. Evaluate local type/size/readability checks and ML for
unwanted or irrelevant content before upload; this is not a selected classifier
or a guarantee that all unwanted material can be blocked. Provide understandable
rejection/correction paths and minimize unnecessary uploads. Server validation
and authorization remain authoritative. Include device permissions, accessibility,
keyboard/safe areas and network interruptions in physical-iPhone acceptance.

## 3. Minimum useful capacity of each surface

### Home: understand where I stand

Home answers:

1. What do I have and owe?
2. What changed?
3. What needs my attention?

Minimum capacity:

- A clear summary of recorded assets and debts, separated by currency.
- Recent meaningful activity: spending, income, payments, and progress.
- Relevant next actions: a payment approaching, a budget nearing its limit, or an account needing an update.
- A readily available Record action.
- Resume unfinished work, such as reviewing a statement import.
- Open the account, transaction, plan, or explanation behind a summary.

Use a simple vertical mobile flow. Do not turn Home into a generic market-news feed or a collection of charts. Incomplete information should still be useful: say “Based on your recorded accounts” and show freshness instead of suggesting comprehensive live coverage.

#### Populated Home summary and list boundary

Founder-locked September 27, 2026. The populated sketch leads with recorded net
worth, a quiet source note and cash/debt breakdown. Remove promotional headings
and repeated coverage explanations. Show missing balances and estimate provenance
when relevant. Keep a short account preview with View all leading to Accounts;
[DESIGN growing lists](../../.agent/designs/argus/DESIGN.md#growing-lists-across-ecosystem-surfaces)
owns the row limits and inherited disclosure/loading interaction.

Net worth follows the [currency rule](#currency-rule). The October 4 lock
supersedes the sketch's earlier optional combined view.
Below the recorded summary, Coming up shows those dated expectations and
projected cash within Home's rolling next-30-days window, read from the same
projection service as Plan (see [Recurring setup, Upcoming and useful
scenarios](#recurring-setup-upcoming-and-useful-scenarios)), with View plan as
its destination. Do not present that estimate as net worth or guaranteed spendable
money. Without expectations, invite the person to add their next income or bill;
do not assume future expenses are zero.

### Accounts: organize the financial facts

Minimum account types include cash, checking, savings, investments, credit cards, and other debts. Cash is first-class.

Minimum capacity:

- Create an account manually or populate supported fields from a document.
- Inspect balance, currency, activity, source, and last-updated date.
- Record spending, income, transfers, payments, and balance corrections.
- Edit transactions and categories; correct or undo mistakes.
- Reconcile a recorded balance against a statement or the user's observed balance.
- Track investments initially through recorded balances or holdings without requiring a portfolio terminal.
- Distinguish individual and joint accounts, with explicit household visibility. One joint account can appear in both personal and household contexts without becoming two accounts or being counted twice.

Transfers between owned accounts are not spending. A credit-card payment must not count purchases twice. A cash withdrawal is a transfer to cash when that is what happened; later cash purchases are expenses. Changes to a balance must not silently manufacture income or spending.

#### Account activity and balance checks

Founder-approved September 27, 2026. Adding an account with an opening balance
completes setup; it does not require a second income/expense entry. Account
details editing, recording new activity, inspecting an existing activity row,
and checking a balance are distinct actions. Keep their labels stable; do not
turn a completed account into a misleading “Resume entry” task.

“Record new activity” creates a new transaction. Opening an activity row inspects
or corrects an existing transaction. Income/Expense/Transfer is the activity type;
source (salary, remittance, interest, other income) or spending category is optional
additional detail, not another selection of the same type. Transfers do not need
an income source or spending category.

“Check balance” compares the user's observed amount with recorded information
before confirmation. Show the prior recorded amount, observed amount, currency,
check date and difference. If they differ, offer recording missing activity or
saving an explicitly labeled balance adjustment. Preserve the discrepancy in
history; never silently replace the amount or classify unexplained differences
as income/spending. A matching balance needs no nonzero adjustment. An unknown
prior balance cannot produce a calculated difference. Asset estimate changes
remain value updates, not unexplained cash transactions.

A confirmed adjustment can establish a known balance while transaction coverage
remains incomplete. Keep that distinction visible in account history and affected
summaries. Later imports, missing activity, corrections and removals must reconcile
against the check without double-counting. The production design obligations and
unresolved technical choices are recorded in the
[backend reconciliation handoff](argus-account-balance-reconciliation-handoff.md).
This locks behavior, not a schema, API or posting model.

Removal names the affected record, explains effects on linked accounts and uses
the shared destructive confirmation treatment in
[DESIGN.md](../../.agent/designs/argus/DESIGN.md#destructive-confirmations).
Recovery language must match actual capability: the disposable sketch supports
immediate Undo and session-only restoration through Data & privacy → Removed
financial entries. List the original space and account, preview balance effects,
and restore the original record rather than creating a copy. Transfers/payments
return together. Production retention, authorization and recovery periods remain
open; no conversation-deletion policy is silently inherited.

#### Archiving accounts

Account archiving in the final September 28 mobile baseline is organizational:
allow a nonzero or unknown balance, retain its balance/history and existing
obligations in the financial picture, and make restoration available from Manage
accounts. It removes the account from the ordinary active list, not from money
totals. Do not manufacture an outflow or silently reduce debt by archiving.
Removing an empty account is a separate reviewed action; this does not authorize
deleting accounts with history or changing permissions.

#### Refunds, corrections and adjustments

September 28 UI refinement: a refund records money actually returned to cash,
a bank account or a credit card. It is distinct from income and reduces spending
in the month received. A card refund reduces debt and may leave credit in the
person's favor. Show that credit explicitly. Partial refunds can reference the
original purchase; linked refunds cannot exceed it. Keep the purchase and refund
as separate records with a shared category. Refunding to another account must
identify the actual destination. Never assume an exchange rate for a foreign-
currency return; use the actual received amount and mark an unlinked purchase.

When the original purchase is absent, allow an explicitly unlinked refund with
an optional category. Do not fabricate a purchase or retroactively rewrite old
months. Correcting an erroneous entry is a separate action from money returned.
A balance adjustment or property-value change changes position, not spending or
income. Loan principal/interest reversals need a breakdown; do not treat them as
ordinary purchase refunds. An unexplained loan difference uses Check balance.

Activity dated on or before a previously recorded balance check needs a clear
account-level question: was it already included in that checked balance? If yes,
record its activity without applying the same balance movement again. If no,
show the resulting balance change. Paired movements may need an answer for each
account. This UI choice does not resolve source matching, adjustment lineage or
concurrent corrections in production; those obligations remain in the backend
handoff. Preserve the optional 200-character note across every financial activity
form, including refunds and balance checks.

#### Financial spaces

The [consumer launch boundary](#consumer-and-business-launch-boundary) governs
availability. The following September 28 sketch describes the broader experience.

Founder-approved sketch boundary: Personal is the default. Add a space offers
Household, a named private Business space, and Custom for another named private
financial picture (September 28 template refinement requested by the founder).
Custom reuses the private account/activity/plan flow; it is not a new permission
type. Personal remains the single permanent default. Business reuses manual accounts,
activity and plans, with optional user-entered categories. It does not imply
employees, payroll, invoicing or tax accounting. Retirement remains an account
or goal within an appropriate space, not a mandatory new space.

Use the quiet horizontal space selector on Home, Accounts and Plan. A space is
not an account type or category. Household projects only explicitly shared
records; it must not silently combine private Business or Personal information.
Global search can find authorized records across spaces and must identify the
record's space. Space ownership and authorization still need production contracts.

#### Managing private spaces

The September 28 disposable UI refinement closes creation and recovery together:
`+` offers Household, Business and Custom, with Manage spaces below. The final
mobile lock removes duplicate space and household management entries from
Profile & settings; use the existing space and Manage household controls.
Private spaces can be renamed. Their names
must be distinct, including archived and recoverable deleted spaces.

Archive removes a private space from ordinary space navigation, retaining its
accounts, balances, activity, corrections, notes, plans and recovery records.
Search still finds these records with an Archived space label. Opening an
archived space identifies its status; archiving is organization, not a read-only
financial freeze, a cancellation of commitments, or a change in permissions.
Restore brings it back to the space selector. Leaving or archiving the active
private space returns to Personal, without moving records or money.

Delete is available only for an empty private space: no accounts (including
archived accounts), activity, plans, expected items, entry drafts or recoverable
removed accounts. Use the existing destructive confirmation, Undo, and Recently
deleted within Manage spaces. Never cascade-delete financial records from this
control or encourage deleting history to make the space eligible. Personal
cannot be archived, renamed or deleted. Household retains its separate membership
and sharing flow; deleting a private space cannot revoke a partner's access.

The sketch permits multiple named private spaces but does not establish an
unlimited production entitlement. Production limits, retention/purge policy,
concurrent deletion checks and lifecycle authorization remain technical/product
contracts to settle before implementation. No employee, payroll, tax, nested-space
or bulk migration capability is introduced by Custom.

#### Reassigning accounts between spaces

Founder-approved UI refinement, September 28, 2026. Manage account offers
**Move to another space** between Personal, private Business and Custom spaces, and
**Share with household** separately for personal accounts. Household sharing
changes visibility/access, not the account's owner or private-space assignment.

Moving first names the source and destination. Keep balance, opening position,
full activity/correction history, notes and recoverable removed entries together,
with original record identity. A move creates no transaction, income or expense.
Explain which space budgets stop/start including the account's matching activity;
the budgets and goals themselves remain where they are. Open the moved account
in its destination and identify that space. Moving it back uses the same review.

Before confirmation, identify links to transfers/payments, cross-account refunds,
asset loans, household sharing, forecasts, debt plans, documents and unfinished
entries. Never break these links or suggest deleting valid history to make a move
possible. The disposable sketch moves standalone accounts and explains why a
linked account is blocked; group moves and permission-aware link migration need
the production contract. Creating a destination is explicit and does not itself
move the account. Cancelling a move leaves its account and activity in place.

#### Quick account setup and optional assets

Founder-approved September 27, 2026. Keep a short, single-screen setup with
progressive details, not a required wizard. Once chosen, the type picker folds
into a compact row with a Change action. Let users choose an account type,
confirm its currency, optionally give it a nickname, and enter a balance or
leave it unknown. A missing value is not zero. A nickname changes the display
name, not the underlying account identity or institution.

Initial creation contains only type, nickname, currency, and balance or estimated
value. Move the optional details below into the saved item's editing surface;
do not show a More details questionnaire during initial creation. Keep unknown
values supported so completing the financial picture is not a prerequisite.

For assets, show a compact ownership summary beside this simple entry:
“You own all of it · Change.” Change reveals “All of it,” “Half,” or “Another
share”; only the last choice asks for a percentage. Reflect the selected share
in plain language and calculate its contribution automatically. This remains
one item, without inviting a partner or configuring sharing during creation.

Use the same entry pattern with fields that fit the item:

| Item | Starting value | Optional details, disclosed when relevant |
| --- | --- | --- |
| Cash, checking, savings | Recorded balance or unknown | Balance date; institution for bank accounts |
| Investments | Recorded value or unknown | Institution, date, supported holdings later |
| Credit card | Amount owed or unknown | Credit limit, payment due date, interest rate |
| Other debt | Amount owed or unknown | Lender, payment dates, rate and repayment details |
| Property, vehicle, other asset | Estimated whole-asset value or unknown | Estimate date and basis, ownership share, related debt |

Offer property, vehicles and other assets through a secondary entry alongside
accounts. They are optional parts of the financial picture, not prerequisites
for getting started. Users can record an item before knowing its value and
update the estimate later. Cash remains the easiest first item to add.

Asset estimates must remain visibly distinct from cash and bank balances.
Home can include them in a clearly labeled recorded net-worth picture, separated
by currency, but must not present them as spendable money. Unknown values make
that picture incomplete rather than silently contributing zero. Show the
estimate's date and basis; changing an estimate does not create income or an
expense.

Record the full asset value and the user's ownership share explicitly. Count
only the relevant share in a personal view. Household aggregation must use the
same underlying asset and ownership records, so inviting a partner cannot
create a second copy of the property. Ownership and permission to view are
separate facts; adding an asset does not grant household access.

A mortgage or vehicle loan is a separate debt that can be linked to the asset.
Linking organizes the picture; it does not add another debt or subtract the
same liability a second time. Do not require an asset's estimated value to add
its related debt.

**Future valuation assistance:** investigate Dominican listing sources such as
[SuperCarros](https://www.supercarros.com/) for vehicles and
[SuperCasas](https://www.supercasas.com/) for residential property. Published
asking prices are comparison evidence, not verified sale prices or an appraisal.
Any later estimate should expose its comparable listings, date, currency,
relevant differences and uncertainty, then let the user accept or adjust it.
Manual estimates remain available. Automated collection, source access and
reuse terms, valuation methodology, coverage and refresh behavior still need
technical validation; these sites are candidates, not committed integrations.
This decision authorizes the experience and disposable sketch, not production
scrapers or a new financial-record contract.

### Argus: ask, understand, and get things done

Preserve the existing chat experience: time-aware greetings, typed hero animation, starter chips, composer, conversational continuity, grounded calculations, research, historical simulations, comparisons, result explanations, and retrieval. Do not add a persistent blinking cursor to the completed hero text.

Minimum capacity:

- Ask general finance and market questions without first recording personal finances.
- Ask about recorded accounts, activity, and plans when available and permitted.
- Describe financial activity and review a proposed record.
- Speak activity or questions, then review the interpreted content.
- Upload a supported file, statement, scan, or image for review.
- Create or adjust a plan through a confirmed action.
- Compare investments with alternatives such as savings or certificates of deposit using supported calculations and sourced assumptions.

Conversational answers and financial writes are distinct. Asking “What if I spent RD$5,000?” must not record an expense. New proposed financial records require confirmation. The assistant can help across the app; it is not necessary to visit chat for every edit.

#### Guest access and registration

Founder-locked September 28, 2026: guests can see the app and use the existing
Argus finance chat under its current capability, quota and usage rules. Using
any other ecosystem feature requires a registered account. Seeing a surface
does not grant permission to use it. Creating a financial account, recording
activity, importing documents, managing plans or participating in a household
must lead to sign-up or sign-in before the operation. The same boundary applies
on iPhone, Android and web, and to actions requested through chat. No durable
guest financial records are authorized on the server. Existing guest-chat behavior
and limits are preserved; this decision does not expand guest compute or research
access. The iPhone's on-device guest book ([October 9 entry](argus-decision-log.md#october-9-2026-iphone-on-device-guest-book-probar-sin-cuenta))
keeps its data on the device only and amends this boundary for that case alone.

Registration is the gate, not payment. The exact registration/return-to-action
journey and server enforcement need implementation contracts. This publication
does not claim that the gate is implemented or change current auth endpoints.

#### Agentic ecosystem direction and sequence

Founder-locked September 28, 2026: text and voice are the intended primary
interface for every supported app workflow. Manual controls are the secondary,
extremely simple alternative and must remain complete and usable. Both entry
points use the same canonical actions, financial
rules, permission checks and confirmation boundaries. Research, calculations
and historical simulations remain capabilities within this broader assistant.

The founder cited Meta Muse as a goal-to-action experience reference, not a
provider selection or authorization to copy its architecture. Re-architect by
inheriting useful Argus services, artifacts and safeguards. The current
research/backtest-oriented chat alone does not satisfy this agentic direction.

The ecosystem conversational-runtime work is deferred until the core workflows
and their UI are defined. Build the manual workflows and their shared service
contracts first, then assign the chat action integration and runtime evolution
as a separate lane. Preserve the existing single conversational runtime until
that lane explicitly changes its architecture; do not create a parallel chat
brain or modify model-facing prompts as part of the mobile foundation. Existing
chat maintenance and security fixes continue independently.

#### Continuous Cuadrao conversation

Founder decision, October 6, 2026: the consumer assistant is this agentic
assistant, and memory and voice are in release 1. The old Argus chat code stays
until the founder decides to remove it. See the
[decision log](argus-decision-log.md#october-6-2026-first-release-assistant-and-memory-and-voice-scope).

Founder direction, October 4, 2026. Cuadrao should support an ongoing conversation
that carries a person's work forward. The first runtime contract in
[#826](https://github.com/lagarcess/argus/issues/826) must define the following
behavior before implementation:

- Enter from chat or a plan, receipt or chart without losing the unfinished
  message or the route back to the originating screen. Context is visible and
  removable.
- Keep the active space clear. A space change does not grant access to earlier
  private context. Define which history, attachments and memory can be used or
  displayed, including after household membership or a grant is revoked.
- Reconnect to durable jobs after the person closes and reopens the app. Show
  their real status and results, with retry or cancellation appropriate to the
  underlying action. Changing chat context cannot retarget an in-flight job.
- Bind an approval to its specific action, revision, recipient and space. A
  later message or changed space must not silently approve stale work.
- Define consent, correction, forgetting and deletion for permitted memory.
  Preserve the Temporary chat boundary below. Record whether memory and voice
  are in the first release rather than assuming their presence.

An ongoing conversation is an experience direction. It does not require one
unbounded model transcript, one global permission context or a particular
thread/checkpoint schema. The reference apps inform interaction goals, not our
backend topology. The [reuse decisions](../ARCHITECTURE.md#cuadrao-reuse-decisions)
guide the implementation assessment.

#### Temporary chat and conversation recovery

Founder-locked mobile presentation, September 28, 2026: one Temporary chat mode replaces separate private/incognito names. Optional Use my context starts off; neither temporary variant creates new memories or enters chat history. Context choice locks after the first message. A nonempty session asks before discarding; returning can restore the prior regular draft. This is the experience target, not a shipped retention or anonymity guarantee. Context authorization, provider handling and retention need explicit technical contracts before implementation.

Recents distinguishes no chats, archived-only and no matching results. New chat from a search creates an unsent draft. Archive/restore and delete/recovery preserve the original identity. The More menu concerns the current chat; temporary entry is not duplicated there. DESIGN.md owns the stable header positions and motion.

### Plan: decide what I want to change

Minimum capacity:

- A spending budget.
- A savings goal.
- A debt-payment plan.

Each shows the same understandable structure: current position, intended outcome, planned contribution or limit, and progress. Users can create and edit these manually or through Argus.

Existing calculators supply useful scenarios. A savings calculation can become a goal; a payoff calculation can become a debt plan; an opportunity-cost comparison can inform a decision. Saving a scenario does not authorize any real-money action.

Projected progress and actual progress are separate. “If you save RD$3,000 monthly” is a projection. Recorded contributions establish what happened. Avoid counting the same contribution twice when it appears through multiple sources.

#### Connected plan status

A dated expectation may reference a budget; that budget's limit is not another
cash movement. Show Planned until an actual entry is explicitly recorded or
linked. Recording from an expectation names the account and actual date, previews
the amount, and creates one activity entry. Accounts and budget spending use it;
the forecast excludes that fulfilled occurrence. A refund changes recorded cash
and spending without automatically making the paid bill unpaid. Removing or
correcting the linked entry must re-evaluate the link rather than preserving a
false Completed label. Dates, included accounts and currency remain visible.

In the connected UI study, a debt or savings plan can name its funding account,
destination and next date. Overview derives those expected movements from the
plan; it does not keep another editable copy. Show why an unconfigured plan is
excluded. Transfers between included cash accounts remain visible but do not
reduce their combined cash. Use “Net cash change” for inflow minus outflow;
reserve a shortfall warning for a projected negative balance.

A linked contribution opens its original activity for correction or recovery.
When linking an existing contribution, clarify whether a manually recorded goal
total already includes it. Correcting the amount of an explicitly fulfilled
occurrence changes actual balances without creating a second expected payment;
a changed type or account requires review. Removal and restoration re-evaluate
the link. These are sketch behavior requirements, not production recurrence,
allocation, or reconciliation contracts.

#### Recurring setup, Upcoming and useful scenarios

Founder-approved October 4, 2026. Connect the existing recurring-expectation and
cash-projection owners to the designed Home and Plan experience.

- A movement can become a prefilled recurring expectation. Review the copied
  details, cadence and next date, then confirm. Preserve the original movement;
  future occurrences are expected payments or income, never actual money merely
  because their date arrives. Confirm or explicitly link the actual movement
  when paid or received, fulfilling the occurrence once.
- Home's Próximamente / Upcoming uses a rolling next-30-days view of confirmed
  dated commitments and expected income, including one-off items. Keep this Home
  horizon independent of a longer Plan exploration while using the same
  canonical projection service. Pending/overdue items retain truthful status;
  they are not fabricated paid entries or silently rescheduled.
- Make recurring entry useful first. Pattern detection then suggests a schedule
  after several consistent occurrences within the authorized account/currency
  scope, using sensible date and amount tolerances. Explain the evidence and let
  the person accept, adjust or dismiss. Do not silently turn a detected pattern
  into a commitment or overwrite a rejected suggestion.
- Plan distinguishes confirmed schedules, uncertain estimates and hypothetical
  changes. A dated what-if recalculates the same timeline and explains its impact
  on upcoming obligations and goals without saving a real transaction. Exclude
  already scheduled or fulfilled amounts from any variable-spending estimate.
- With sparse history, use an honest schedule-based projection and show missing
  coverage. A sample or linear fixture must not be presented as learned behavior.
  Evaluate the usefulness of the lookforward experience with users before a
  decision to expand or remove it.

The existing expectations, fulfillment and currency owners remain the starting
point. #822/#824 own connection work; #818/#826 bound scenario inclusion and
contracts. Statistical forecasting is a later evidence-based choice: compare
simple baselines and StatsForecast on chronological holdouts, including errors,
interval coverage and shortfall warnings. StatsForecast is a candidate, not a
selected dependency; Prophet, Chronos or paid forecasting do not become launch
requirements. Approved direction does not make all follow-on detection and
forecasting work a first-release blocker.

#### Category suggestions and useful corrections

Founder-approved October 4, 2026. One canonical category identity must feed model
validation, financial records, localized labels, icons/artwork and charts.
Reconcile the existing preview/backend taxonomy before connecting enrichment.

Preserve explicit user choices and accepted rules first. Reuse valid mapped
source categories; suggest a category through the existing model for unresolved
cases under the shared consent policy. Show suggestions as editable in receipt
or transaction review. Unknown or uncertain results can remain unclassified;
model-reported confidence is not a calibrated correctness probability. Financial
posting keeps its existing confirmation boundary.

Correcting one record is immediate through the canonical correction action.
Offer separate, explicit choices to update selected similar existing records or
remember a scoped rule for future ones. Bulk correction is not proof of future
learning. Preserve authorization, revision history and linked-refund rules, and
never silently overwrite a person's correction. Validate batch results against
stable record IDs rather than assuming model output order matches input order.

#822 owns category and correction contracts; #823 connects extracted suggestions;
#824 consumes the same category identities in Home and Search. Use existing
OpenRouter, Supabase and Render foundations. No separate categorization vendor
or vector index is required by this direction.

### Search: find what I already know

Minimum capacity is unified retrieval across transactions, accounts, plans, goals, conversations, saved answers, and prior analyses, with direct links to their owning surfaces.

Build on the existing Omnisearch and history experience. Finding “that certificate comparison” should recover useful prior thinking, not require remembering which screen created it.

Opening a result preserves its search origin: query, filters, results and scroll
position. Chat and document destinations provide an obvious return to that
context; Back must not route to unrelated Settings or require reconstructing the
search. A file result opens the actual authorized document/image preview with
related records and appropriate actions, not just a filename and Delete button.

Market-product discovery is an expansion direction: loans, cards, insurance, savings products, and other alternatives. It becomes useful when there is maintained, sourced inventory. Do not fill the minimum ecosystem with fictional offers or imply shopping/execution capabilities that do not exist.

### Updates: tell me when something deserves attention

The bell opens a persistent inbox. Minimum useful categories are budget thresholds, goal milestones, payment reminders, scheduled summaries, changed conditions relevant to saved answers/plans, and records needing review or refresh.

Every update should explain what changed, why it matters, and where to act. Delivery preferences belong in settings. Scheduled briefs should concern useful, selected context rather than become a generic daily feed.

Distinguish changes in user records from external market changes. Argus can observe what its sources provide; without fresh banking information it cannot claim to see every transaction. Investment-performance updates require an appropriate data source, time window, and comparison basis.

Notifications should invite a return without exposing financial amounts in push previews. Details belong inside the authenticated experience.

### Profile: control Argus

Own app preferences, notification preferences, security, data controls, export and the Argus login account. Keep this separate from Accounts and Home so “my profile” does not ambiguously mean “my finances.” Financial space organization and household invitations/membership remain at their existing space controls, without duplicate Settings entries.

The September 28 mobile lock keeps Personal details above three groups: App (Preferences, Personalization, Notifications), Account (Security, Data & privacy, Usage), and Support (Help & feedback). Language lives only in Preferences. Personal details offers an avatar theme or profile photo; response preferences remain distinct from remembered context and financial records. Light, Dark and System persist as appearance preferences.
With no avatar selection the Profile tab keeps its original icon; otherwise it
shows the same selected avatar that Profile reads.

For the October 2 native release pivot, identity uses initials and avatar themes.
Hide personal photos, Personalization, Security and sessions, Shared
conversations, Removed activity, Memory, Usage, More options and conversation
bulk actions until their connected native features are assigned. Design commit
`fc7650ea`, from Yelena's UI checklist, hides Personalization, Security and
sessions, Shared conversations, Removed activity and photos. Usage, More options
and conversation bulk actions are hidden by #786 (`a20362d3`) as a Head of
Engineering judgment call. Memory (`.memory`) is hidden until native memory
arrives with its controls. These are designed rows whose backend is still owed, not cuts, and Yelena is
ordering their backends after chat. `CuadraoFirstRelease` hides them only in
release builds and shows every row in development builds. Release builds hide
the avatar-editing entry and development builds keep the full editor, including
photos ([decision of October 3, 2026](argus-decision-log.md#october-3-2026-avatar-editing-in-release)). This does not remove them from
the September 28 grouping. Remove only the notification preference named Por
correo, because Updates go to the inbox and push only. This does not
remove email authentication or recovery. Household email invitations and update
email are not in this pass, per the [October 2 lane
locks](argus-decision-log.md#october-2-2026-cuadrao-lane-locks). Keep legal links
reachable while signed in and provide in-app account deletion. Native memory
off/reset and source Disconnect controls arrive with those features. Existing web
availability is unchanged.

### Native release access and account lifecycle, October 2

The founder's next UI assignment prioritizes external TestFlight readiness and
invites/Household. It supersedes conflicting native preview choices, not current
production web guest entry or technical contracts. New native users enter with an
invitation code, link or QR; people without access can reach the cuadrao.ai waitlist.
Existing admitted users retain sign-in/recovery. Sign-in for TestFlight is Apple,
Google and email ([October 2 founder
decision](argus-decision-log.md#sign-in-for-testflight)). Email works with any
address and has an in-app confirmation step; today's email sign-up instead ends on
a confirmation link. Apple and Google are built behind default-off flags until the
founder supplies the keys, and connected buttons stay hidden while a flag is off.
Design their full states.

Personal app invitations have a ten-invite quota. Household invitations are
administrator-only, do not consume that quota, and also admit a new person to the
beta. Only the founder creates a capped, expiring group access link. It is beta-only,
never grants household membership, and is distinct from a household or financial
plan invitation. Membership never automatically shares financial records. Under
the lane contract, group-link redemptions do not use anyone's personal quota.

The assigned account-deletion experience explains removal of the person's data,
retention of an anonymous invite record, administrator succession to the
longest-standing remaining member (the household closes if no one is left), and
removal of the household's locked copy of that owner's history. In plans other
people own, the person's amounts stay under a nameless "Exmiembro" / "Former member"
placeholder, open balances with them are frozen as a closed line, and shared plans
they created pass to the longest-standing participant. A shared debt plan they
created is instead archived read-only with a banner, because nobody can own another
person's debt account (the Head of Engineering's call, recorded in the [decision
log](argus-decision-log.md#deleting-an-account-in-a-household)). These follow the
October 2 locks; the wording is Iris's founder-locked copy in the
[lane handoff](lanes/mvee-five-lane-handoff.md#copy-founder-locked-iriss-wording).
Present only applicable consequences, then verification, confirmed completion and
sign-out. The deletion command and its web flow are on integration behind the
default-off `ARGUS_ACCOUNT_DELETION_ENABLED` (#799, #801); while it is off, the web
files the earlier support request instead, and no native flow is on integration.
Deletion locks the account (signed out, every route but deletion refuses it)
until every outside service has confirmed, and only then deletes the
login. A deletion still waiting finishes when the person retries or an operator
runs the sweep. Nothing runs that sweep on a schedule: that is the founder's
decision of October 3, 2026, to revisit before an external beta, and no cron or
scheduled job is to be created for it until he decides otherwise. The
[API contract](../API_CONTRACT.md#post-accountdelete) owns the route and its
responses, the [launch runbook](../PRIVATE_LAUNCH_RUNBOOK.md#account-deletion-runs-lane-6)
owns the sweep and its cadence, and the
[lane handoff](lanes/mvee-five-lane-handoff.md#lane-6-account-deletion) owns the
steps. #805 and #806 block turning the flag on. Ordinary household leave/removal
and financial archive retain their own semantics.

Updates includes invitation acceptance, administrator handoff, owner-history
removal and household closure. The lane that causes an event writes its Updates
entry: Household writes the closure when the last member leaves, and account
deletion writes the administrator handoff and any closure it causes. The Updates
lane owns only display and the push opt-in
([lane contract](lanes/mvee-five-lane-handoff.md#contracts-between-lanes)). Bill reminders occur three days before and on
the due date while still due; push previews contain no amounts. A moved account's
authorized pre-move household history is read-only and visibly distinguished.
A month with confirmed complete coverage and no spending is a known zero and shows
0. Sin datos shows only when coverage is missing. A comparison with a known-zero
month uses an amount difference rather than a percent ([Home comparisons lock](argus-decision-log.md#home-comparisons)).

Explicit AI disclosure/consent must precede the first sharing of personal data
with an external model. It ships with that feature, including if live chat lands
before document reading. Local capture and save-for-later do not require model
processing. [Cuadrao's guide](../../.agent/designs/cuadrao/DESIGN.md#13-release-readiness-interaction-rules)
owns interaction details. The [main roadmap](argus-execution-board.md#cuadrao-release-ui-landing-order)
owns the landing order and evidence. Build Household/Connected UI changes on
integration's existing owners rather than the older preview sheets.

## 4. Information ingestion: one destination, several entry methods

The product must work with incomplete banking connectivity. Users may mix input methods without creating competing copies of their finances.

**All ingestion methods converge on one flow:**

**CAPTURE → SAVE → PREPARE → REVIEW → APPROVE.**

**Founder clarification, October 2, 2026:** saving a captured document creates a
durable private draft and retains its source. Successful extraction is not a
prerequisite. The user can close the app and return later. Preparation runs
asynchronously; failure preserves the draft/source with an honest recoverable
status. Approval alone creates confirmed financial activity through the existing
canonical services. Upload does not create an expense, change a balance or make
anyone owe money.

The confirmed record is the durable financial fact. Chat messages, uploaded files, notifications, and extracted text provide context and provenance; they are not independent competing ledgers. Home, Accounts, Plan, Search, and Updates derive from the same confirmed records.

This approved confirmed-record scope supersedes the September 8 historical
Decision 8 prohibition on a new personal-figure storage surface only for explicit
financial-record confirmation. It does not copy arbitrary chat figures into
personalization memory or change conversation retention. That older decision
already allowed figures inside conversation messages; “unconfirmed” must not be
misread as “never persisted in chat history.” Financial-record access follows
the [registered-account boundary](#guest-access-and-registration).

The input methods below are part of the experience direction. Their technical readiness differs. Wallet integrations and bank access are experiments, not promises of universal support or prerequisites for a useful ecosystem. Provider selection for wallet, OCR/document, and banking paths is not locked. Voice provider direction is locked separately under [ARCHITECTURE.md](../ARCHITECTURE.md#voice-and-chart-direction) and section 4.3.

### 4.1 Direct manual entry and editing

Users can add accounts, opening balances, transactions, debts, holdings, goals, and corrections without AI. Keep common entries short, with sensible reusable choices and editable details.

Support both individual activity and balance updates. Someone who only knows their current balance can record that fact without inventing a complete transaction history. Make clear what is known and what remains unrecorded.

Saving a manual form is the user's confirmation; do not add redundant AI approval steps. Manual corrections should be available for every imported or interpreted record.

### 4.2 Type to Argus

Example: “Gasté RD$850 en comida, en efectivo.”

Argus proposes the amount, currency, date, activity type, category, and cash account. The user can confirm or edit the proposal before it affects their finances.

Ask only for material missing information. Do not silently guess an account, currency, debt, or transfer relationship when the choice changes the financial picture. Multiple activities in one message may become a reviewable batch.

Distinguish actual activity from hypotheticals, intentions, questions, and quotations. “Voy a pagar…” is not evidence that a payment occurred.

### 4.3 Speak to Argus

Voice is another way to express the same questions and activities, not a separate financial workflow.

- Record speech, transcribe it, and interpret the intended question or action.
- Let the person inspect and correct important interpreted details.
- Present the same editable financial draft used for typed input.
- Save only after confirmation.
- Handle interrupted recordings or uncertain amounts without creating partial financial records.

**Founder update September 28, 2026:** include full spoken conversation alongside
dictation and transcription. The microphone produces editable text; voice mode
supports spoken replies and interruption while preserving the same review and
confirmation journey. Speech must not silently save a draft or bypass a material
correction. Users can return to text without losing the relevant conversation or
confirmed records. Audio retention and consent, including Temporary chat, remain
explicit product decisions rather than hidden provider defaults.

The selected provider direction and integration boundaries are owned by
[ARCHITECTURE.md](../ARCHITECTURE.md#voice-and-chart-direction). Full voice is an
approved target, not a claim that the frozen template or production implements it.

### 4.4 Upload a file or statement

Support a path for statements and structured transaction files. Exact supported formats and institutions must be stated truthfully as they become available; the intended document path includes PDFs and images, while structured files can include CSV-type exports.

The experience should:

1. Save the supported source and draft, then prepare account, currency, statement period and balance information.
2. Extract candidate transactions and relevant statement facts, such as payment due dates or rates when actually present.
3. Show the original source alongside reviewable extracted information when needed.
4. Flag uncertain fields, missing pages, unreadable content, and suspected duplicates.
5. Let the user assign the account, correct categories/details, and confirm a reviewed batch.
6. Explain what was added, skipped, or left unresolved.

Do not force separate confirmation for every reliable row in a large statement. Batch confirmation must remain understandable, with exceptions highlighted. Failed imports must be recoverable without re-adding successful records.

Statement balances and transactions may describe the same money. Keep opening,
closing, available and running balances distinct from transactions and statement
periods. Never relabel them to satisfy validation or add them as new activity.
Retain useful observations even when one cannot become an import candidate.
Preserve statement dates instead of presenting older data as today's balance.

### 4.5 Photograph or scan a document

Camera capture, document scans, receipts, and screenshots feed the document-review flow. Help users capture readable, complete information and request a retake when necessary.

A photographed receipt can propose a purchase; a bank screenshot may establish only a balance. Extract only what the source supports. OCR output is a proposal, not an authoritative financial fact. Users can always correct or abandon it.

Receipt preparation preserves merchant, date, currency, line items, quantities,
prices, suggested categories, subtotal, tax/service, tip and total when present.
Missing or uncertain details remain reviewable. Items and totals are components
of one purchase, not automatic separate expenses. Keep extracted information,
proposed interpretations and confirmed records distinct. Strict financial
validation applies at confirmation; never invent values or convert currencies.

The supported journeys share one durable draft identity:

- Personal receipt from Chat: save, prepare details/categories, review now or
  later, confirm the account and approve.
- Group receipt from Plan: save in that plan, prepare receipt details and an
  equal-split proposal, review payer/participants, keep equal splitting or assign
  items, including shared items, then approve. Sharing is a separate action.
- Group receipt from Chat: attach the same draft to the requested plan. Chat and
  Plan reopen that draft. A missing or ambiguous destination can wait for review.

A group plan's currency remains fixed. Resolve a receipt currency mismatch during
review without changing the plan or converting amounts. The backend foundation
preserves destination and split proposals; full Chat actions, native presentation
and the complete split-approval journey require their own integration work.

### 4.6 Apple Pay / Google Pay and device-assisted capture

Explore opt-in device workflows that detect a payment-related event and offer a draft: “A payment was detected. Add it to your tracking?”

Potential paths include Apple Shortcuts/App Intents and permitted Android integrations. Feasibility must be validated on the actual platform, device, and payment flow. Neither Apple Pay nor Google Pay is assumed to expose a universal transaction feed to Argus.

Only draft fields the event actually supplies. Missing merchant, amount, currency, or account details must remain unresolved or be supplied by the user. A device notification is not proof of a settled transaction.

The user opts in, can disable the integration, reviews the draft, and can dismiss it. Match later statement imports against these entries so the same purchase is not counted again. Do not imply background tracking is active when the platform cannot support it.

### 4.7 Bank connections and read-only browser-assisted experiments

Direct APIs or aggregators may eventually provide balances and transactions. Named bank coverage, permission, freshness, and failure behavior must be verified; a provider's general marketing claim does not establish support.

The founder also wants to explore user-authorized, read-only browser-assisted access where APIs are absent: the user authenticates to their bank through a secure flow, and an experiment retrieves permitted financial information for review/import. This is an exploration direction, not a selected architecture or a claim that all Dominican banks support it.

Before a real integration, resolve institution-specific feasibility, terms, authentication, credential/session handling, and user consent. Do not bypass MFA or bank security controls. Authentication secrets must not enter chat, analytics, or ordinary logs. The exact secure access design remains open.

Bank access must show connection state, last successful refresh, and actionable failure/re-authentication status. A failed refresh must preserve existing records and their old freshness timestamp. This ingestion path does not authorize payments, transfers, trading, or other banking actions.

Begin with the same draft/review boundary. Any future automatic acceptance of trusted feeds requires an explicit policy rather than silently removing user review. API partnerships can replace the access mechanism without replacing the user's financial records or experience.

## 5. Shared ingestion and trust requirements

- **Provenance:** distinguish user-entered, extracted, connected, and calculated information. Retain enough source context to explain a record without spreading sensitive raw content everywhere.
- **Dates:** distinguish activity date, statement/as-of date, and capture/refresh time.
- **Currency:** preserve source currency; ask when ambiguous. Do not infer dollars or pesos from an unqualified amount.
- **Drafts:** unconfirmed proposals do not affect balances, budgets, goal progress, or alerts about actual spending.
- **Duplicates:** handle repeated uploads, overlapping statements, spoken/manual entries later seen in a statement, and repeated integration events. Surface uncertain matches for review rather than silently deleting legitimate similar purchases.
- **Transfers and repayments:** link the two sides where known and avoid double-counting spending or income.
- **Reconciliation:** distinguish a balance correction from a new transaction. Explain discrepancies; never invent missing activity to force agreement.
- **Corrections:** let users edit, undo, or remove mistakes and see the resulting changes across surfaces. Keep enough history to explain changes.
- **Freshness:** an old known balance remains old, even if Argus opens the screen today. The app must not imply continuous awareness beyond available data.
- **Privacy and control:** explain what is collected and retained; provide appropriate deletion/export controls. Keep financial amounts, document contents, transcripts, and credentials out of analytics and ordinary logs. Storage contracts and enforcement of the registered-account boundary still need implementation.
- **Recovery:** preserve review progress where appropriate and offer a manual path when parsing, voice, or bank access fails.
- **Money representation:** use exact arithmetic; unknown is not zero. Keep
  currencies separate and distinguish actual, expected, estimated and hypothetical
  values throughout records, projections, summaries and charts.
- **Reliable writes:** retries and double taps must not duplicate records.
  Concurrent edits require explicit reconciliation against the current basis;
  interrupted requests retain a recoverable path without silent resubmission of
  stale facts. These guarantees apply to every entry method.

## 6. Connected journeys that the ecosystem must support

### Record everyday cash activity

Type or speak an expense → review and confirm → cash account activity updates → relevant budget changes → Home reflects recorded spending → any meaningful threshold update links back to the budget.

### Understand a statement

Upload or scan a statement → resolve extraction and duplicate issues → confirm → Accounts reflects the new information → Home explains what changed → ask Argus about a charge or payment → save a plan if useful.

### Explore a financial choice

Ask a general market or personal-finance question → receive a grounded calculation or sourced explanation → compare a supported alternative → optionally save a goal or plan → record actual progress → revisit with updated facts.

An investment simulation remains historical evidence, not a promise of future performance or an executed investment.

### Return because something changed

A relevant recorded or external fact changes → Argus creates an explainable update → the user opens the affected account, plan, or answer → inspects the basis → adjusts or records an action if desired.

## 7. Carry forward the existing Argus investment

| Existing capability | Role in the ecosystem |
| --- | --- |
| Chat, cold-start motion, greetings, chips, composer | Familiar entry and conversational help |
| Grounded calculators | Explain choices and support saved plans |
| Research and historical simulations | Explore investments and opportunity costs |
| Structured results, assumptions, confirmations | Make proposals and consequences reviewable |
| Conversations, history, Omnisearch | Recover prior reasoning and evidence |
| Localization, guest access, mobile experience | Reduce friction when starting and returning |
| Saved-answer and change-awareness direction | Relevant updates tied to a person's context |

This is a reuse map, not a claim that components need no adaptation or an exhaustive inventory of production features. Existing capabilities, interactions, records, and gates carry forward unless explicitly changed; omission from this document is not retirement. The primary addition is a persistent, user-correctable personal financial picture. Preserve the existing conversational intelligence and trust boundaries while connecting it to those records. [PRODUCT.md](../PRODUCT.md#current-production-availability-and-planned-changes) owns current availability and approved transitions; the planned experience does not itself enable a hidden feature.

## 8. Differentiation and boundaries

The intended differentiation is a complete-feeling experience even when financial data is incomplete: cash, documents, manual input, and eventual bank connections are all normal ways to participate. Combine low-effort recording with grounded explanations and continuity across a person's financial life.

The minimum ecosystem should feel credible through reliable editing, clear navigation, useful retrieval, currency handling, transparent freshness, and connected outcomes. These are experience goals, not an assertion of verified competitor parity.

Future directions include maintained financial-product discovery, shopping assistance, bank partnerships, remittances, bank-backed accounts/cards, and investment roundups. They are not required capacities of this minimum ecosystem and are not authorized financial execution by this document.

The boundary for adding a capability is: **does it help someone understand, maintain, or improve the same financial picture?**

## 9. Decisions deliberately left open

- Registration, guest conversion and return-to-action mechanics under the [locked access boundary](#guest-access-and-registration).
- Voice integration, retention and acceptance contracts under the [selected provider direction](../ARCHITECTURE.md#voice-and-chart-direction); OCR/document and banking providers and supported formats/institutions.
- Wallet/device automation feasibility and permissions by platform.
- Secure design and institution-specific conditions for browser-assisted bank access.
- Source-file/audio retention details and any future automatic acceptance policy.
- Remaining notification scheduling defaults within the locked inbox and opted-in push channels.
- Maintained market-product inventory, commercial relationships, and execution permissions.
- Engineering breakdown, release order, timelines, and platform sequencing, subject to the [deferred ecosystem runtime lane](#agentic-ecosystem-direction-and-sequence).
- Household invitation security and delivery integration, membership, removal, retention, and permission mechanics. Section 12 owns the share-link, code and QR flow and the current exclusion of household email. The integration contracts must preserve its visibility and consent boundaries.

These open implementation choices do not reopen the approved ecosystem structure. Agents should preserve the distinction between the intended experience, an exploratory integration, and a currently working feature.

## 10. Supporting research

- [DR and Latin American finance pain points: research-to-MVEE mapping](../research/2026-09-26-dr-latam-finance-painpoints-mvee.md) — founder-supplied social/market research recorded September 26, 2026, with the original text and executive summary preserved separately. Its audience and experience-emphasis proposal was subsequently approved and is owned by section 1.1 above. Other research suggestions remain candidates unless explicitly adopted.

## 11. Pain points, limits, and the reinforcing loop

### 11.1 Pain points the minimum ecosystem is designed to address

These are intended outcomes, not assertions of shipped behavior or guaranteed financial improvement.

| User pain | How the ecosystem helps | Boundary |
| --- | --- | --- |
| “My money is scattered; I cannot see where I stand.” | Accounts unifies recorded cash, bank balances, investments, and debts; Home summarizes; Search retrieves the source | Coverage depends on supplied records and supported connections; incomplete coverage stays visible |
| “I do not know what remains until I get paid.” | Home relates dated commitments to recorded money and explicit income assumptions; Plan shows allocations | Estimates expose missing expenses and uncertain income; Argus cannot guarantee affordability |
| “My income varies, so a fixed monthly budget does not fit.” | Separate actual receipts from expected inflows; revise timing and plans when circumstances change | Argus cannot guarantee a commission, remittance, job, or future income |
| “Recording everything is too much work.” | Manual, typed, spoken, and document inputs converge on reviewable records; retain context and match imports | Capture cannot become effortless by inventing facts; device and bank automation remain conditional integrations |
| “I keep paying debt but do not understand the result.” | Bring debts and activity together; explain payment scenarios, costs, and actual versus projected progress | Calculations depend on supplied terms and supported models; Argus does not refinance or negotiate debts |
| “My budget, debt payments, and goals compete for the same money.” | Plan relates all commitments to a shared picture and shows how a proposed choice affects it | The person chooses priorities; no forced financial ladder or automatic money movement |
| “Bills and irregular expenses catch me off guard.” | Record recurring and occasional obligations, show upcoming dates, and issue selected reminders | A reminder does not pay a bill; unknown obligations cannot be monitored |
| “An emergency erased my progress.” | Show its effect on accounts and goals; support revising a plan without blame | Visibility and planning do not provide emergency cash or insurance |
| “I cannot tell how a choice changes my situation.” | Argus uses grounded calculations, comparisons, and recorded facts to explain alternatives; a useful scenario can become a saved plan | A simulation is not a promise, executed transaction, or automatic recommendation |
| “I do not trust a number or cannot find where it came from.” | Expose assumptions, provenance, freshness, and editable records; Search reconnects an answer to its evidence | Transparency helps assess information; it does not certify every external source as correct |
| “We manage money together but cannot see our shared commitments clearly.” | Invite a partner; combine explicitly shared individual and joint accounts, obligations, budgets, and goals in a household view | Household membership does not grant access to every personal account or conversation; only authorized shared information contributes to the shared picture |

### 11.2 Pain points only partially addressed or outside the minimum

- **Insufficient income, inflation, and housing prices:** Argus can expose a shortfall and model choices; it cannot create surplus, employment, cheaper housing, or purchasing power. Do not equate a structural shortfall with poor discipline.
- **Housing access:** Supported payment scenarios and savings goals can help exploration. Mortgage underwriting, preapproval, access to a lender, and dedicated qualification workflows are not minimum capabilities promised here.
- **Credit access and bureau problems:** Explaining supported supplied information is different from obtaining a bureau feed, fixing a credit file, predicting a score, or determining why a lender declined. Those specialized services are not locked into this minimum.
- **Fraud and scams:** Grounded explanations can expose missing information or unsupported claims. Guaranteed scam detection, account-takeover monitoring, and recovery of losses are not provided by this ecosystem definition.
- **Banking and financial execution:** No claim of universal live bank access, automated bill payment, debt negotiation, subscription cancellation, remittance transfer, custody, card issuance, or trade execution.
- **Household scope:** Partner invitations and combined household finances are included, as defined in section 12. Joining a household does not provide bank-account authority, merge personal identities, or make all private records visible. Broader family/dependent and professional-advisor roles are not implied by this decision.
- **Behavior and emotional stress:** Clear, neutral feedback and low-effort routines may help. Habit, reduced anxiety, and retention are outcomes to learn from users, not guarantees or substitutes for human support.

### 11.3 Five experience pillars and how they reinforce the loop

These are MVEE experience pillars, distinct from the repository's engineering quality pillars. They describe the existing approved loop rather than five new modules or navigation destinations.

| Experience pillar | Primary surfaces | Value to the person | How it strengthens the next step |
| --- | --- | --- | --- |
| **Record with little effort** | Accounts, Argus, shared capture/review controls | Keep finances up to date through the input method that fits the moment | Confirmed, corrected facts make the financial picture more useful |
| **Understand the picture** | Home, Accounts, Argus, Search | See what is known, committed, changing, or uncertain | Clear explanations make it easier to choose a realistic action or plan |
| **Plan and compare choices** | Plan, Argus | Connect budgets, debts, and goals; explore consequences before acting | Saved commitments establish meaningful dates, thresholds, and progress to revisit |
| **Notice relevant change** | Updates, Home | Recognize a deadline, change, milestone, or stale assumption while it is useful | Each update links to the affected record or decision and gives a reason to return |
| **Return and adjust easily** | All surfaces, with Search for continuity | Record what actually happened, correct facts, and revise a plan without starting over | Updated records improve the next explanation, forecast, and reminder |

The loop is **record → understand → plan → notice → return and update**. It also supports direct entry at any point: a question, an account check, a saved goal, or a useful reminder. Daily use and visiting every surface are not requirements.

Profile/data controls and transparent provenance support trust throughout. Search preserves continuity. Chat crosses the entire loop, contributing capture, interpretation, explanation, and comparison rather than competing with the other surfaces.

### 11.4 Example and failure conditions

A person confirms a received commission. Accounts records it. Home places it alongside upcoming obligations. Plan shows the remaining room after existing commitments. The person asks what an extra debt payment would change and saves a chosen plan. A reminder opens that plan; after the person actually pays, they confirm the payment. The transaction matches the planned commitment, progress updates, and the next visit starts from the revised picture.

That loop fails if capture is too burdensome, stale facts appear current, hypothetical actions change actual balances, several surfaces allocate the same money, reminders are irrelevant, or corrections do not propagate. Polished navigation alone cannot compensate for these breaks.

Retention is intended to come from accumulated useful context and recurring real decisions. The product should remain valuable even when someone dismisses notifications; interruptions are not a substitute for utility.

## 12. Household collaboration: approved minimum capacity

**Founder decision, September 26, 2026:** Include a combined household view and a way to invite a partner. Individual and joint accounts can both be part of the financial picture. This explicitly supersedes the earlier boundary that treated household collaboration as a separate future decision.

### One person can belong to both financial contexts

Provide a clear **Personal / Household** context choice without adding another primary navigation destination. Use the same Home, Accounts, Argus, Plan, Search, and Updates surfaces in the appropriate context. A person can use Argus alone; inviting a partner is optional.

The personal view contains the person's own financial picture and any joint accounts they are authorized to see, with ownership clearly labeled. The household view combines explicitly shared information, rather than summing two personal dashboards.

### Invite and choose what to share

- A person creates a household and invites their partner. The invitation must be accepted before access is granted; each person keeps their own sign-in.
- Before sharing, show what the partner will be able to see and do. Household membership alone must not expose private accounts, documents, chats, or income.
- Support individual accounts kept private, individual accounts explicitly shared with the household, and joint accounts shared by the partners.
- A person can contribute an agreed amount to a household plan without exposing the source account's entire balance or history. Mark whether that contribution is planned or received.
- Account ownership, visibility, and permission to edit are distinct. Label them clearly; joining a household does not transfer ownership or confer banking authority.
- Sharing can be reviewed and revoked. Leaving/removal must stop future unauthorized access, explain effects on shared plans, and avoid silently deleting another person's records. Member powers, view-versus-edit grants, and departure/custody for membership and account grants are locked by the [2026-10-01 permission policy](lanes/household-permission-policy.md); further joint-plan export/retention product choices beyond that package remain open.

### Shared financial picture

**Home:** Show shared money and obligations, expected versus received contributions, and household progress. Identify missing or stale information. Describe totals as based on shared records, not as everything either partner owns.

**Accounts:** Label individual versus joint ownership and who can see or edit the record. Both partners can inspect authorized shared activity. Keep private account details out of the household view.

**Plan:** Support shared budgets, bills, debt commitments, and goals. Show each contributor, planned versus recorded progress, and who can view or edit the plan. A planned contribution is not received cash or saved progress. Plan editing does not grant access to private funding accounts. Make responsibilities understandable without requiring a 50/50 split. Private plans remain private unless explicitly shared. The sketch demonstrates these distinctions with optional fictional shared-plan examples, not a working multi-user permission system.

**Argus:** Let a person ask about the personal or shared picture, with the active context clear. A proposed entry must identify the relevant account or household commitment before confirmation. Answers, summaries, and calculations must not expose another person's private facts indirectly.

**Search and Updates:** Respect the same visibility boundaries. Shared milestones and obligations can generate relevant household updates; private activity must not leak through search results, totals, notifications, exports, or suggested actions. Each person controls their notification preferences.

**Capture and review:** The approved capture paths in section 4 should also serve shared records. Existing chat is a foundation to extend; manual, conversational, voice, document, and connection-based financial-record capture still need their scoped technical contracts and implementation. Show the destination and sharing scope before confirmation. Uploading a document to a household context must make source-document visibility clear; it must not unexpectedly share unrelated private pages or details.

### One shared fact, no duplicate money

- A joint account imported by both people is still one account. Match overlapping transactions and resolve uncertain matches before double-counting.
- A contribution transferred from an individual account to a joint account must not become new household income merely because it moved accounts. Preserve the distinction between external income, transfers, and contributions; show the reporting scope.
- A shared bill appears once in the household obligation total, even when both people contribute toward it. A planned contribution is not actual available cash.
- Confirmed shared updates propagate to both partners' authorized views. Make it possible to identify who recorded or corrected an entry and resolve mistakes without silently overwriting another person's work.
- Information that was not shared must not be silently included in shared calculations, even if a personalized aggregate could conceal its source.

### Invitation delivery: founder-locked September 27, 2026

- **Copy invite link** is the simple sharing action. People can paste it into
  WhatsApp, Messages, or another channel themselves; Argus does not send a
  WhatsApp Business API message for this flow.
- The [October 2 invitation decision](argus-decision-log.md#invitations) narrows
  the September 27 delivery selection. Provide a share link, an invite code and
  a QR code for the same invitation lifecycle.
- Invite links use a direct cuadrao.ai universal link. do-blitz is no longer the
  invitation path; it remains an option for later marketing links. Cuadrao owns
  authorization, expiry, revocation and acceptance.
- Household email invitations are outside this pass. Resend remains the selected
  email service, including authentication and recovery. Its availability does
  not enable household invitation emails or consumer Updates emails.
- Invitations carry no rewards or incentives in this iteration.
- Acceptance does not create a joint financial account or share personal accounts
  automatically. Joint account creation and account sharing are explicit actions.

The disposable UI may explore choosing an individual contact as a shortcut to
entering the recipient. Contact synchronization, revealing who already uses
Argus, a social feed, automatic friend creation, and acquisition incentives are
not approved by this delivery decision. Any later discovery design needs explicit
consent, discoverability controls, and a scoped privacy contract.

### How the household strengthens the loop

One partner records a household purchase → the shared budget reflects it → both can understand what remains → they adjust an agreed contribution or goal → a relevant update brings either person back → the next confirmed action refreshes the same picture.

The value is less repeated coordination and fewer conflicting versions of shared commitments. This adds collaborative usefulness to the existing loop without making surveillance, mandatory sharing, or relationship management part of the product promise.
