# ARCHITECTURE.md

## Existing Runtime Architecture and Technical Contracts

**Status:** Active | **Alpha Architecture v1 Locked**
**Audience:** Engineers, AI agents, founders
**Purpose:** Define the existing runtime's technical boundaries and intended contracts. The [MVEE](specs/argus-minimum-viable-ecosystem-experience.md) owns product experience. New financial-record, ingestion, household, and native-client architecture remains to be designed through explicit scoped work.

> [!IMPORTANT]
> **Locked Status**: No structural architecture shifts (service ownership changes or protocol swaps) are allowed without explicit approval. Additive refinements and implementation detail documentation are permitted.

> [!NOTE]
> This document contains both existing system descriptions and intended runtime contracts. Check code and release evidence for availability. Resolve a concrete discrepancy in the assigned scope; this document does not select the architecture of the new ecosystem or authorize an unrelated migration.

---

# 1. Architecture Philosophy

The existing conversational runtime and backtesting engine are infrastructure
that the approved ecosystem carries forward.

Their architectural responsibilities remain:

- Preserve conversational state, grounded responses, and artifact continuity.
- Keep quantitative execution reproducible and separate from interpretation.
- Simplicity and speed are favored over premature complexity.
- Systems should be modular enough to evolve without rewrites.
- Launch speed matters more than theoretical perfection.

---

# 2. Core Technical Principles

## Single Source of Truth

Persistent user and product state must live in one canonical system.

## Stateless Compute

APIs, AI orchestration, and execution workers should remain stateless whenever possible.

## Clear Boundaries

Each service must have a narrow responsibility.

## Contract Driven Development

Frontend and backend should integrate through explicit API contracts.

## Async Where Valuable

Use streaming or jobs only where they materially improve UX.

## Replace Complexity with Iteration

Prefer simpler architecture that can ship now.

## Document draft and preparation ownership

