# Cuadrao Business owner pilot

## Current authority and landing boundary

**October 10, 2026 update.** The founder approved the Business agent direction later the same day. The [Business agent execution spec](cuadrao-business-agent-execution-spec.md) now owns the Business build order, the proposed agent contract and the decisions. Where this document says "Business chat stays off" or that the agent audit approves no model-facing implementation, that spec takes priority. Business chat is part of the future agent implementation. This PR changes documents only. It turns on in hosted environments for pilot businesses, through server flags, after J1 passes and the founder approves. Each model-facing change still needs a committed scorecard.

Reconciled October 10, 2026. Dates in the decision table are UTC. This document preserves the original owner-pilot
requirements and records their later disposition. It is not a new implementation
assignment or a statement that the complete pilot works.

Read [documentation authority](../../DOCUMENTATION_AUTHORITY.md) and the
[MVEE](../argus-minimum-viable-ecosystem-experience.md) within their declared
scopes. The [connected-flow spec](../cuadrao-business-connected-flow-spec.md) owns the
wider workflow. The [Business handoff](../../handoffs/cuadrao-business-lane.md)
records the October 8 implementation checkpoint and its evidence. Its pause
predates the later founder continuations below. The
[core-flow tracker](https://github.com/lagarcess/argus/issues/942) tracks remaining
acceptance. The [API](../../API_CONTRACT.md), [data](../../DATA_MODEL.md), and
[architecture](../../ARCHITECTURE.md) documents retain their technical ownership.

| Work | Disposition for this landing |
| --- | --- |
| Owner API, S1–S3 isolation, and non-model-facing S4 chat separation | Already merged through #913, #914, and #918. #920 adds the default-off Business chat gate. Do not rebuild them. |
| #900 and #910 | Documentation reconciliation only. They enable no feature and apply no migration. |
| #925 | Preserve separately. Its model-facing restrictions, refusal UI, evaluation-budget changes, and scorecard work are excluded. Business chat stays off. |
| Later local sandbox at `df208f7ec2379cd84efd55eea0deb685d67c5360` | Preserve on `codex/cuadrao-business-sandbox`. It is not included in these planning PRs. Local evidence does not establish hosted delivery or complete core-flow acceptance. |
| Agent-first Business direction | Retain the direction for communication through defined Cuadrao tools. This docs landing adds no runtime, tool, prompt, voice, memory, or ledger action. |
| E0 and wider UI work | No restart in this landing. The later capture work does not automatically authorize fiscal work or a broad redesign. |

The founder's continuation decisions supersede the original narrow pilot where
noted below. References identify human turns in Business Lane
`01a0de75-29ee-71f0-8f58-0d2bb3934a33`.

| Human decision | Effect on the original brief |
| --- | --- |
| October 9, turn `01a11fa2-0fcb-76e3-b986-1b728868a46d`: “don't wait on my permission use your best judgement” and a “full working sandboxed system with the plumbing ready” | Authorized continued local sandbox delivery after the earlier handoff pause. Preserve existing shell behavior and keep delivery claims tied to evidence. |
| October 9, turn `01a12229-be2b-7de0-8a9f-fd2c5b19c45a`: “Approved proceed.” | Authorized the proposed Core Flow 2 work after the preceding scope discussion. |
| October 9, turn `01a122a9-8d1e-7112-b157-222bf06c2411`: the supplied capture acceptance table | Added email, manual capture, multiple formats, routing, original bytes, duplicates, recovery, security, and honest status. Capture must not silently record an expense. |
| October 10, turn `01a123db-ef52-7361-bfa2-89eb2a44293a`: “Laptop proof first; don’t point Meta/email at it until that passes. Prod untouched.” | Authorized scoped WhatsApp and staging follow-through then. This landing performs none of those external actions and makes no claim that their gates passed. |
| October 10, turn `01a124c9-777f-7c63-9325-3250e4854406`: request to audit the agent/tool inventory | Establishes the newer agent-first investigation. It does not approve a new model-facing implementation through this PR. |

Current landing constraints exclude main, hosted changes, paid evaluation,
chat activation, and new product or copy work. The coordinator grants serialized
merge slots. Preparing a PR does not grant its merge slot.

## Original planning baseline

The remaining sections describe the October 7 owner-pilot baseline, with explicit
later dispositions where its requirements changed. Code pointers and initial
verification targets belong to that baseline. Use the handoff and core-flow
tracker above for delivery status, not future-tense requirements below.

Planning base fetched on October 7 is
`93571e593e1677561e1dd38f63b6475574942e2d` on
`origin/codex/private-alpha-next`. Code pointers below were inspected at that
base. They establish reuse candidates, not tested Business availability.
Production deployment identity was not verified for this scope PR. A visual
inspection of the signed-in production chat established only sidebar, composer
and search presentation. Refresh code and issue state at assignment time.

## Deliver the owner outcome

An owner sends a receipt to Cuadrao through WhatsApp or uploads it on the web.
Cuadrao saves the private source, prepares a reviewable draft and shows it in
one inbox. The owner corrects the draft, selects the account and confirms the
expense. After leaving and returning, the owner can find the expense and its
original receipt. Repeated delivery cannot silently create another expense.

The owner can also see a small, accurate business overview and ask Cuadrao's
built-in AI about saved expenses, with links back to the supporting records.
The initial interface serves business owners. Later accountant feedback expanded
the workflow to organized evidence, uncertainties, and accountant handoff.

The original pilot used one owner per business. Later sandbox work explores firm
access and custodian approval separately; this PR neither ships nor validates it.
Private Business records must remain separate from the same person's Personal and Household data.
The founder chose separate Personal and Business spaces on October 8; the
[space slice plan](https://github.com/lagarcess/argus/pull/910) is the detailed
isolation contract.

This pilot is stage B1 of the
[connected-flow spec](../cuadrao-business-connected-flow-spec.md) (#912), which
owns the wider Business roadmap: the offline fiscal engine (E0), the connected
period pilot with invoices, collections and the accountant package (B2), and
separately authorized live fiscal processing (L). This pilot implements none of
those. E0 has no automatic start when this slice finishes; the handoff records
its hold and this landing does not lift it.

## Preserve the agreed experience

| Area | Required pilot behavior |
| --- | --- |
| App shell | Reuse Argus's responsive web/PWA shell, restrained typography, spacing, rounded controls and collapsible sidebar. Preserve existing guest and registered chat outside Business. |
| Search | A desktop top search entry opens the existing omnisearch interaction. Add authorized Business results and source links through canonical search owners. Do not build a second search index just for this page. |
| Sidebar | Expose working overview, receipt inbox, expense records, New chat, Recents and settings destinations. Exact labels and grouping are reviewed in the local preview. No dead future-feature icons. |
| Main panel | Show useful summary cards with period/currency filters and drill-down to their actual records. Keep a full conversation view available. |
| Composer | Keep the familiar composer available at the bottom on overview and conversation views without covering content or losing an unfinished draft. Define its contextual handoff to a conversation. |
| Profile | Top-right at desktop widths. Preserve the existing placement on smaller viewports. Reuse one profile state and menu owner. |
| Phone web | Cards stack, navigation stays usable, upload and review work with touch and the keyboard. This does not promise offline ingestion or background browser execution. |
| Languages | English and Spanish, including loading, empty, validation, failure and recovery states. |

Start the overview with receipts awaiting review, confirmed expenses in the
selected period and imports needing attention. Show recorded coverage and
freshness. Use separate currency totals; do not add DOP and USD or invent FX.
Do not show profit, runway, revenue or trend claims without sufficient real data.
Summary cards can use deterministic facts. Generative summaries are not required.

Separate conversations, New chat and Recents remain. Agent actions can later
operate within those conversations. A consumer continuous-conversation target
does not require replacing Business history in this assignment.

Preserve the broader Business direction for accounts, planning, customers and
useful actions. It is not necessary to build all of Midday to finish this pilot.
Company logo customization, a detachable/draggable desktop composer, dashboard
builders, invoicing, bank integration, team billing and the native Business app
are outside this slice.

## Create menu, Inbox and Updates

Founder clarification on October 7 adds a Slack-inspired **+ Create** control.
It sits on the sidebar row grid, sized like the other rows. Its short menu holds
upload receipt and record expense. New chat appears once, at the top of the
sidebar, not in Create. Expose only working actions. On small
screens, keep Create reachable through responsive navigation without requiring
a desktop sidebar. Show both layouts in the first preview.

Use one shared action owner for Create, starter chips and composer entry points.
The composer attachment adds a receipt to the current conversation. Create can
start receipt intake outside a conversation. Both enter the same receipt flow
and preserve unfinished input. Opening a menu must not upload, invoke AI or
confirm an expense. Support keyboard navigation, Escape and focus return.

Keep two distinct destinations:

- **Inbox:** receipts that need owner review or correction.
- **Updates:** processing results, failures and other changes that need attention,
  with a link to the affected record.

Assess the existing #825 contract before implementing Business Updates. This
slice does not require a full notification system or push delivery. Include an
Updates sidebar entry only when real events and working destinations support it.
Until then, surface processing state and recovery in Inbox and the receipt view.
Do not invent an unread count or duplicate receipt state in a notification store.
The preview must explain this boundary without adding inactive menu items.

## Adapt starter chips and preserve personality

Founder clarification on October 7 keeps the existing starter-chip interaction.
Adapt chips to actual pilot entry points, such as uploading a receipt, reviewing
pending receipts and asking about saved expenses. Chips open the correct flow or
prepare an editable question. They must not auto-approve expenses, invoke paid
AI without consent or advertise unfinished features. Test empty and populated
Business states so suggestions lead somewhere useful.

The founder's reference to new-chat type-out messages means the rotating welcome
or starter copy, not a new chart type. Business-specific greetings and additional
Cuadrao personality are optional later polish. Preserve suitable existing copy
and motion without making a copywriting pass a pilot requirement. Respect reduced
motion and avoid repeatedly announcing animated text to screen readers.

Inventory the Argus A in the chat background, chat-loading transitions and the
top-left corner. Replace those through a shared brand asset once the founder
approves the Cuadrao logo. Logo design and that replacement are not pilot blockers.
Do not invent a final logo or treat marketing's provisional favicon as approved
application branding. Keep a clear asset owner so future replacement is consistent.

## Adapt the composer to receipt intake

Founder clarification on October 7 adds the consumer ingestion experience to
Business's existing composer. Use an attachment/add control as the initial
entry point. Omit the asset/indicator `@` picker in the Business composer for
this pilot. Preserve it in existing Argus chat where it still has a purpose.
This changes presentation, not the shared runtime's existing finance abilities.

Assess `ios/ArgusFoundation/Cuadrao/Receipts/CuadraoReceiptCapture.swift`,
`CuadraoReceiptNativePicker.swift` and
`ios/ArgusFoundation/Connected/ConnectedReceiptDrafts.swift` for the consumer
interaction and contract. Reuse the contract and interaction intent, not Swift
components inside a browser. Consumer release flags remain owned by consumer.
Also distinguish financial receipt ingestion from `web/components/receipt/`,
which contains existing answer/evidence receipt presentation.

- Every supported browser gets a normal file picker. Show camera or photo
  capture where supported, with a file-picker fallback on denial or failure.
- Desktop can offer file drop and image/file paste where supported. Keep upload
  reachable through a labeled button, keyboard and touch.
- Detect actual input/browser capabilities. Use responsive breakpoints for
  placement and spacing; screen width or user-agent guesses alone must not decide
  whether someone has a camera or can upload. Do not request camera access on load.
- Show only working ingestion actions. Forwarded email and Gmail do not appear
  as usable controls before their integrations exist. WhatsApp setup is a linked
  intake method, not an invented local file-picker capability.
- Save attachment state independently of unsent chat text. Attaching a file must
  not silently send the message, consent to AI or approve an expense. Navigating
  between inbox, overview and chat must preserve the intended destination.
- Test narrow desktop windows, touch laptops, mobile Safari, permission denial,
  picker cancellation and unsupported camera capture, not only phone/desktop
  user-agent presets.

## Complete both intake paths

### Web upload and review

- Accept the existing bounded PDF, JPEG and PNG contract first. State supported
  formats and limits before upload. Assess iPhone photo formats and either safely
  normalize them or give an actionable unsupported-format message.
- Save source and draft before preparation. A capture can succeed while AI is
  unavailable or consent is declined. Do not describe a draft as a saved expense.
- Show original source and editable merchant, date, amount, currency, category
  and destination account. Keep useful line items, tax, service and tip when
  supported by the receipt. Unknown fields stay unknown until corrected.
- Correcting a proposal does not rewrite the original extraction evidence.
  Distinguish proposal edits from edits to an already confirmed expense.
- Use the existing canonical approval/posting service. One receipt total creates
  one purchase, not separate purchases for its total and each line item.
- Allow review later, retry after recoverable failure, and removal under the
  existing source-retention and financial-history rules. Never erase confirmed
  money merely because an intake connector is disconnected.
- If the receipt does not establish payment, do not infer a paid expense or
  balance movement. Ask for the missing fact using the canonical money contract.

### WhatsApp receipt intake

WhatsApp and web upload were the first pilot inputs. The later Core Flow 2
assignment added forwarded email. Connected Gmail remains separate. The original
email deferral must not be used to discard the authorized sandbox email work.

Use Meta's official Cloud API. During development use its test business number
and approved testers, including the founder's personal WhatsApp as a sender.
Founder decision, October 8: Cuadrao has one receiving number. Each owner links
the personal number they already use to their Business space with a verified
code. Owners do not buy a number or register their own WhatsApp API account.
Only receipts the owner sends are processed; their other conversations are
never read.
Do not migrate the founder's personal number into a business sender. The company
number is pending. Confirm test resources in the actual Meta account before
claiming availability. Do not buy a number or subscribe to another provider.

The narrow pilot proposal is receipt intake plus a receipt acknowledgement and
an authenticated web review link. Correction and expense approval happen in the
web app. This was the original review boundary. The newer agent-first direction
requires a separate tool and approval contract before conversational review can
be enabled.

The implementation contract must cover:

- Verified linking of a WhatsApp sender to one signed-in Business owner and
  destination. A phone number supplied in text is not proof of ownership.
- Unknown or disconnected senders, relinking and revocation. Never guess an
  owner from a filename, forwarded sender name or document content.
- Webhook verification and signature validation, bounded media download from
  trusted provider endpoints, type/size validation, and privacy-safe logs.
- Durable receipt of the delivery before acknowledging it. Replay of the same
  provider message must converge on the original draft and confirmation result.
- Cross-channel duplicate handling. Exact bytes can be recognized; WhatsApp can
  transform an image, so receipt similarity needs review instead of silent
  deletion. Different legitimate purchases must remain distinguishable.
- Explicit AI consent scoped to the linked owner. Sending a document alone must
  not become implicit consent to an unapproved model provider.
- Acknowledgement only after durable capture, failures that can be recovered,
  and owner-scoped review links that disclose no financial data to another user.
- Outbound acknowledgement rules, provider limits and any template/cost needs.
  Do not assume unrestricted outbound messaging.

A public HTTPS callback is needed for real delivery. Prepare a bounded temporary
local tunnel or existing approved endpoint for founder review. Do not expose
local services, send real messages or create hosted resources in this scope PR.
The final real test must use a synthetic receipt and an explicitly approved test
sender. Replay fixtures prove code behavior, not actual WhatsApp connectivity.

## Keep one record and one set of permissions

The assessment must name owners for these concepts before implementation:

| Concept | Required contract |
| --- | --- |
| Business context | Explicit owner/business/account authorization, independent of visual navigation and consumer household grants. Decided October 8: one Business space per owner, compatible with #819, per the [space slice plan](https://github.com/lagarcess/argus/pull/910). |
| Intake delivery | Source channel, provider delivery identity where applicable, owner, Business destination and linked document identity. |
| Retained source | Private object reference, MIME type, size and fingerprint, authorized retrieval and deletion. |
| Document draft | Existing durable identity, preparation status, version, consent, extracted evidence and editable proposal. |
| Confirmation | Existing review event, stable idempotency key and canonical financial activity link. Retry and concurrent confirmation cannot post twice. |
| Search/overview/AI | Read the same confirmed records and authorization context; drafts and failed imports are explicitly distinct. |

These are requirements for an assessed contract, not instructions to create six
new tables. Extend canonical owners only where the existing shape cannot express
the approved behavior. Do not create a second ledger or a second approval state.

At the original planning base, source bytes lived in Postgres. The handoff now
records merged private Storage work. Verify the target environment for private
storage,
source retrieval and cleanup before enabling receipt ingestion for the pilot.

The original preparation path used FastAPI BackgroundTasks. The handoff records
the subsequent durable-job work. Persisted drafts alone do not prove
that a process restart will finish a job. Reuse the existing job direction and
coordinate #823/#826 to define durable dispatch, bounded retries, restart recovery
and stale-result rejection. Do not introduce another worker platform by default.
A closed browser must not cancel accepted intake. Provider timeouts with uncertain
outcomes must not trigger unbounded duplicate spend.

## Original assistant boundary and later direction

Cuadrao provides its own AI by default. Preserve the existing LangGraph runtime,
conversation persistence, streaming and grounded calculations. The original proposed
Business job was read-only expense Q&A, for example "What did I spend this month?"
and "Show the receipt for this expense."

- Read authorized Business records through a typed tool/service contract.
- Compute totals deterministically with period, currency and recorded coverage.
- Link answers to actual expenses and their source where available.
- Make missing data and unavailable capabilities explicit. Do not answer from
  mock balances, marketing examples or a model's recollection of money.
- Recheck permissions on tool reads and source links. A changed conversation
  context cannot grant access to Personal or Household records.
- Treat receipt text and attachments as untrusted data, never instructions.
- This documentation landing adds no autonomous writes, background agents,
  generic RAG, memory changes, voice, or parallel interpreter. Later agent work
  follows its own explicit contract. Model-facing changes require the repository's
  applicable scorecard/evaluation gates and separately bounded live spend.

The wider approved direction includes connecting an owner's external AI through
MCP, similar to [Midday's connection flow](https://midday.ai/mcp/chatgpt/).
That lets the external AI use authorized Cuadrao tools. It does not mean a user's
ChatGPT subscription powers Cuadrao's composer. External MCP/OAuth and customer
API-key support are deferred follow-ups. Preserve reusable tool boundaries now;
do not implement an MCP server or token store in this slice.

## Inspect these existing owners first

| Existing path | Observation at the planning base | Assessment needed |
| --- | --- | --- |
| `web/components/sidebar/SidebarShell.tsx`, `ChatSidebar.tsx`, `ProfileMenu.tsx`, `profileMenuPlacement.ts` | Existing navigation/profile components. | Reuse shell with desktop-only profile relocation; preserve mobile and guest behavior. |
| `web/components/chat/ChatInterface.tsx`, `ChatInput.tsx` | Chat owns substantial conversation/composer state. | Extract only necessary shared layout seams; do not copy the whole chat brain into Business. |
| `web/components/sidebar/ChatCommandPalette.tsx`, `command-palette/`, `RecentsQuickPeek.tsx` | Existing search/dossier/recents UI. | Extend typed results and routing without leaking context or dropping existing history. |
| `src/argus/api/routers/financial_documents.py`, `src/argus/api/documents.py` | Registered-owner, gated upload/list/read/source/proposal/prepare paths. | Connect Business UI and adapter; current upload schedules process-local background work. |
| `src/argus/domain/ingestion/documents/` | Source/draft persistence, receipt structure and extraction/preparation. | Business ownership, Storage, transport provenance and restart recovery. |
| `src/argus/domain/ingestion/reconcile/` | Import observations, duplicate handling and canonical recording boundary. | Trace reviewed receipt edits through exactly-once posting; confirm cross-channel behavior. |
| `src/argus/domain/recording/` | Canonical money/account owners. | Prove Business context, account selection, correction and balance effects. |
| `src/argus/domain/financial_search.py`, `src/argus/api/routers/financial_search.py` | Typed financial search includes accounts and activities; document is not currently a hit kind. | Add source/draft retrieval to the existing search contract where required. |
| `tests/ingestion/`, `tests/test_document_extractions_postgres.py`, `tests/test_ingestion_reconcile_postgres.py`, `tests/test_financial_search_postgres.py` | Focused existing verification entry points. | Extend realistic fixtures and real Postgres evidence; do not duplicate every test. |

The existing marketing Business guide owns website presentation, not this app's
availability. No WhatsApp adapter was verified in this scoped read. Claude must
search before claiming it is absent or creating one.

## Original delivery sequence (not a restart instruction)

1. Fetch remote integration. Record its SHA and assess this brief against code,
   open PRs and #778, #819, #823, #824, #826, #827 and #828. Return a short
   reuse/build/conflict table, concrete API/data/job contracts, file ownership,
   and any genuine founder decisions. Continue independent local work.
2. Show the founder a local desktop and phone preview using the existing shell.
   Agree overview, inbox, review and chat navigation. Clearly label fixture data.
   UI approval is not proof of the connected flow.
3. Complete web upload through review, canonical save, retrieval and overview on
   local real services. Include minimal Business account setup or selection so
   the journey does not depend on manually editing the database.
4. Connect WhatsApp to that same pipeline. Prove identity binding, replay and
   recovery locally, then run the authorized real test-number journey.
5. Connect the bounded built-in expense Q&A and record links. Preserve existing
   chat/history and run the applicable regression and live evaluation gates.
6. Reconcile current integration, review the whole slice and deliver durable
   evidence. Prepare the separate activation packet with actual configuration,
   remaining provider inputs, cost, rollback and hosted smoke plan.

These are work ordering steps within one slice, not isolated frontend/backend
projects or long-lived incubation branches. Claude may propose small integration
PRs with unfinished functionality default-off. Do not mark the pilot complete
until all required connected journeys pass.

## Verify the complete slice

| Scenario | Required evidence |
| --- | --- |
| Upload/save/return | Real API and local Postgres/Storage; source and draft survive reload, reviewed expense appears once, search opens it and its source. |
| WhatsApp/save/return | Approved real test sender and synthetic photo or PDF; acknowledgement, web review, canonical save and later retrieval. Record provider mode separately from fixture tests. |
| Duplicate delivery | Replay provider event, repeat upload, deliver same receipt across channels, double-click approval and retry after lost response. Show one financial effect and explain uncertain near-duplicates. |
| Correction | Correct merchant/date/category/amount/currency/account before save; stale revision cannot overwrite newer review. Explicit correction after save uses canonical money behavior. |
| Missing data | Unreadable receipt, unknown currency, ambiguous payment, unsupported file and absent account produce recoverable states without invented money. |
| Failure/restart | Declined AI consent, provider failure, expired media, disconnected sender, worker interruption and browser close preserve valid saved state; retry remains bounded. |
| Isolation | Two owners plus Personal/Household context; forged webhook, unknown sender and direct draft/source/search/tool access cannot cross boundaries. |
| Overview and AI | Totals match saved expenses for the selected period/currency; drafts excluded; AI sources resolve and deleted/inaccessible records do not leak. |
| UI regression | Desktop and phone widths, English/Spanish, keyboard/focus/touch; composer draft survives navigation; existing chat, search, Recents and profile behavior remain intact. |
| Retention | Source removal/disconnect/account deletion removes private stored objects as required without silently rewriting confirmed financial history. |

Use focused tests plus actual browser journeys. Record manual-entry baseline and
receipt-assisted active review time, correction count and completion rate on
realistic labeled synthetic receipts. Measure capture acknowledgement and review
loading on the target environment. Agree numerical budgets in the assessment;
this planning PR does not invent performance results or require broad load tests.

Store exact-head screenshots, test logs and acceptance results under
`docs/reports/evidence/cuadrao-business-owner-pilot/` or durable GitHub attachments.
Record original/current integration base, reconciliation merge, semantic overlap,
PR head, CI and review result. Local mock-provider success is not provider proof;
local real-service success is not hosted pilot acceptance.

## Coordinate without blocking unrelated lanes

- Consumer owns iOS #877/#899 and its release candidate. Business does not edit
  `ios/`, alter consumer navigation, or reopen guest/pricing/household decisions.
- Marketing owns #880/#895 and `marketing/` extraction, forms, DNS and Resend.
  Assess work against that extraction before editing the web shell. Do not pull
  website code back into the application or alter its release candidate.
- #778 private source storage and #823 document jobs are shared dependencies.
  Confirm one active writer for each contract. Reuse existing issues rather than
  launching a competing storage, consent or job implementation.
- #819 owns space migration; #824 search; #826/#827 conversational runtime;
  #828 AI consent. Business proposes narrow extensions with their owners and
  retains the existing interpreter until an approved contract changes it.
- Schema additions use a coordinated migration order. No `db push` to the live
  project, backdating to bypass a gate, ledger repair or gate-pin changes here.
- Supabase stays Free; Docker is the development/rehearsal environment. No new
  hosted staging, automatic preview branch, subscription or service purchase.
  Check GitHub/Supabase automatic behavior before publishing migration PRs.

## Approval and completion boundaries

The original assigned owner could perform local implementation, tests, PR edits
and review follow-up. That assignment included landing preparation and the
repository landing workflow after an authorized merge. Founder merge authority remains unless the
founder explicitly delegates bounded integration merges when assigning the lane.
No promotion to main, deployment, DNS, live migration, provider activation,
credential creation, message sending or paid run is granted by this scope PR.

Before live extraction tests, propose provider, fixtures, attempt limits and
maximum spend. Before real WhatsApp delivery, identify the test sender, callback,
synthetic receipt and acknowledgement. Batch required founder inputs once the
concrete setup is ready. Company-number activation is needed for public pilot
availability; test-number proof can precede company approval.

Finish with separate statements for implemented, locally verified,
provider-verified and hosted-enabled. Record concrete blockers instead of calling
a default-off or mock-only implementation a launched Business product.