The default-off document lane follows the [capture contract](API_CONTRACT.md#document-capture-preparation-and-review).
`DocumentsService` saves supported source bytes and a draft in the existing
`financial_document_extractions` store before model work. The statement connection
ID is the shared identity for later Chat and Plan entry points. Source retention,
preparation state, observations and candidate delivery share that owner.

FastAPI background tasks dispatch persisted preparation intent. Connection leases
and draft versions fence work; interrupted in-flight attempts require explicit
recovery instead of automatic model retries. Prepared candidates enter existing
reconciliation. Retained observations and receipt itemization remain review data,
and only reconciliation confirmation through MoneyService writes financial activity.
Plan proposals grant no sharing or authority to change plan currency. No separate
ledger, draft store, OCR vendor or conversational runtime is introduced.

## Cuadrao action and integration principles

These principles constrain future assigned Cuadrao contracts. They do not declare
new APIs, business services or a replacement chat runtime implemented.

Screens, chat, jobs and external tools use the same canonical record and action
owners. A model can propose or explain an action. Validated domain services own
financial calculations, authorization and durable writes.

An approval applies to the reviewed revision, destination and action. Execution
rechecks current permissions and rejects a changed basis. Duplicate delivery
must not repeat a financial effect. An uncertain external result requires
reconciliation before resubmission, not a blind retry. Endpoint payloads and
idempotency behavior remain with the assigned [API contract](API_CONTRACT.md).

Fiscal integration follows the [partner-first decision](specs/argus-decision-log.md#fiscal-route).
Cuadrao-owned fiscal tooling remains a parallel direction. Canonical records and
business rules stay independent of provider adapters, so replacing a provider
does not replace the customer's records. This neither chooses the provider nor
authorizes live fiscal issuance. Regulatory eligibility and signing authority
need separate evidence for the selected route.

The blueprint's entities, queues, MCP tools and runtime mechanisms remain
proposals until their scoped technical contracts are approved. Its diagrams do
not authorize another active chat brain or decide Cuadrao's future agent runtime.

## Cuadrao reuse decisions

Founder-aligned October 4, 2026. Reuse the existing foundations below. This is
implementation direction, not proof of connected availability or permission to
enable a provider. [#826](https://github.com/lagarcess/argus/issues/826) owns the
bounded runtime contract and its migration plan.

| Foundation | Direction | What remains to deliver |
| --- | --- | --- |
| Render Workflows | Extend the existing backtest execution foundation to assigned import and export jobs. Receipt reads run in a plain background worker instead, as recorded below. | Separate task families, persisted product state, duplicate-safe effects, bounded retries and recovery after interruption. This extension is not already delivered. |
| LangGraph | Start from the existing orchestration and checkpointing foundation. | Define Cuadrao's state and action contract. Preserve the active Argus runtime until its authorized transition; do not start a second chat brain per client. |
| Mem0 and pgvector | Reuse the existing semantic-recall integration; retain Supabase/Postgres as the storage foundation rather than adding a second memory database. | Define Cuadrao recall scope, consent, correction, revocation, deletion and first-release availability in #826. The current adapter configures pgvector and returns canonical record IDs; this is code evidence, not hosted enablement evidence. |
| On-demand context injection | Retrieve the permitted records and memories needed for the current request. | Resolve retrieved IDs through current authorization and canonical records before model dispatch. Define bounded context selection and stale/deleted/revoked-result handling; similarity is not authority or financial truth. |
| Supabase and financial services | Keep identity, storage and canonical financial operations under existing owners. | Complete the approved space contract and share the same actions across manual and conversational entry points. |
| OpenRouter, Perplexity and Grok voice | Retain the [selected provider direction](specs/argus-decision-log.md#ai-providers). | Connect only assigned capabilities with shared consent and server-side credentials. Voice selection does not settle first-release inclusion. |
| Resend and Apple push | Keep Resend for approved email uses; use direct APNs for iOS push. | Deliver the assigned inbox/push journey with private payloads. Email templates do not expand consumer Updates or household invitation channels. |

React Email and react-pdf are candidates for their assigned template and business
PDF work, not new consumer launch dependencies. Specialist OCR needs evidence of
lower total correction effort and cost against the existing vision path.

Founder-locked clarification, October 4: LangGraph, Mem0/pgvector, scoped
on-demand context injection and Render Workflows are the starting stack for
Cuadrao's continuous agentic chat. Temporal, Inngest, Trigger.dev and Novu are
not additional launch dependencies. Evaluate a replacement or addition only
against a demonstrated unmet requirement in the assigned slice, including
recovery, approval waits or scheduling. Braintrust is optional evaluation and
tracing tooling; quality evaluation remains required without selecting it.
Reconcile any external trace content and retention before transmitting user data.
This lock supersedes the earlier blanket pgvector deferral for Cuadrao memory;
it does not authorize a general vector-search rewrite, provider activation or a
new runtime. No library license or copied application-code rights are established
by this reuse map.

Founder decision, November 1, 2026: receipt reads leave the API for a plain
background worker, `python -m workflows.document_worker`, which pulls from
Postgres. The unmet requirement is a concurrency cap: a Render Workflow starts
every run it is given and has no cap setting, so a burst of reads would need a
gate in the API. The worker holds one setting for reads at once. It is the only
reader: the API never runs one. The measurements and the order of
work live in [the receipt intake architecture](specs/cuadrao-receipt-intake-architecture.md).

Retirement inventories describe old tasks and configuration, not blanket deletion
of these foundations. Before removal, name current callers, the replacement
owner, retained state and migration evidence. A retired backtest task does not
retire Render Workflows; a retired chat route does not authorize deletion of
checkpoints or memory infrastructure needed by its successor. Preserve current
behavior until its authorized transition and verify secret consumers before
revocation or renaming.

## Agent Quality

The engineering rules that keep AI work grounded in this architecture live once,
in `AGENTS.md` under "Codebase rules" and "Checks". Do not restate them here (a
second copy drifts). This doc only adds architecture-specific emphasis: durable
facts come from product records, engine outputs, and provider-backed validation.
LLMs interpret and voice; they do not own truth.

---

# 3. Existing Client Surfaces

## Conversational Surface

### Chat Workspace

The existing conversational workspace. The MVEE defines its role alongside the other ecosystem surfaces.

Contains:

- conversation thread
- AI messages
- user messages
- starter prompts
- progress states
- result cards
- follow-up actions

## Retrieval and Account Surfaces

### Recents

Mixed chronological feed of:

- chats
- completed backtests
- durable idea/evidence activity

### Legacy Strategy and Collection Records

Retained only for owner-scoped historical reads. No dedicated UI, API router,
or write path remains; durable idea/evidence recall lives in Omnisearch.

### Settings

Preferences (language saved to the account, theme kept in the browser),
feedback, account actions.

---

# 4. High-Level System Topology

```text
Client (Next.js Web/PWA)
        |
        v
Frontend App Shell (argus-app / Render web service today)
        |
        v
API Control Plane (argus-api / FastAPI / Render)
        |
        +--> Supabase (Auth + Postgres + Storage)
        |
        +--> OpenRouter (LLM)
        |
        +--> Render Workflow (Backtest Execution Plane)
                |
                +--> Supabase Market Data Cache
                |
                +--> Market Data Provider (Alpaca / Kraken)
                |
                +--> Backtest Engine (Simulation Logic)
                |
                +--> Supabase Result Records
```

**Later Optional:**
- **Static/CDN Frontend Delivery**: only after a route/auth audit proves the app
  experience and authorization model remain intact.
- **Alternate Execution Backend**: always-on workers or external compute if
  Render Workflows do not meet reliability or cost needs.
---
# 5. Frontend Architecture

## Existing Alpha web surface

Three clients ship from this repository: the public website (`cuadrao-web`,
built from `marketing/`), the signed-in web app on staging (`cuadrao-web-staging`,
built from `web/`, Business only through `NEXT_PUBLIC_BUSINESS_ONLY_WEB`), and
the native iPhone app (`ios/ArgusFoundation/`). The
[Cuadrao launch boundary](specs/argus-minimum-viable-ecosystem-experience.md#consumer-and-business-launch-boundary)
owns the consumer iPhone and business web direction.

**Chosen because:**

- Fastest route to market
- Easiest iteration loop
- Shared codebase
- Mobile-accessible enough for alpha

## Approved Platform Direction

**Founder-locked September 26, 2026.** This section owns the interface stack
decision; other product and agent documents link here.

| Platform | Selected interface stack |
| --- | --- |
| iOS | Swift + SwiftUI, with UIKit where a component requires it |
| Android | Kotlin + Jetpack Compose, with Android Views where a component requires it |
| Web/PWA | Retain and evolve the existing Next.js + React + TypeScript app |

Mobile interfaces are platform-native implementations, not PWA/WebView shells.
React Native is not the selected mobile framework. Preserve the Argus visual
identity and product behavior while respecting each platform's navigation,
gestures, keyboard behavior, accessibility, and device capabilities.

All clients use the same Argus backend and canonical financial records,
permissions, calculations, and conversational runtime. Extend the existing
backend through shared contracts; do not create an independent financial or
chat truth for each interface. Existing web UI code does not automatically
become native UI; carry forward its design and behavior through explicit
native implementation and verification.

The founder accepts separate interface implementation and maintenance to gain
direct platform integration and control over interaction quality. Coordinated
agents may implement against shared specifications and acceptance criteria;
agent capacity does not replace device testing or integration review. Judge
quality on representative devices, including affordable and midrange Android
phones, rather than assuming the chosen framework guarantees performance.

This locks the platform stacks, not a new service topology or implementation
assignment. Client/API contracts, native authentication and guest continuity,
local storage/offline synchronization, device integrations, supported OS/device
ranges, financial-record and household design, ownership/task breakdown, and
rollout order still require scoped technical definition. No runtime, feature
gate, or production deployment changes are made by this decision.

### Voice and chart direction

**Founder-locked September 28, 2026.** This section owns provider and chart
library direction; [MVEE voice](specs/argus-minimum-viable-ecosystem-experience.md#43-speak-to-argus)
owns the experience. These are implementation choices to validate, not shipped
integrations or an authorization for paid calls or deployment.

- **Voice:** xAI is the selected provider direction for dictation, transcription
  and full spoken conversation. The proposed integration path is xAI streaming
  speech-to-text → existing Argus runtime → xAI streaming text-to-speech.
  LangGraph remains the single conversational owner; financial drafts,
  confirmation, permissions and durable records keep their existing owners.
  Direct speech-to-speech orchestration requires a bounded architecture review
  before adoption. The hosted Voice Agent Builder's separate reasoning,
  knowledge store and recording defaults are not adopted by this decision.
- **Charts:** Swift Charts for iOS, Vico as the Android Compose candidate to
  validate, and retained TradingView Lightweight Charts for web. Do not add a
  React Native stack for charting. Validate one representative financial chart
  before committing library versions or spreading the implementation.
- **Shared chart contract:** consume the same canonical series, units, dates,
  projection/actual distinction and missing-data semantics. Clients render and
  select points; they must not reconstruct financial calculations independently.
  Use a stable date/value readout, responsive scrubbing and restrained styling.
  Preserve actual jumps, gaps and flat periods rather than smoothing away facts.
- **Acceptance still required:** spoken Dominican Spanish and English, language
  switching, amounts and corrections, interruption/cancellation, disconnection,
  transcript/card consistency, privacy modes, retention and cost. Charts need
  scrolling/gesture coexistence, accessibility, theme and representative-device
  performance checks. Exact API contracts, credentials, versions, OS ranges and
  rollout remain scoped implementation work.

Sources checked September 28, 2026: [xAI voice APIs](https://docs.x.ai/developers/rest-api-reference/inference/voice),
[Voice Agent Builder](https://x.ai/news/grok-voice-agent-builder),
[Swift Charts interaction](https://developer.apple.com/videos/play/wwdc2023/10037/),
[Vico](https://github.com/patrykandpatrick/vico), and
[Lightweight Charts](https://github.com/tradingview/lightweight-charts).

## Frontend Responsibilities

- Chat UI
- Streaming responses
- Optimistic interactions
- Auth flows
- Surface navigation
- Rendering metrics/results
- Settings/preferences
- Local UI state

# 6. Backend API Architecture

## Primary Role

Thin orchestration layer.

The backend should coordinate systems, not become monolithic business chaos.

## Responsibilities

- Validate auth/session
- Route requests
- Persist data
- Call LLM provider
- Create durable backtest jobs
- Trigger execution workflows
- Hydrate job/result state from Supabase
- Stream responses
- Enforce quotas (Usage Counters)
- Enforce rate limits
- Enforce per-user and global backtest concurrency limits
- Enforce engine constraints
- Enforce asset_class coherence (Same-asset runs only)
- Expose clean APIs

## Non-Goals

- Rendering UI logic
- Storing long-term state in memory
- Becoming deeply stateful
- Importing or executing the heavy backtest stack in the API startup path

## Cuadrao Business and intake surfaces

The same FastAPI service hosts Cuadrao Business. Its routes live in
`src/argus/api/routers/business_*.py` and its domain in
`src/argus/domain/business/`, including the DGII fiscal profile, 606/607 export
and month close. Request and response shapes for month close are in
[the month-close contract](contracts/business-month-close.md).

Receipts reach a Business space by upload, by email (`/business/email` and the
`/webhooks/resend` webhook in `routers/email_intake.py`) and by WhatsApp
(`/webhooks/whatsapp` and `/whatsapp` in `routers/whatsapp.py`, default off).
Each arrives as a saved document draft. A read waits on its draft's row until
the document worker takes it. The worker,
`python -m workflows.document_worker` (`src/argus/domain/ingestion/documents/worker.py`),
is the only reader, and it runs the sweep. The API records the read and never
starts, imports or wakes a reader, so a burst of reads cannot hold up its
health check.

**Year check.** The reader often writes the wrong year. An issue date is a year
to check when the reader wrote it (origin `extracted`) and its year is not the
upload year: the year, in America/Santo_Domingo, of the `received_at` of the
draft's first source. A date from the QR or from a person is never checked.
Such a record stays out of Listos, in Por resolver with the reason
`check_details`. A single approval must name `check_details` and every other
gap in `accept_gaps`, and every gap must be confirmable. `year_to_check` in
`src/argus/domain/business/bandeja_group.py` owns the rule. The dossier carries
its answer (`upload_year`, `year_to_check`), and the review calendar offers the
date in the upload year from that answer. The web compares no years.

### Bandeja

What the person sees lives in
[the Business web app design](../.agent/designs/cuadrao-business-app/DESIGN.md#bandeja).
The server decides the group and the label of every Bandeja row. The web
renders them and decides neither.

- **One label owner.** `bandeja_label()` in
  `src/argus/domain/business/bandeja_group.py` gives every row one label:
  `reading`, `cant_read`, `needs_attention`, `ready` or `accepted`. Every row
  carries the same `bandeja_group` shape: `group`, `reason`, `label`,
  `draft_id` and `version`. Three builders in the same file make it.
  `group_of` makes it for receipts, called from
  `src/argus/api/business_receipt_activity.py`. `note_group` makes it for typed
  notes, called from `src/argus/domain/business/actions/captures.py`.
  `email_group` makes it for emails, called from
  `src/argus/api/routers/email_intake.py`. The web reads the label only in
  `rowLabel` (`web/components/business-app/recepcion/reception-model.ts`).
- **The group picks the tab. The label picks the word.** The group is
  `attention`, `listo`, `reading`, `eliminados` or null. Por resolver lists
  `attention`, Listos lists `listo` and Eliminados lists `eliminados`. Todos
  lists every row except a deleted one. `inbox_counts` in
  `src/argus/domain/business/receipt_activity.py` counts by the same groups.
  `RULE` in `bandeja_group.py` decides between `listo` and `attention`. The
  label follows the group. `attention` gives `cant_read` or `needs_attention`
  by the reason, `reading` gives `reading` and `listo` gives `ready`. A row
  with no group gives `accepted` when it was accepted, and a deleted row has
  no label. A receipt that is being accepted is `listo` with no `draft_id` and
  no `version`, so a second approval cannot name it.
- **Read failure and read held.** `READ_FAILURES` in `bandeja_group.py` holds
  `unreadable`, `ai_unavailable`, `interrupted`, `outcome_unknown`,
  `source_unavailable`, `read_deadline_passed` and `not_a_receipt`. Each gives
  `cant_read` in the `attention` group. `READ_HELD` holds `read_budget_day`
  and `read_budget_month`. Each gives the group and the label `reading`, like a
  read that still runs, so a held row shows only on Todos.
  [The API contract](API_CONTRACT.md) says how each count treats a held row.
- **Read-limit resume.** `ReadResume` in `workflows/read_resume.py` reads a
  held receipt again with no person. It runs in the document worker's upkeep,
  beside the Eliminados purge (`workflows/document_worker.py`). The sweep calls
  it every 30 seconds by default, and it works at most once every 10 minutes
  (`RESUME_EVERY`). A pass takes the receipts refused before `window_start` in
  `src/argus/domain/business/read_budget.py`, which is the start of the
  current Santo Domingo day or month. It queues each one through the path that
  "Leer de nuevo" uses. That path is `DocumentsService.queue` under the owner's
  reading setting, then `dispatch_preparation`. The pass sends
  `expected_version`, so it leaves alone a receipt that moved after the pass
  chose it, and two workers queue one receipt once. While extraction is off,
  the pass does nothing. The idle cost is one query every 10 minutes per worker
  against an empty partial index, plus the log line
  `Refused reads resumed due={} requeued={}`. The limits and the index live in
  [the data model](DATA_MODEL.md#business-read-budget).
- **Enviado por.** `SentBy` in `src/argus/domain/business/sent_by.py` is the
  one sender shape for every channel: `id`, `kind` (`member`, `email` or
  `whatsapp`), `person`, `address` and `phone_last4`. A sender carries only the
  field its kind names. Ids are `member:<user>`, `email:<address>` and
  `whatsapp:<link id>`, so one sender has one id on every row.
  `receipt_senders` gives each receipt its sender. A web upload gets the
  member on the first applied `receipt_upload` row. An email gets the sender
  of the earliest delivery that brought it. WhatsApp gets the number's link to
  this Business, and only its last 4 digits leave the server. A typed note
  sends its author (`member_sender`), and an email delivery sends its sender
  (`email_sender`). The web words a sender only in `sentByName`
  (`web/lib/sent-by.ts`), and the filter keys on `sent_by.id`.
- **Typed notes switch.** `business_typed_notes_enabled()` in
  `src/argus/domain/business/config.py` reads
  `CUADRAO_BUSINESS_TYPED_NOTES_ENABLED`, which is off by default. While it is
  off, `capture_note` in `src/argus/api/routers/business_manual.py` refuses a
  note that starts a draft with 404 `business_typed_notes_unavailable`, before
  it stores anything. A note on an existing draft is not refused.
  `GET /business/workspace` reports the switch as `typed_notes_available`.
  `ReceiptIntakeDialog.tsx` reads it through `businessTypedNotesAvailable` in
  `web/lib/business-api.ts`. Notes saved before still list.

### How a receipt becomes a record

A receipt goes through six steps. A later step trusts an earlier one in this
order. Each step has one owning file.

1. **The photo is stored as sent.** `objects.py` in
   `src/argus/domain/ingestion/documents/` keeps the original file. No step
   changes it.
2. **The DGII QR is decoded locally.** `dgii_qr.py` in the same folder reads
   the QR with a plain library, not a model. It tries the page as it is, then
   with more contrast, then at twice the size. When it reads a DGII link, the
   issue date, the supplier RNC, the e-NCF and the total in that link are
   exact.
3. **The reader model fills the rest.** The rules are the prompt in
   `extractor.py` and the field descriptions in `models.py`, both in the same
   folder. One photo of a receipt cut into pieces is one receipt. The issue
   date is the date labeled Fecha, Emitido or Fecha Emisión, never the date
   labeled Caduca or Válido hasta. The ITBIS amount is the amount printed next
   to ITBIS or Impuesto. The supplier RNC and the buyer RNC are separate
   fields. A read is complete when each fiscal field is found or is not
   printed.
4. **The values are merged.** `fill_from_qr` in `dgii_qr.py` does the merge,
   and `src/argus/domain/business/actions/mutations.py` calls it. A QR value
   replaces a reader value. A value that a person gave replaces both and is
   never overwritten.
5. **Checks flag what is unlikely.** `src/argus/domain/business/review_flags.py`
   sets the flags. `src/argus/domain/business/bandeja_group.py` keeps a flagged
   or incomplete record out of Listos, so a person reviews only those records.
6. **The person approves.** `src/argus/domain/business/actions/approval.py`
   records the approval. Nothing is approved without a person.

### When a receipt read fails

Designed 2026-11-15 with the founder and built in #2192. The design is sized
for pilot scale. What the person sees lives in
[the Business web app design](../.agent/designs/cuadrao-business-app/DESIGN.md#when-a-read-fails).
Each fact below has one owner in `src/argus/domain/ingestion/documents/`.

- **Transient or permanent.** `classify` in `failures.py` gives every failure
  its kind. The worker retries a timeout, an interrupted read, a 5xx answer and
  a 429 answer. After a 429 it waits at least the `Retry-After` time. It fails
  fast on an unreadable or unsupported file, a missing source file, a file that
  is not a receipt and an answer that came back wrong. It also fails fast on an
  auth or configuration error (401, 403, a missing model or key). That error
  writes an error log with the tag `document_read_config_alert` and the
  document id, because the fault is ours, not the receipt's.
- **Bounded, jittered backoff.** The numbers live in `config.py`, beside
  `PROVIDER_CALLS_PER_READ`. One read gets at most 4 provider calls in total
  (`MAX_PROVIDER_CALLS`). One take of a read still makes at most 2: the first,
  and one more at once when it times out. Every other retry waits in the queue.
  The wait starts at 15 seconds and grows 4 times for each call already made
  (15, 60, 240 seconds). Half of each wait is random. The waits of one read
  never add up to more than 10 minutes. A `Retry-After` that does not fit
  inside that total ends the read.
- **The wait is in the queue.** A take that failed for now puts the receipt
  back to `queued` with a `not_before` time on its `preparation_job`, in one
  write. No worker sleeps on it and it holds no read slot. `store.pull` skips
  it until that time. The count of calls (`provider_calls`) is written before
  each call, so a worker that dies does not reset it. The owner's "Leer de
  nuevo" starts a new read with a new count.
- **Dead letter.** When the calls run out, the receipt goes to Por resolver
  with its reason, the same failed state as before. That tab is the dead
  letter, and people already work it. The worker logs the final error as
  `document_read_failed` with the document id. There is no separate
  dead-letter queue.
- **Circuit breaker.** `breaker.py` owns the rules and
  `public.document_read_breaker` owns the state, one row. 5 failed provider
  calls inside 2 minutes stop all sends for 5 minutes. Then one read probes
  the provider: its answer closes the breaker, and its failure starts the 5
  minutes again. Only the probe moves an open breaker. Its admission carries
  the probe's id (`probe_id` on the row), and the call reports its end with
  that id. A call sent before the breaker opened, or a probe that was given
  up, carries no id or an old one, so its late answer does not close the
  breaker and its late failure does not start the 5 minutes again.
  Every admitted call ends at the breaker once, at one place
  (`AdmittedCall` in `breaker.py`, ended where `extract` returns in
  `service.py`). It has three ends. It failed for now: a failure.
  The provider answered: every other end of a sent call, including an answer
  that came back wrong, a refusal and a refused key (401, 403). It was never
  sent (the read budget or a lost lease stopped it after the admission): the
  probe gives its turn back, the breaker stays open and the next read probes.
  `provider_answered` in `failures.py` owns the line between a failure and an
  answer. A refused key is an answer: the provider is up, so the probe that
  gets one closes the breaker, and it never counts toward opening it. The key
  is ours to fix, and `document_read_config_alert` is its signal. A read the
  breaker held back was not admitted and reports nothing.
  Every worker and every new deploy read the same row. A read
  the breaker holds back goes back to the queue and is charged no call, no
  wait and no read budget. The breaker has no timer of its own. It changes
  only when a read asks to be sent or reports how its call ended. If the
  breaker row cannot be read, reads continue.
- **Read deadline.** A read still waiting in the queue 6 hours after it was
  asked for goes to Por resolver with the code
  `document_read_deadline_passed` (attention `read_deadline_passed`): the read
  waited too long with the service unavailable, and the receipt did not fail.
  `READ_DEADLINE_SECONDS` in `config.py` owns the 6 hours. `asked_at` on the
  `preparation_job` owns the start: the upload for the read an upload starts,
  and the owner's ask for a later "Leer de nuevo". The first try, a retry and
  a rerun after a dead worker do not move it. The worker's existing sweep
  (`read_expired` in `jobs.py`) checks it on the rows it already loads, so a
  read that a retry's wait, the open breaker or a stopped worker holds still
  expires. No new loop or timer runs. The sweep leaves a read alone once a
  worker took it. That read ends by its own answer, and a take that fails for
  now goes back to the queue, where the next sweep ends it. This code must not
  count against the owner's manual "Leer de nuevo" limit, which ships in
  #1681.
- **Idempotent writes.** Each extraction write is keyed by the document:
  `financial_document_extractions` has one row for each document, and the
  canonical Business bridge is keyed by the document's binding and checks the
  read hash that #2067 made stable. A retry writes into the same row and never
  adds a second one. Tests prove it in memory and on Postgres.
- **Escalation, not blind retries.** A read that returns a wrong answer is not
  retried. The review checks catch it. When the automatic calls run out, the
  next step belongs to the person, as the web design says. A second model is out
  of scope until it has its own receipt scorecard.
- **Concurrency and budget unchanged.** The worker keeps 3 reads at a time
  (`max_reads=3`), and uploads keep 3 in flight. A worker that pulls a read
  while the breaker is open puts it straight back in the queue, so the breaker
  sits in front of those shared read slots. An idle worker does not read the
  breaker.
  Every provider call, a retry included, is charged to the Business read budget.

### The record dossier

The dossier is the one view of a record, opened from the Bandeja or from
Registros. What the person sees lives in
[the Business web app design](../.agent/designs/cuadrao-business-app/DESIGN.md#receipt-detail).
Request and response shapes are in `docs/API_CONTRACT.md`.

**The server owns every value, every editable field and every link.**
`dossier` in `src/argus/domain/business/actions/dossier.py` builds the whole
payload, `BusinessDossier` in `src/argus/domain/business/contracts/dossier.py`,
and `GET /business/drafts/{draft_id}/dossier` returns it. The web keeps no copy
of a rule. After each save the server answers with the new dossier, and the web
replaces the one it held.

The payload fields that the dossier screen reads:

| Field | What it says | Owner |
| --- | --- | --- |
| `facts`, `net_amount` | The record's values. `net_amount.source` is `read`, `calculated` or `edited`. `net_amount.calculated` is the Subtotal the server calculates, whatever the source. | `facts_of`; `net_amount` in `purchase_review.py` |
| `dgii` | The 606 or 607 declaration. On an open expense with none saved, it is the declaration that an approval would write. | `written_from` in `amount_inheritance.py` |
| `inheritance` | The linked state of each fiscal field: `{field, value, inherited, paired_with}`. `field` names the source fact, `value` is the source value to restore, and `inherited` is false after a person overrides the field. | `inheritance_state` and the `INHERITANCE` map in `amount_inheritance.py` |
| `dgii_calculated` | `{billed_amount, itbis_advance}`: the two amounts the 606 calculates and no person enters. Null for a sale and for a record with no 606 declaration. | `purchase_calculated` in `dgii_validation.py`, which the 606 line also reads |
| `facts_editable` | Whether the caller may write to this record now: `prepare` on an open draft, `prepare` and `approve` on an accepted record. | `dossier` |
| `editable_fields` | The fields the caller may change through review in the current state. Empty for a caller that is not a person. | `_editable_fields` in `actions/dossier.py` |
| `declaration_editable`, `document_type_editable`, `payment_split_editable` | Whether the caller may write the 606 answers, the Compra or Venta type, and the 607 payment split. | `takes_purchase_declaration` and `takes_payment_split` in `purchase_review.py` |
| `declaration_suggestions` | One suggestion, with its source, for each 606 answer the person has not given. | `review_sources` in `actions/dossier.py` |
| `bandeja_group`, `listo_gaps`, `confirmable` | The Bandeja label, every reason the record is not in Listos in rule order, and the reasons a person may accept over. | `bandeja_group.py` |
| `review_flags`, `rnc_registry_status` | The checks on the amounts and numbers, and what the DGII register says of the RNC. | `review_flags.py`; `supplier_registry_read` in `actions/dossier.py` |
| `amounts_check` | Whether Montos adds up: `adds_up`, `difference` with the amount left over, or `unchecked`. | `amounts_check` in `review_flags.py`, which the `amounts_mismatch` flag also reads |
| `note_kind` | The note the record is: `credit`, `debit` or null. | `record_note` in `fact_blockers.py`, on the type table in `fiscal_identity.py` that the 606 and 607 checks read |
| `source_owned_fields` | The declaration fields that always follow their source, so their row is read-only: a purchase's Tipo de ID, and Propina legal. | `source_owned` in `amount_inheritance.py` |
| `history` | Every saved revision with its before and after. | `business_draft_revisions` |
| `approval_available`, `approval_action`, `delete_available`, `restore_available` | The actions the caller may take now. | `dossier` |

**One owner per fact.** The list row and the dossier read the same owner for a
shared fact. The pill is `bandeja_group.label`, from the same `group_of` rule
that labels the Bandeja row. The reasons are `listo_gaps`, and the approve
route reads that same rule again inside its transaction. A linked value comes
from `inheritance_state`, and the 606 and 607 export the saved declaration
without recomputing a link. `dgii_calculated` and the 606 line both call
`purchase_calculated`, so the two amounts match the line.

**The server enforces what it offers.** `editable_fields` and the `*_editable`
flags describe what a write will accept. They are not the guard. Every write
goes through `PATCH /business/drafts/{draft_id}/review`, or the approve route,
with the draft `version`. The server checks the permission, the version and the
review rules again, and refuses a stale version with `stale_version`. An
override or a restore of a linked field travels as `montos.override_inherited`
or `montos.restore_inherited` in that same review request.

**The web renders only.** `ReceiptDossierReview.tsx` loads the dossier and
passes it down. A row has a pencil when `editable_fields` names it. A row shows
the link icon when its `inheritance` entry has `inherited` true, and it shows
the restore button when that entry has `inherited` false. While the fiscal form
holds an unsaved change, the web asks
`POST /business/drafts/{id}/amounts-preview` what each linked field would show.
The same answer carries `dgii_calculated` for that unsaved draft.
It does not work the value out. The web adds no amounts, compares no years and
decides no status.

A fiscal row has no pencil when `source_owned_fields` names it. NCF modificado
shows when `note_kind` is set, and the refund question when it is `credit` on
a purchase. The Total shows its check on `amounts_check.state` `adds_up`, and
the difference on `difference`. The Subtotal shows ƒ while `net_amount.source`
is `calculated`, and the way back to it once the source is `edited`.

The web does hold layout. `dossier/fiscal-rows.ts` decides which card a fiscal
field sits in, the row order, and the fields the Datos fiscales tab leaves
out. A field that the server lists and that file does not name still shows.

One known gap remains between this rule and the code:

- The web does not read `dgii_calculated` yet, so the dossier does not show
  Total facturado or ITBIS por adelantar.

---
# 7. Communication Protocols

## Chat Messaging

**Preferred MVP Transport:** SSE (Server Sent Events)

**Use for:**

- AI token streaming
- Progress updates
- Request-scoped stage updates
- Partial explanations

**Why:**

- Simpler than WebSockets
- Ideal for one-way streaming
- Lower implementation overhead

## Backtest Job Status

**Private-Alpha Transport:** API polling on durable job rows now; Supabase
Realtime is the selected target once the first workflow-backed path is stable.

**Use for:**

- queued/running/succeeded/failed/canceled/expired job updates
- result-card hydration after the chat request has ended
- refresh/reload recovery from durable state

API SSE remains request-scoped. Do not hold long-lived API streams open for
workflow-duration backtests.

## Standard Request / Response (REST)

**Use for:**

- Auth
- Settings
- CRUD operations
- History
- Run requests
- Detail fetches

## Deferred: WebSockets

Only introduce later if required for:

- Collaborative sessions
- Many concurrent background jobs
- Persistent live market feeds

# 8. Stateful vs Stateless Systems

## Stateful Systems

### Supabase

Canonical state store.

**Owns:**

- Users
- Profiles
- Preferences
- Legacy onboarding state (inert compatibility JSON on old profile rows)
- Conversations
- Messages
- Durable chat-turn lifecycle records
- Legacy Strategy and Collection rows (read compatibility only)
- Backtest jobs
- Backtest history
- Computed answers (a tool result card and its computation marker on an
  assistant message; no run)
- Archived / deleted records
- Feedback records

### Market Data Cache

Temporary performance state owned by Supabase first. It accelerates repeat
provider reads across users and workflows, but it is not the source of truth for
portfolio results, persistence, or quotas.

**Owns:**

- Fresh market data snapshots keyed by provider, asset class, symbol, timeframe,
  data window, and schema version
- Expiry metadata based on market/timeframe clocks
- Cache hit/miss evidence for job execution metadata

## Stateless Systems

### API Layer

Request in -> response out. Decomposed into focused routers (`api/routers/auth`,
`conversations`, `backtest`, `agent`, and supporting product routers). The
`api/main.py` registers routers and contains no business logic.

### AI Orchestrator (Stateless Per Request)

Build prompt → call LLM → parse response → validate facts → route.
- **Rule**: Orchestrator memory is reconstructed per turn from the LangGraph checkpointer (backed by Supabase `AsyncPostgresSaver` in production, `MemorySaver` in development).
- No in-process session state is stored outside the checkpointer. `InMemorySessionManager` is not used.
- One LLM call per turn for intent classification. Downstream calls (explain, clarify, name suggestion) are permitted but do not reclassify intent.

### Execution Workflow (Stateless)

The runtime compute process that executes simulations. In the private-alpha
target architecture this is a Render Workflow task, not the API process. It
loads pandas/numpy/vectorbt/numba and the backtest engine only for the lifetime
of the job.

### Backtest Engine (Domain Logic)

The simulation logic (Numba/Python) that calculates metrics and returns results.
It remains domain code in the monorepo, but the production runtime boundary is
the workflow execution plane. Execution realism (trading fees + slippage) is
modeled in the engine behind `ARGUS_ENABLE_EXECUTION_REALISM`. The capability is
active by default, while modeled costs remain opt-in per idea. An explicit
`false|0|off|no` value is the kill switch and preserves the pre-realism cost path
byte-identical, so evidence artifacts stay reproducible across the flag boundary.

*Stateless systems should scale horizontally later.*

# 9. Third Party Systems

### Supabase

**Use for:**

- Auth
- Database
- Row Security
- Storage (if needed)
- Realtime job status updates

### OpenRouter

**Use for:**

- Chat intelligence
- Strategy extraction
- Explanations

### Market Data Provider

**Use for:**

- Historical price data
- Supported symbols

Provider ownership:

- Alpaca is primary for equity and crypto availability.
- Kraken public REST complements coverage for currency pairs and crypto fallback.
- Provider-specific windows are execution truth. Kraken OHLC returns only the latest 720 candles per interval, so the runtime must ask the user to shorten the request or widen the timeframe when the requested window cannot be served.
- Backtests remain single asset class per run: `equity`, `crypto`, or `currency_pair`.

### PostHog (Server-Side Product Analytics)

**Use for:**

- Measurement-only product analytics for the closed event registry
  (`src/argus/observability/analytics_events.py`): the wave 1 events and the
  Business pilot's six events (`src/argus/domain/business/analytics_events.py`,
  sent by `src/argus/domain/business/analytics.py`). `docs/DATA_MODEL.md`
  section 12.1.1 lists every event and property. The sink re-validates each
  event against the registry and refuses anything else.
- Aggregate funnels, retention, and loop-health questions, and per-Business
  document volume, read cost and correction rates for pricing.
- Unhandled API and document read exceptions, as class name, route or job,
  hashed actor and stack frames only (`capture_exception` in
  `src/argus/observability/envelope.py`).

**Do not use for:**

- Frontend autocapture or session replay.
- Person profiles.
- Feature flags or product behavior decisions in this slice.

### Observability Stack

Minimal but critical for Alpha stability.

- **Logs**: Structured logs (Loguru) sent to service provider logs.
- **Request Tracking**: `X-Request-Id` headers across all flows.
- **Error Alerts**: Error monitoring (e.g. Sentry) for exception tracking.
- **Latency Monitoring**: Request-time tracking for API and Engine.

# 10. Canonical Product Objects

Argus does not have one canonical object. It has multiple first-class objects.

- **User**: Identity + preferences.
- **Conversation**: A thread representing one isolated idea journey.
- **Message**: A unit inside a conversation.
- **Strategy definition**: A supported executable template + parameters used in
  conversational drafts and immutable run configuration, not a saved-record
  surface.
- **Backtest Run**: Immutable simulation result.
- **Legacy Strategy / Collection record**: Owner-scoped historical data kept
  read-compatible without a current create, manage, or navigation surface.
- **Asset**: Supported symbol/instrument metadata (includes `asset_class`).

Authenticated profile language is product state, not browser state. Signup
validates the selected language and creates the profile with its server-derived
locale in the same server-owned path. Login and reload hydrate the
authoritative profile before rendering the authenticated application.

The language a visitor sees is decided in this order: the account's saved
language once signed in; else a choice saved on the device (the one `i18nextLng`
key); else the default, which is `es-419` on a Cuadrao Business build that ships
Spanish and `en` otherwise. The browser's language is a logged-out hint on a
consumer build only; a Business build never reads it. The auth page offers the
other language by its own name; a press switches at once and the choice is saved
on the account at sign-in. A key the shown language lacks is read from that
language's own chain (`en` for English readers, `es-419` then `en` for Spanish
readers), and both locale files carry the same keys, which a test enforces.

# 11. Conversation Model

## Multi-Chat Required

Each conversation is isolated.

**Reasons:**

- Cleaner context windows
- Lower memory leakage
- Easier retrieval
- Idea-oriented UX
- Better organization

## Memory Boundary (Alpha)

**AI may use:**

- Current thread history
- User profile/preferences

*AI should not depend on unrelated thread memory.*

> [!TIP]
> **Global Rule**: Historical Collection rows may contain mixed asset classes.
> Backtest runs may not mix asset classes operationally, and no current flow
> creates or manages Collections.

## Conversational Runtime Architecture

The agent runtime is a **LangGraph `StateGraph`** executing a pipeline of named stages. The graph is the execution contract. No routing logic exists outside the graph's conditional edge functions.

### Tool Stack

| Tool | Role | Scope |
|---|---|---|
| **LangChain** (`langchain_openrouter`, `langchain_core`) | LLM call layer | `ChatOpenRouter`, `.with_structured_output()`, `.ainvoke()`, `SystemMessage`/`HumanMessage`/`AIMessage` types |
| **LangGraph** (`langgraph.graph`, `langgraph.checkpoint`) | Graph execution layer | `StateGraph`, `checkpointer`, `astream_events()`, thread-scoped state |

These responsibilities are absolute and do not cross. Routing is not implemented inside LangChain calls. Session persistence is not implemented outside the checkpointer.

### Pipeline (Per Turn)

```
HTTP POST /api/v1/chat/stream (SSE)
    │
    ▼
[Pre-flight] Auth validation, quota check (stateless, no LLM)
    │
    ▼
[LangGraph: astream_events()]
    ├── [interpret]  LLM classifies intent, extracts strategy fields, detects semantic_turn_act.
    │                Post-LLM validation only: symbol resolution, asset parity, date limits,
    │                missing required fields. → streams stage_start event immediately.
    │
    ├── [clarify]    if needs_clarification → LLM generates context-aware question.
    │                No hardcoded prompt templates. → streams question tokens.
    │
    ├── [confirm]    if ready_for_confirmation → deterministic confirmation card assembly.
    │                → streams stage_outcome event; frontend renders card.
    │
    ├── [execute]    declaration policy gates the actual callable before any launch payload.
    │                Local calls return immediately; backtests retain confirmation and jobs.
    │                → streams declaration-owned tool_progress with typed argument facts.
    │
    ├── [explain]    backtest success → LLM generates result narrative from metrics.
    │                Direct tool answers use their typed result/card binding without this call.
    │                → streams explanation tokens.
    │
    └── [next_step]  LLM suggests follow-up actions. → streams next-step chips.
    │
    ▼
[checkpointer] Persists WorkflowState to Supabase (AsyncPostgresSaver) or memory.
    │
    ▼
SSE stream: done event with final payload
```

### Executable tool declarations

`domain/capability_registry.py:get_tool_catalog` is the catalog assembly point.
Each declaration binds a real callable's typed argument and return models to its
description, cross-argument rules, domain and units, failure semantics, execution
cost, confirmation callback, progress template, and versioned card presenter.
Its schema, catalog text, runtime dispatch and result projection derive from
those declarations. Availability derives from the existing feature-flag owner.
Strategy templates retain their registry and unsupported-admission checks.

The interpreter's system prompt, seven intents and response schema remain
unchanged. Catalog-driven model selection is parked for roadmap decision 9.
The existing validated Run action calls the declared backtest with its canonical
`StrategySummary`; the same confirmation owner checks the approved inputs.
Unapproved direct calls return `confirmation_required`, and one approval cannot
authorize a second backtest. Research declarations expose the typed query and
shape supported by the existing service, preserving its routing and retrieval
contracts. This lane adds no question-to-tool classifier or production calculator.

The callable's models generate a closed nested input tree for schema and runtime
validation. Unknown fields are rejected at their owning level; explicit maps
retain their declared openness. Legacy models retain their read behavior.
Neutral `domain/tool_contracts.py` transports import no catalog or backtest code;
serializer-pinned model paths remain unchanged. Outcomes distinguish `succeeded`,
`invalid`, `ambiguous`, `bounded`, and `unavailable`. Unsuccessful outcomes cannot
carry an answer. Cross-argument blank rules count `None`; zero remains known.

`tool_result_cards` and per-call `tool_jobs` retain each call's identity through
streaming, publication, worker completion and reload. Existing workers, quota,
cost ledger and persistence owners remain authoritative. The card presenter owns
display facts while the callable owns the typed result. Local editable tools
recompute through the guarded message-artifact writer: the original unknown
stays blank and the input revision advances with the result. Public sharing
freezes a computed answer's card as its own `calculation` leaf through the
shipped selected-turn contract.

A computed answer is an artifact without a run. The answering model, the
research provider or the no-search voicing answer, returns its prose and one
typed calculation request with each input's source; the runtime holds every
input to that source, computes in process, fills the prose's figures from the
card and publishes it, and the one marker owner
(`argus.domain.computation_marker`) writes `metadata.computation` from it. Every
later reader derives from that pair and nothing else: a decision stores its
inputs and re-runs the declaration's one compute function, Search projects an
answer dossier and counts results under an asset, the conversation rail ticks a
result, comparison lines up two cards' typed facts in Python, continuing copies
the card into a new chat, and sharing freezes it. None of these creates a
backtest run, a job, an evidence artifact or a strategy. The only paid read is
a refresh of cited inputs the user starts, which goes through the research
allowance and the cost ledger like a turn.

### Registered in-process calculations

`get_calculation_declarations()` in
`src/argus/domain/calculations/__init__.py` is the only catalog of free
calculations. Do not restate that inventory here: names, count, and modules
belong to that owner. Each registered calculation is local, never confirmed,
and recomputes in process through its own compute function. CI derives the
live set from the same owner (for example
`tests/test_calculation_kernels.py` parametrizes over
`get_calculation_declarations()`), so a new registration cannot leave a
hand-maintained doc table behind.

Open product work that is not yet registered in that catalog, including
candidates under PR #634, is out of scope for this architecture summary until
it lands in `get_calculation_declarations()`.

Recovery preserves the current question's ownership. When interpreter candidates
fail, focused strategy repair requires a typed strategy read from that same turn;
an outage, a ticker, or a pending test cannot supply that intent. An unread turn
keeps the interpreter-unavailable recovery and retry contract. Likewise, the
current interpretation must identify an answer to a pending need before it can
block knowledge or arithmetic; the previous `await_user_reply` alone cannot.

Inline research attempts share the active turn's remaining deadline. The lookup
ladder reserves the normal knowledge-voicing timeout (at most half the remaining
turn) for the existing answer-without-lookup path, and bounds both the provider
transport and its async wait. The turn also owns a single-use call reservation
for that recovery answer, so interpreter retries cannot consume its last attempt.
A cancelled sync provider may still finish remotely,
so its admission charge is retained and its late result is never published or
cached. Interpreter-unavailable copy names failed question understanding in both
locales without assuming the user requested a test.

Progress is a declaration locale key with typed arguments, emitted when that
call executes. Graph-stage events retain operational meaning and cannot select
product prose. A stage without tool progress renders a neutral loader. This
path requires no extra model call.

### NLU Ownership Rule

The LLM is the **only NLU layer**. Deterministic code validates facts it cannot know — it does not classify intent, detect approval signals, or generate user-facing text.

Structured action chips are not natural-language NLU shortcuts. They enter LangGraph as explicit product operations attached to the current confirmation or result artifact. Normal user text still reaches the structured LLM interpreter before routing decisions.

| Layer | Owns |
|---|---|
| LLM (interpret node) | Intent, task_relation, semantic_turn_act, strategy field extraction, social/approval/education detection, assistant_response |
| Deterministic (post-LLM) | Symbol resolution via `domain/market_data.resolve_asset()`, asset class parity check, date range limit check, missing required fields check |

No regex gate intercepts a user message before the LLM sees it. No hardcoded natural language string competes with the LLM's response in any stage file.

User-facing prose is language-agnostic by construction. The runtime keeps no
per-language copy tables: LLM-authored prose is written in the detected turn
language, degraded/recovery copy renders from typed codes, and result chrome
renders from typed keys the frontend localizes (B4, #154). English/Spanish parity
is proven by the eval harness, not hardcoded. See `docs/CONVERSATIONAL_RUNTIME.md`
— "Language-Agnostic Prose Composition".

### Session State Rule

`TaskSnapshot` is the authoritative in-turn state. It stores only non-derivable fields:
- `pending_strategy_summary` — strategy under construction
- `confirmed_strategy_summary` — strategy approved for execution
- `last_stage_outcome` — what the runtime last did
- `latest_backtest_result_reference` — artifact pointer to last completed run

Derived state (missing fields, pending needs, field provenance) is computed fresh each turn from `pending_strategy_summary`. It is never persisted.

### Durable Chat-Turn Lifecycle Ownership

Supabase owns the current durable lifecycle of every accepted non-backtest chat
turn; LangGraph continues to own semantic runtime state through the checkpointer.
The lifecycle record answers whether accepted work is still running or reached
a durable terminal outcome. Chat turns admitted under `chat.run_backtest` use
the durable `backtest_jobs` lifecycle instead, so the two records do not compete
to own one execution. The chat-turn lifecycle does not store conversation
meaning, route the graph, queue work, or replace messages.

The chat request boundary durably creates `accepted` with the user message. The
runtime worker moves it to `running`. Terminal assistant persistence owns
`completed`, while the existing terminal-runtime-failure guard owns
`recoverable_failed`. A server-side reconciler, invoked on the next chat POST
and conversation-message read, owns stale `abandoned` or `reconciled` outcomes.
SSE delivery and the frontend never own these transitions: a lost response is
transport ambiguity until durable state proves otherwise. Exact transition and
read semantics live in `docs/API_CONTRACT.md` under
`contract-chat-turn-lifecycle`; the current-state persistence shape lives in
`docs/DATA_MODEL.md` section 8.1.

### Conversation Activity and Read Projection

The API combines `chat_turn_lifecycles`, conversation-scoped `backtest_jobs`,
fully finalized Run/evidence truth, and `conversation_read_states` into one
activity projection. Operation state and attention state are independent: a
task can be working while an older completion is still unseen. The frontend
renders this typed projection; it does not scan prose or infer completion from
transport events.

Conversation and History pages project activity only after pagination, in one
owner-scoped batch of at most 100 task ids. Reads may reconcile at most 20 stale
turns using the existing lifecycle evidence predicate, but never advance read
state. Mark-read mutations lock and revalidate the referenced terminal source
before advancing the monotonic boundary. Activity reads and mutations do not
change `conversations.updated_at`, previews, ordering, or list cursors.

### Conversation Artifact Continuity

Conversation text is input, not state truth. Once a confirmation card, result
card, saved strategy, or failed-action artifact exists, every subsequent turn
must first resolve the active artifact anchor before interpreting the user
message as a new task.

Artifact anchors are resolved in this order:

1. The structured action payload attached to the user turn.
2. The latest active confirmation card in the same conversation.
3. The latest completed backtest result referenced by the turn or conversation.
4. The latest retryable failed-action artifact, if the user is retrying that
   failure.
5. No artifact anchor, which means the turn starts a new idea.

After an anchor is resolved, the runtime builds the working draft from the
artifact's canonical configuration (`confirmation_payload`, completed
`backtest_run.config_snapshot`, saved strategy state, or failed-action launch
payload). The LLM may interpret the user's messy text as a patch over that
draft, but omitted artifact fields must carry forward. A date-only edit cannot
erase assets, contribution amount, cadence, timeframe, benchmark, or strategy
type that were already canonical in the anchored artifact.

The deterministic guardrail layer applies the patch and validates the resulting
draft. If the patched draft is executable, Argus emits a new confirmation card.
If required information is genuinely missing, Argus asks a targeted
clarification. Generic guidance such as "try next" must never replace an
artifact-patch response when the user is attempting to modify or rerun a known
setup.

Failure and retry artifacts follow the same rule. A retry button represents one
specific failed action and payload. Later turns that create a new active draft,
new confirmation, completed result, or explicit cancellation must supersede or
expire stale retry affordances so the user never has to guess what "Retry" will
do after reload.

# 12. Strategy Architecture (Alpha)

## Controlled Template System

Users speak freely. AI maps requests into supported templates.

**Example:**

User says: *"Buy Tesla after oversold dips."*

Mapped internally to:
```json
{
  "template": "rsi_mean_reversion",
  "symbol": "TSLA",
  "rsi_threshold": 30
}
```

## Why This Model

- Reliable execution
- Lower hallucination risk
- Simpler engine integration
- Faster shipping

# 13. Backtest Execution Flow

1. User requests simulation in chat
2. API validates request (symbol set, **asset_class parity**, and quota)
3. AI extracts supported strategy config if needed
4. API creates a durable `backtest_jobs` row with status `queued`
5. API triggers a Render Workflow with a compact job id or payload reference
6. Workflow marks the job `running`
7. Workflow reads fresh market data from Supabase cache or fetches from provider
   on cache miss
8. Strategy kernel produces raw signals
9. Execution reducer applies long-only position state, cash, sizing, and policy
   constraints
10. Engine computes metrics and chart markers from executed fills only
11. The shared typed finalizer idempotently commits the immutable run, Idea,
    IdeaVersion, EvidenceArtifact, and enriched result-card identity as one
    logical operation. Local/in-process execution uses this same boundary.
12. Workflow marks the job `succeeded` only after finalization returns the
    complete identity and links `result_run_id`; a recoverable finalization
    failure uses the existing `failed` status with
    `failure_code = finalization_failed` and `retryable = true`.
13. Supabase Realtime notifies the browser of job status changes.
14. The server reconciles a completed asynchronous job to its canonical
    finalized result before the chat UI hydrates durable Supabase records. The
    result, evidence, and decision identities therefore survive reload; reload,
    history, and search cannot expose partial or client-reconstructed state.
15. The finalized run appears in history.

The execution ledger is the boundary between strategy logic and result
presentation. Signals are diagnostics until they become order intents and fills.
Long-only runs must ignore exit signals while flat and duplicate full-position
entries while already long. Chart markers, trade counts, win-rate inputs, and
user-facing trade explanations consume fills, not raw triggers.

For the current Alpha architecture, `domain/engine_launch` is the sufficient
engine adapter boundary. Product surfaces consume canonical run and evidence
contracts rather than engine-native output. Do not add a formal multi-engine
plugin interface until a second validated engine or workflow creates a concrete
need; that abstraction belongs to the later engine-leverage experiment.

# 14. Search Architecture

## Global Search

Alpha search is implemented using **Postgres Full-Text Search (FTS)** + recency + pin boost.

**Ranking Criteria:**
1. Pinned boost (explicit user intent)
2. Exact title/name match
3. Symbol match
4. Recency (updated_at)
5. Basic text relevance

## Deferred Direction

The global Search surface retains SQL/text search. A vector-search replacement
is not part of this launch assignment. This boundary does not prohibit reuse of
the existing Mem0/pgvector adapter for scoped Cuadrao memory under the
[reuse decision](#cuadrao-reuse-decisions). Memory recall and global Search have
different owners and acceptance criteria.

## Structured Recall Versus Memory

P2 continuity comes from owner-scoped `Idea`, `IdeaVersion`,
`EvidenceArtifact`, `DecisionNote`, conversation, and run records in Supabase.
That structured recall is not memory. Current production availability for
personalization memory (flag, role gate, semantic recall) and its approved
transition are owned by
[PRODUCT.md Current production availability and planned changes](PRODUCT.md#current-production-availability-and-planned-changes).
Other docs link there rather than restate rollout state. Memory must not be
required for the idea/evidence/comparison loop.

# 15. Deletion / Archival Model

## Soft Delete Preferred

Use soft-delete patterns where practical.

**Supports:**

- Recently deleted
- Recovery UX
- Analytics continuity

## Archive Preferred for Chats

Chats may be archived without loss.

# 16. Security Model

## MVP Priorities

- Secure auth flows
- Row ownership enforcement
- Protected private user data
- Safe API boundaries

## Defer Complexity

- Enterprise roles
- Team accounts
- Advanced permissions

# 17. Scalability Philosophy

Design clean seams now, not heavy systems now.

## Good Now

- Stateless APIs
- Explicit contracts
- Render Workflow execution boundary
- Supabase-backed market data cache
- Durable job status
- Normalized data model

## Later

- Autoscaling workers
- Queue systems
- Advanced quotas
- Distributed tracing
- Realtime fanout systems
- **Mixed-Asset Support**: Deferred until custom benchmark and complex allocation systems exist.

# 18. Deployment Shape

Simple, scalable, and practical Alpha hosting.

- **Frontend**: current Next.js Render web service; static/CDN only after a
  route/auth audit proves it preserves the app experience and authorization
  boundary.
- **Backend**: Render Web Service (FastAPI).
- **Database/Auth**: Supabase (Postgres + Auth).
- **Backtest Execution**: Render Workflows for pay-per-run execution.

Private-alpha release validation is governed by the founder-approved contract in
`docs/specs/private-alpha-release-integrity-contract.md`. One checked-in
machine-readable profile owns non-secret API, web, workflow, locale, capability,
and canary expectations. Candidate SHA is a runtime input, not profile content.
The profile is authoritative for desired release mode: release validation fails
if `render.yaml`, live Render configuration, or effective API/web/workflow mode
disagrees. Fast local memory/synthetic/mock-auth execution is useful development
evidence but cannot substitute for production-parity Supabase/Postgres/real-auth/
live-provider/Render-Workflow evidence.
The release manifest records the profile hash, environment fingerprints,
deployed service SHAs, and full real-user Spanish signup-to-evidence-to-decision-
to-recall canary evidence for that same candidate.

## Guest Identity and Policy Boundary

Supabase Auth owns both permanent and anonymous identities. Anonymous users
receive the ordinary `authenticated` Postgres role; verified Auth truth
(`is_anonymous`) plus an active `guest_workspaces` row determines guest status.
Editable profile metadata, browser state, and the frontend flag never determine
authorization.

One request-scoped typed account context is the server policy owner for guest
capabilities, fixed expiry, and lifetime allowances. The existing conversation,
LangGraph, message settlement, and backtest-admission paths remain the only
runtime and accounting owners.

Two server flags own separate policy boundaries:

- `CUADRAO_GUEST_ACCESS_ENABLED` defaults on; explicit `false` is the emergency
  bootstrap kill switch.
- `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=false` in production separately
  controls ordinary permanent-account access, so production is invite only.
  Staging sets it to `true` for internal use. Unlike the guest flag it fails
  closed when unset, so an environment that omits it denies public registration.
  The production rule in `scripts/ops/staging_env_manifest.json` owns the value.

`NEXT_PUBLIC_GUEST_ACCESS_ENABLED` also defaults on and selects presentation
only; explicit `false` restores the preserved auth-first landing. An explicit
client/server disagreement fails closed. With the flag false, as in
production, the allowlist owns signup and login admission: only an email with an
active row enters, and a disabled row still refuses it. When the flag is true,
the allowlist owns role elevation and explicit denial only, and an absent row no
longer blocks. With the flag false and `CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED`
true (default false; production keeps it false), the Business invitation and grant tables admit exactly the email a live
invitation or grant on an open Business names; a disabled allowlist row still
refuses it, and an email admitted only that way cannot start a Business or
invite anyone.
Turning the server guest flag off stops bootstrap only: active verified guests
drain through their fixed expiry or conversion instead of being abruptly
deauthorized.

Cleanup is a bounded privileged database operation. It locks the Auth identity
and workspace, removes an eligible conversation graph, guest feedback text,
and matching LangGraph checkpoint thread, then deletes the anonymous Auth row
inside that same transaction. Claimed source identities receive a
reconciliation grace and are deleted only after the transferred graph has zero
remaining source owners. This closes the cross-system check/delete race and
cannot delete a converted or permanent account.
Append-only cost and route/security evidence may remain only with privacy-safe
nullable attribution. No hosted Supabase setting is changed by the feature
branch.

# 19. Failure Handling Standards

## AI Failure

User must still receive graceful fallback and retry path.

## Engine Failure

Show honest error + preserve conversation.

## Market Data Failure

Retry or explain temporary issue.

## Partial Failure

Never leave user confused.

# 20. Implementation Dependency Order

### Layer 1: Truth Layer
- `PRODUCT.md`
- `ARCHITECTURE.md`
- `API_CONTRACT.md`
- `DATA_MODEL.md`

### Layer 2: Runtime Foundation
- Auth
- Conversations
- Messages
- Persistence

### Layer 3: Intelligence Layer
- Starter prompts
- Extraction prompts
- Response streaming

### Layer 4: Engine Layer
- Templates
- Execution
- Metrics
- History

### Layer 5: Polish Layer
- Search
- Feedback
- Feature flags

# 21. Architecture Decision Filter

When choosing any technical path, ask:

> *Does this preserve the separation between deterministic simulation truth, LLM-owned language, and contextual intelligence?*

If not, it likely should wait.

# 22. Agent Runtime Decision Filter

When writing any code that touches `agent_runtime/`, ask:

1. **Does this add a regex, localized stop-word/alias table, display-label token matcher, or early-return gate before the LLM call?** If yes, stop. Move language interpretation to the LLM system prompt or consume typed action metadata instead.
2. **Does this store derived state in `TaskSnapshot`?** If yes, stop. Compute it fresh from `pending_strategy_summary` instead.
3. **Does this add natural language strings to a stage file?** If yes, stop. The LLM generates the response; stage files orchestrate only.
4. **Does this use `.invoke()` on the graph in production?** If yes, stop. Use `astream_events()` instead.
5. **Does this write session state outside the checkpointer?** If yes, stop. The checkpointer is the only session store.
6. **Does this add a second LLM call for intent classification?** If yes, stop. One classification call per turn.

If the answer to any of these is "yes", the change reintroduces the brittleness the runtime remediation exists to eliminate.
