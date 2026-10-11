# Cuadrao Business agent: execution spec from conversation to accountant

**Status:** founder-approved direction, October 10, 2026 (America/Chicago).
This document is a plan. It does not claim built behavior. It authorizes no
hosted action, no live WhatsApp message, no paid model call and no merge.

**Base branch:** `codex/private-alpha-next`, reconciled at
`35fae200034c51ef27cee64d76adc4a903c19672`. The default-off Business foundation
and planning PRs #900 and #910 are integrated. The local sandbox at
`df208f7ec2379cd84efd55eea0deb685d67c5360` is separate audit evidence.
This documentation landing does not publish or merge that sandbox or #925.

**Tracker:** [#942](https://github.com/lagarcess/argus/issues/942). Flow
issues: #943 to #949.

**Language:** ASD-STE100. Short sentences. One instruction for each sentence.

## 1. The goal

A business owner with no accounting knowledge sends each transaction to
Cuadrao in WhatsApp. Each transaction takes seconds. The accountant receives
organized, accounting-ready records. Each uncertainty is visible.

These are the transaction types:

- Fiscal receipts.
- Cash purchases with no receipt.
- Personal spending mixed into the business.
- Income, transfers, owner money, credit purchases and loans.

## 2. The finish line

The finish line is a complete, traceable period. The accountant accepts the
period as sufficient to prepare the required financial statements. Each
remaining uncertainty is visible, with a next action and a responsible person.

Two people judge success:

- A novice owner captures a representative month without accounting help.
- The accountant prepares the agreed statements. The accountant does not
  rebuild a transaction that the package already explains.

The goal is alignment and clarity between a client and its accounting firm.
The test is the accountant's acceptance. Banks are not part of this scope.

## 3. Decisions

### 3.1 Locked decisions

| ID | Decision | Date |
| --- | --- | --- |
| L1 | One agent works in the conversation and uses the Cuadrao tools. It completes each record in one short conversation. A queue of saved messages is not a complete record. | 2026-10-10 |
| L2 | The agent talks only to the owner in version 1. The accountant works in the web view. The agent does not send WhatsApp messages to the accountant. | 2026-10-10 |
| L3 | Reuse the existing runtime and services. Do not add a second agent loop, extractor, ledger, permission system or vendor. | 2026-10-10 |
| L4 | WhatsApp is the first customer channel. The conversation is the owner's interface. The web view that matters first is the accountant's view. | 2026-10-10 |
| L5 | Write the contract first (section 6). Then the streams in section 8 work in parallel against the contract. | 2026-10-10 |
| L6 | The first proof is the "Pagué 850" journey (section 9, J1). No polish work starts before J1 passes end to end. | 2026-10-10 |
| L7 | Evals gate the merge. Unit tests alone do not. | 2026-10-10 |
| L8 | Jev and a separate MCP server are deferred. An MCP adapter can come later. It must call the same tools and the same authority checks. | 2026-10-10 |
| L9 | Branch Cuadrao work from `codex/private-alpha-next`. `main` stays as the Argus tribute. | 2026-10-10 |
| L10 | "I paid with my own money" is recorded against an "owner funds" source in the shared money service. The accountant decides if it is a capital contribution or a debt to the owner. | 2026-10-10 |
| L11 | Approval is a permission, not a fixed role. The business admin holds it. The admin can grant it to an associate. An accounting firm gets it for each client through that client's grant, so a firm can manage a portfolio of clients. The agent never holds it. Each action goes into an action ledger that shows who did it, through which grant and for whom (section 6.9). | 2026-10-10 |
| L12 | The OpenRouter key caps AI spend. Cuadrao adds no spend guard of its own. Before a PR makes model calls, the founder names the models for it (section 3.4). | 2026-10-10 |
| L13 | The default currency is DOP. A draft marks a defaulted currency so the reviewer can change it before sign-off. | 2026-10-10 |

### 3.2 Defaults

No decision is open. Each item below has a default. Change a default only when
real use shows a need or a critical risk.

| ID | Item | Default |
| --- | --- | --- |
| D1 | The accountant's package | A CSV and an Excel file, with the receipts attached. Add a QuickBooks connection only if the pilot accountant uses QuickBooks. |
| D2 | Who answers the owner | The AI agent answers each message. No person answers on the Cuadrao side. AI is on for each pilot business. |
| D3 | The agent's replies | No person approves the words. The model follows the platform policies and the Cuadrao prompt rules. Evals measure behavior: the correct record, the correct question and no invented facts. No word lists and no regex. |
| D4 | Tax numbers on receipts | J2 reads RNC, NCF or e-CF, and ITBIS. Each value is "not verified" until the admin or an authorized associate signs off. This is not tax filing. |
| D5 | The WhatsApp 24-hour window | The agent replies within seconds of each owner message, so each reply is inside the window. The window limits only a message that Cuadrao starts after 24 hours of owner silence, for example a reminder. Those messages use Meta-approved templates after #941. |

### 3.3 Build now, build later

Product-market fit comes from real owners and a real accountant using J1 to
J3. It does not come from complete coverage. Build only the "now" list. Start
an item from the "later" list only when real use asks for it.

**Now:**

- P0, C0 (only the shapes that J1 to J3 need), T1, W1 and E1 (scripted J1).
- M1: income and owner funds only.
- A1: one record page with the sources, the action ledger, the open questions
  and an approve button.
- X1, so that J2 reads the tax numbers (default D4).
- A CSV and an Excel file for the accountant, with a funding column and the
  receipts (default D1).
- Then put J1 to J3 in front of one real owner and one real accountant.

**Later:** M2, V1, K1 beyond the CSV and Excel files, R1, J4 to J8, and the formal
E2 and E3 tests.

### 3.4 PRs that make model calls

Tell the founder before each of these PRs makes a model call. The founder
names the models.

- T1: the live scorecard for the new model-facing text.
- E1: the live J1 case.
- X1: the extractor change.
- V1: transcription.

## 4. What we keep

These protections are correct. Each stream keeps them. Each acceptance test
checks them.

- Cuadrao keeps the original evidence and its source. Corrections make new
  revisions. The original does not change.
- Cuadrao saves the item before it says "received".
- A repeated delivery does not record money a second time.
- Businesses stay separate. Personal and Business data stay separate.
- Cuadrao keeps an unknown fact as unknown. It does not invent a value.
- Approval binds the exact record revision. A later edit needs a new approval.
- Capture and preparation do not change balances. Only an approved record
  changes balances.
- Untrusted text never selects the business and never starts an approval.

## 5. How the agent works

### 5.1 The model reads and the tools enforce

The model reads the owner's message. It proposes what to do. The server runs
the tools. The tools check permissions, approval state, exact money values and
record-once rules.

The current runtime does not use model tool calling. The model returns one
structured interpretation. Server code turns the interpretation into tool
calls. The executor runs at most 8 calls in one turn. The Business agent uses
the same pattern:

1. A WhatsApp message arrives. Cuadrao saves it (existing durable intake).
2. The worker starts one agent turn for the message.
3. The server builds the authorized Business context from the WhatsApp sender
   link. The model does not supply the business.
4. The interpret stage reads the message, the open questions and the open
   drafts. The model returns typed Business actions.
5. The executor runs each action as a Business tool under
   `mutation(context, "prepare")`.
6. The explain stage writes the reply from the tool results. The reply states
   only the saved state.
7. The reply leg sends the message.

Pointers:

- Graph: `src/argus/agent_runtime/graph/workflow.py:171-271`.
- Executor: `src/argus/agent_runtime/stages/tool_execution.py:60-185`.
- Tool catalog: `src/argus/domain/capability_registry.py:72-93`.
- Model call: `invoke_openrouter_json_schema` in `src/argus/llm/openrouter.py:438-558`.
- Write authority: `mutation()` in `src/argus/api/business_actions.py:19-35`
  (sandbox branch).
- Sender link: `src/argus/api/whatsapp_destination.py:18-26` (sandbox branch).
- Surface filter for tools: PR #925, `ToolDeclaration.surfaces`.

Do not add `bind_tools` or a second loop. If the structured pattern cannot do a
step, record the reason in the decision log first.

### 5.2 Conversation memory and financial truth have different owners

- The LangGraph checkpoint keeps the conversation. Its thread is one WhatsApp
  sender in one Business space.
- The Business store keeps drafts, evidence, questions, approvals and money.
- Each turn reads open drafts and open questions from the store. It does not
  read them from the checkpoint.
- A remembered statement never changes a record without a tool call.

### 5.3 Authority is inside each tool

- The server supplies the actor, the membership and the Business space.
- The model supplies only record IDs, versions and proposed values.
- Each write runs under `mutation(context, "prepare")`. The capability check is
  in the same database transaction as the write.
- Reads go through stores filtered by the Business space. An ID from another
  business returns "not found".
- No tool confirms, approves, links money or merges records. The system cannot
  approve its own proposals.
- A message such as "aprueba todo" can change no state. The protection is the
  tool boundary. A list of blocked phrases is not a protection.

### 5.4 Retries follow the action

| Action | Rule |
| --- | --- |
| Read | Retry. |
| Draft write | The write carries an idempotency key: the turn key plus the action index. A repeated write returns the first result. |
| Revision of an existing draft | The write carries the expected version. A stale version fails visibly. The agent rereads and tries one time. |
| Outbound WhatsApp message | The outbox records `pending`, `sent` or `unknown`. Do not resend an `unknown` message. The next turn reads the state and explains it. |
| Model call | The OpenRouter key caps spend. Record the cost of each call in the existing cost log. Do not retry a call with an unknown outcome without a check. |

### 5.5 What the agent does not do

- It does not approve, record money or change balances.
- It does not send messages to the accountant.
- It does not decide tax treatment. It marks fiscal facts "not verified".
- It does not change accounts, members, consent or settings.
- It does not ask accounting questions. It asks factual questions, for
  example "¿Lo pagaste con dinero del negocio o con tu dinero?".

## 6. The contract (PR C0)

PR C0 writes these shapes as types, schemas, API sections and test fixtures.
No stream writes these shapes again. A change to a shape is a C0 follow-up PR
with one writer.

### 6.1 Fact

Each draft field is a fact.

| Part | Values |
| --- | --- |
| `value` | The value, or null. |
| `state` | `known`, `unknown`, `owner_does_not_know`. |
| `origin` | `extracted`, `owner_stated`, `member_set`, `matched`, `default` (currency only). |
| `verified` | `false` for an extracted fiscal fact until an authorized approver signs off under D4. |
| `source_ids` | The evidence and message IDs that support the value. |

One fact can have a default. If the owner names no currency, `currency` is DOP with origin `default`. The reviewer sees the default and can change it before sign-off. No other fact has a default. A value with no source stays `unknown`.

### 6.2 Activity draft

The draft is the existing candidate row (`financial_import_events`) with one
resolution and one version. C0 extends the resolution:

- `kind`: a fact. Values are in 6.4.
- `amount` and `currency`: facts. Money uses exact decimals.
- `occurred_on`: a fact. The period uses this date, not the upload date.
- `counterparty`: a fact.
- `funding`: a fact. Values are in 6.4.
- `business_share`: a fact. Values are `all`, `none` or a partial amount.
- `receipt_state`: a fact. Values are `fiscal_receipt`, `informal_receipt`,
  `no_receipt` or `unknown`.
- `fiscal`: optional facts for RNC, NCF or e-CF, and ITBIS (default D4).
- `source_ids`: one source for each message and each attachment.
- `review_state`: the existing review states.

C0 adds one source kind for agent proposals. A note or a WhatsApp text can then
become a draft. This change removes the exclusion in
`candidate_eligibility.py:14-15`.

### 6.3 Revision

C0 adds a revision record. Today the audit row stores field names only. It
does not store old values.

| Part | Meaning |
| --- | --- |
| `draft_id`, `version` | The draft and its new version. |
| `actor_id`, `actor_kind` | The person. `actor_kind` is `owner_via_agent`, `member` or `extractor`. |
| `grant_id` | The grant that allowed the action. |
| `changes` | For each field: before, after, origin and source IDs. |
| `turn_key` | The agent turn, if an agent turn made the change. |
| `created_at` | The time. |

WhatsApp, the web view and the accountant write to the same revision history.
There is no second history.

### 6.4 Kinds and funding

`kind` values. J1 to J4 need the first two. The money stream adds the others.

- `expense`, `income`.
- `transfer`, `refund`.
- `owner_contribution`, `owner_withdrawal`.
- `credit_purchase`, `payable_payment`.
- `loan_received`, `loan_payment`.
- `unknown`. An unknown kind stays visible for the accountant. It is never
  changed to `expense` without a source.

`funding` values:

- `business_account` with an account ID.
- `owner_funds` (decision L10).
- `unknown`.

### 6.5 Open question

| Part | Meaning |
| --- | --- |
| `question_id` | The ID. |
| `draft_id`, `field` | The draft and the fact the question resolves. |
| `asked_of` | `owner` or `accountant`. |
| `channel` | `whatsapp` or `web`. |
| `state` | `open`, `answered`, `owner_does_not_know`, `waiting_for_window`, `withdrawn`. |
| `answer_source_id` | The message or web action that answered it. |

Rules:

- The agent asks the owner one question at a time.
- An answer of "no sé" sets the fact to `owner_does_not_know`. The draft stays
  in the period. The question moves to the accountant.
- The turn context lists the open questions. The model names the
  `question_id` that a reply answers. The tool checks that the question is
  open and belongs to the same Business space.

### 6.6 The seven Business tools

Each tool is a `ToolDeclaration` with `surfaces={"business"}`. Each tool calls
an existing service where one exists.

| Tool | Does | Wraps | Writes |
| --- | --- | --- | --- |
| `business_read_context` | Reads the space, open drafts and open questions. | `workspace`, `inbox`, `overview` in `service.py:88-102,581-599` | No |
| `business_propose_activity` | Creates a draft, or revises a draft at an expected version. | `ReconciliationService.resolve` in `reconcile/service.py:124-169` | Draft, revision |
| `business_attach_source` | Links a message or an attachment to a draft. | New link from source to draft | Draft, revision |
| `business_propose_allocation` | Proposes `funding` and `business_share`. | New. Uses 6.4. | Draft, revision |
| `business_find_related` | Finds possible duplicates and matching money. It only proposes. | `activity_matches` in `matching.py:237-259`, `duplicates.py` | No |
| `business_ask` | Opens a question for the owner or the accountant. Requests review by a member who holds the approve permission. | New open-question record | Question |
| `business_explain_status` | Reads the saved state of a draft or a record. | Status fields, dossier and history in `routers/business_authority.py:206-225` | No |

Pointers without a directory are under `src/argus/domain/business/` or
`src/argus/domain/ingestion/` on the sandbox branch.

### 6.7 Turn key and conversation

- `turn_key` is the WhatsApp `provider_message_key`. It is unique. A repeated
  webhook delivery finds the same turn.
- The durable row has these phases: `captured`, `turn_running`,
  `turn_done`, `reply_pending`, `reply_sent`, `reply_unknown`.
- After a restart, the worker continues from the saved phase. Tool writes
  converge because of the idempotency keys in 5.4.
- The worker processes one message at a time for each sender in each space.
  Messages from one sender run in arrival order.

### 6.9 Action ledger

The action ledger is the trust layer. The owner, the associate and the
accountant can read it. Each entry answers these questions:

- Who acted, and in which business?
- Through which grant? Who gave the grant?
- For whom? Example: "Ana (Contadores RD) for Taller de prueba".
- What changed: the record, the version, and the old and new values.
- From which source: a message, a photo or a web action.
- When.

Proposals, answers, approvals, grants and revocations all go into the ledger.
The revision history (6.3) and the existing Business audit events feed it.
There is no second history.

### 6.8 Model-facing text

The Business fields in the interpretation schema and each tool description are
model-facing text. AGENTS.md rule 12 applies. Each change needs a committed
scorecard. The extractor prompt `_PROMPT` in
`src/argus/domain/ingestion/documents/extractor.py` is not under the prompt
fingerprint today. PR X1 adds it before any change to it.

## 7. Gap register

Each gap has one owner PR and one flow issue. Gaps 1 to 17 come from the
first audit. Agents checked them again on October 10 at `df208f7ec`. N1 to N8
are new.

| Gap | Verdict | Owner PR | Flow |
| --- | --- | --- | --- |
| 1. Notes are excluded from review | Confirmed | C0, T1 | #945 |
| 2. WhatsApp text cannot complete a transaction | Confirmed | C0, T1, W1 | #944 |
| 3. Approval accepts expenses only | Confirmed. Four sites force `expense`: `service.py:408,557`, `approval.py:79-81`, `ledger.py:28-31`. | M1 | #947 |
| 4. No personal and business allocation | Confirmed | C0, M1, T1 | #946 |
| 5. No credit purchase or later payment | Confirmed | M2 | #947 |
| 6. No fiscal fields | Partly wrong. Extracted and corrected values are already separate. RNC, NCF and ITBIS are missing. | X1 | #945 |
| 7. No timed novice-owner test | Confirmed | E2 | #942 |
| 8. Manual entry needs re-entry and account choice | Partly wrong. The backend requires account and date. The web fills them in plain view. "Paid from" lists business accounts only. | T1, M1 | #946 |
| 9. No question, reply and correction journey | Confirmed | C0, T1, W1 | #946 |
| 10. No completeness check against statements | Confirmed. The matcher exists in `matching.py:237`. | R1 | #949 |
| 11. No opening cash or cash count in Business | Confirmed. The money service supports both. Business drops the amount. | R1 | #943 |
| 12. No opening position | Confirmed | R1 | #943 |
| 13. The export omits notes and other kinds | Confirmed | K1 | #949 |
| 14. The export uses the upload date | Confirmed | K1 | #949 |
| 15. The export has no version or freshness | Confirmed | K1 | #949 |
| 16. The export stops at 100 receipts or 50 MiB | Confirmed | K1 | #949 |
| 17. No proof that the accountant can use the package | Confirmed | E3 | #949 |
| N1. No Business tools exist. #925 declares none. | New, blocker | T1 | #945 |
| N2. WhatsApp never starts an agent turn | New, blocker | W1 | #944 |
| N3. Two messages cannot join one draft | New | C0, T1 | #946 |
| N4. An agent proposal has no source kind | New | C0 | #945 |
| N5. "Mío" cannot be recorded, and the export shows no payer | New | M1, K1 | #947 |
| N6. A question after 24 hours is dropped | New | W1 (default D5) | #944 |
| N7. "850" has no currency source | New | C0 (decision L13: default DOP) | #943 |
| N8. `manual_capture.require_processable` has no callers | New, low | T1 deletes it | #945 |

Other findings:

- Business chat resolves the business through the old owner-only lookup
  (`conversation_surface.py:45-56`). T1 replaces it with the authorized
  context.
- The #925 dollar guard is for tests only. L12 owns the spend decision.
  T1 records cost and preserves bounded calls and retries. It adds no new
  Cuadrao dollar cap.
- Audio is dropped when the webhook is parsed (`payload.py:112-114`). No
  transcription code exists. V1 adds it.
- WhatsApp has no ordering for each sender (`durable_store.py:201`). W1 adds
  it.

## 8. Work streams and PRs

### 8.1 Order

1. P0. Use the integrated default-off foundation and the landed #900/#910
   plans. Before runtime work, identify any missing sandbox dependency and
   scope its reconciliation separately. Do not publish the sandbox wholesale.
   This docs-only landing neither selects nor implements a runtime subset.
2. C0. The contract. One writer.
3. T1, M1, W1, A1 and E1 start in parallel against C0. Each uses the C0
   fixtures for the parts that are not built.
4. J1 passes with a scripted model. Then J1 passes with the live model.
5. X1, V1 and M2 start after J1.
6. K1 and R1 start after M1. E2 and E3 run after K1.

Codex coordinators land each PR. Claude sessions build and open PRs. They do
not merge.

### 8.2 File boundaries

| PR | Writes only |
| --- | --- |
| C0 | `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`, `src/argus/domain/business/contracts/` (new), one migration, `tests/fixtures/business_agent/` |
| T1 | `src/argus/agent_runtime/` Business parts, `src/argus/domain/business/tools/` (new), `candidate_eligibility.py`, the interpretation schema, its scorecard |
| M1, M2 | `src/argus/domain/recording/`, `src/argus/domain/business/approval.py`, `ledger.py`, `service.py` recording calls |
| W1 | `src/argus/domain/ingestion/whatsapp/`, `src/argus/api/whatsapp*.py`, the durable store |
| A1 | `web/components/business-app/`, `web/lib/business-api.ts` |
| E1 to E3 | `tests/`, `tests/evals/`, `docs/reports/evidence/cuadrao-business-agent/` |
| X1 | `src/argus/domain/ingestion/documents/`, `tests/interpreter_prompt_surface.py` |
| V1 | `src/argus/domain/ingestion/whatsapp/` audio parts, a transcription adapter |
| K1, R1 | `src/argus/domain/business/export.py`, period and reconciliation services |

If a PR must write outside its row, stop. Agree the change with the owner of
that row first.

### 8.3 PR C0: write the contract

**Depends on:** P0.

**Build:**

1. Write the types in section 6 as Pydantic models.
2. Write the migration for revisions, open questions and the agent source
   kind.
3. Write the API sections for the accountant view and the agent turn.
4. Write fixtures: one fixture for each tool response, for J1 and J2.

**Verify:**

- The types reject an illegal state. Example: a fact with `state=known` and no
  `source_ids` fails.
- The migration applies and rolls back on local Postgres.
- Consumer tests pass.

### 8.4 PR T1: build the Business tools and bind the context

**Depends on:** C0.

**Build:**

1. Bind `AuthorizedBusinessContext` into the turn. Replace the owner-only
   lookup.
2. Declare the seven tools with `surfaces={"business"}`.
3. Add the typed Business actions to the interpretation schema.
4. Remove the note exclusion in `candidate_eligibility.py`.
5. Delete `manual_capture.require_processable`.

**Verify:**

- A tool call with an ID from another business returns "not found".
- The interpretation "aprueba todo" makes no approval and no money record.
- A repeated tool write with one idempotency key makes one revision.
- The scorecard for the new model-facing text is committed (rule 12). The
  Personal suite shows no regression.

### 8.5 PR M1: record income and owner-funded purchases once

**Depends on:** C0.

**Build:**

1. Remove the four `expense` hardcodes.
2. Add `owner_funds` as a funding source in the shared money service.
3. Record `income` through the existing money kind.

**Verify:**

- An approved owner-funded expense makes one record and no change to a
  business bank balance.
- Replay of the same approval makes no second record.
- Consumer money tests pass. Record the Consumer compatibility proof.

### 8.6 PR W1: connect WhatsApp to the agent

**Depends on:** C0. Defaults D2 and D5.

**Build:**

1. Add the turn phases in 6.7 to the durable row.
2. Start one agent turn after capture, keyed by `turn_key`.
3. Process messages for each sender in order.
4. Allow more than one reply for each message. Add the outbox states.
5. If the business has no AI consent, keep the fixed acknowledgement.
6. If the 24-hour window is closed, set the question to `waiting_for_window`.

**Verify:**

- The same webhook delivered three times makes one turn and one reply.
- A process kill during `turn_running` continues after restart. The end state
  is one draft and one reply.
- Two messages from one sender run in arrival order.
- Transport is simulated. Label it in the evidence.

### 8.7 PR A1: build the accountant view

**Depends on:** C0. Builds against C0 fixtures until T1 and M1 land.

**Build:** one record page that shows these items:

- The sources: messages, photos and their original text.
- The revisions, with old and new values and the actor.
- The open questions, with the responsible person.
- The approvals, bound to versions.
- A way for the accountant to answer a question and to set a fact.

**Verify:**

- The page shows only backend state. It invents no state.
- An accountant edit and a WhatsApp reply write to one revision history.
- Desktop, keyboard and touch checks pass. The Spanish-first approval rule applies to fixed UI copy only. Generated
  replies follow D3 and E1, without approval of each reply.

### 8.8 PR E1: make J1 a merge gate

**Depends on:** C0. Runs against fixtures until T1 and W1 land.

**Build:**

1. A scripted-model test of J1. Copy the pattern in
   `tests/test_issue_440_cancelled_draft_dates.py:48-251`.
2. A live-model case with the models the founder names. Commit its scorecard
   under
   `docs/reports/evidence/cuadrao-business-agent/`.

**Verify:** the test asserts stored state, not reply text:

- One draft. Its version goes up with each answer.
- `funding=owner_funds`, `receipt_state=no_receipt`, `amount=850`,
  `currency=DOP`.
- The original messages are linked.
- No money record exists before a member with the approve permission approves.
- After approval, one money record exists.

The scripted test runs in CI on each PR. The live case runs before each merge
that changes model-facing text.

### 8.9 Later PRs

| PR | Does | Depends on |
| --- | --- | --- |
| X1 | Adds RNC, NCF or e-CF, and ITBIS to `ReceiptDetails`. Puts `_PROMPT` under the fingerprint first. Needed for J2. | J1, D4 |
| V1 | Accepts WhatsApp audio. Keeps the original audio. Transcribes it through OpenRouter. Gives the text to the agent. Tests Dominican speech. | J1 |
| M2 | Adds transfers, refunds, owner withdrawals, credit purchases with later payment, and loans. | M1 |
| K1 | Builds the period package (section 10). Uses `occurred_on`. Adds a version and freshness. Removes the 100-receipt limit with continuation. | M1, D1 |
| R1 | Adds opening position, opening cash, cash count and the completeness check against statements. | M1 |
| E2 | Runs the timed novice-owner test on real phones. Needs #941 for real WhatsApp. | J4 |
| E3 | Runs the accountant workflow test on one month (J8). | K1, R1 |

## 9. Journeys

Each journey is an acceptance test. Each starts in WhatsApp and ends in the
accountant's package. Each must survive a restart and a repeated webhook
delivery.

| ID | The owner sends | Cuadrao must |
| --- | --- | --- |
| J1 | "Pagué 850 de materiales." Then "Mío. No tengo recibo." | Ask "¿Con dinero del negocio o tuyo?". Make one expense draft with `owner_funds` and `no_receipt`. Get approval from an authorized member. Record it once. Put it in the package with its messages and the accountant action "receipt missing; verify supplier status and applicable fiscal document". |
| J2 | A photo of a fiscal receipt with a caption. | Extract the amount, the date, the supplier, RNC, NCF and ITBIS as "not verified". Ask only for missing facts. |
| J3 | "Me pagaron 5,000 por la reparación." | Make one income draft. Ask for the account if it is not known. |
| J4 | A receipt with business and personal items. | Propose the business share. Record only the business part. Flag the split for the accountant. |
| J5 | A voice note that says J1. | Keep the audio. Produce the same end state as J1. |
| J6 | "No sé" to a question. | Keep the draft in the period. Move the question to the accountant. |
| J7 | The same receipt photo two times. | Propose a duplicate. Record money one time only. |
| J8 | A representative month. | Include transfers, owner money, a credit purchase with a partial payment, a loan, a late receipt and a correction after export. Reconcile bank and cash. The accountant accepts the period. |

## 10. The accountant's package

Status: the long-term field list. Start with default D1. The research summary
is in Appendix A.

The package has three parts:

1. A sheet in the DGII Formato 606 column order for purchases, and one in the
   607 order for sales. Cuadrao fills the fields that evidence supports. The
   accountant fills the fields that need judgment.
2. A general journal CSV that an accounting system can import.
3. The original evidence, with links from each row.

A business on the simplified regime (RST) does not send 606 or 607. The
journal CSV and the evidence still apply.

For each row:

- Kind, date, amount, currency.
- Counterparty, RNC or cédula when known.
- NCF or e-CF and ITBIS when known, marked "verified" or "not verified".
- Funding: business account, owner funds or unknown.
- Business share.
- Receipt state.
- Category proposal, marked as a proposal.
- Accountant action, when one applies. Examples: "issue a B11 or E41 for an
  informal supplier and withhold the ITBIS", or "cash payment over RD$50,000".
- Links to each source.
- Revision, approver and approval time.
- Open questions and their responsible person.

For each period:

- Package version and creation time.
- Opening position, and who supplied it.
- Totals for each currency and each kind.
- The bank and cash reconciliation, with each unresolved difference.
- Records changed after the last export.

## 11. Measurements

E2 and E3 measure these values. The founder sets the targets.

- Owner time for each transaction, from the first message to a complete draft.
- Owner messages and agent questions for each transaction.
- Failed attempts.
- Questions open for more than 24 hours.
- The rate of correct uncertainty resolution, against accountant labels.
- Transactions that the accountant must type again, and minutes for each
  period.
- Model cost for each transaction.

## 12. Boundaries

These items are out of scope for this spec:

- Fiscal issuance, filing, sales invoicing and collections.
- WhatsApp messages to the accountant.
- Approval in WhatsApp.
- Template messages before #941 closes.
- A separate MCP server, Jev or a new model vendor.
- Broad visual polish. Removing steps that block J1 to J8 is in scope.
- Hosted deploys, real WhatsApp messages and paid calls without a separate
  founder approval.

## 13. Blockers and preconditions

1. **Runtime reconciliation is separate work.** P0 uses the integrated
   foundation. The sandbox contract at
   `docs/specs/lanes/cuadrao-business-sandbox-contract.md` is a local-only
   historical source at `df208f7ec`, not a published integration contract.
   Use this spec and the [landed space plan](cuadrao-business-space-slice-plan.md)
   for published direction. C0 defines the future shared contract.
2. **#925 remains excluded.** Plan the per-surface filter inside T1, through its canonical tool
   catalog. This avoids making the excluded PR's refusal wording and eval
   guard a dependency. Reuse from #925, if useful, needs scoped review and
   T1's required scorecard. This documentation landing does not repair or merge #925.
3. **#941 blocks real WhatsApp delivery.** Fixture and simulated proof can
   continue.
4. **Holds from the handoff.** The October 10 decision lifts "Business chat
   stays off". Business chat is a future implementation surface in this plan. This PR changes documents only. Hosted pilot activation uses server flags after J1 passes and the founder approves. Hosted actions, live calls and merges stay held
   until then.

## 14. Documents this spec changes

- `docs/DOCUMENTATION_AUTHORITY.md`: the Business workflow row names this spec.
- `docs/specs/argus-decision-log.md`: the October 10 entry.
- `docs/handoffs/cuadrao-business-lane.md`: a note on the lifted holds.
- `docs/specs/lanes/cuadrao-whatsapp-intake.md`: a pointer. Its rule
  "WhatsApp never queues AI preparation" changes when W1 lands.
- `docs/API_CONTRACT.md` and `docs/DATA_MODEL.md`: PR C0 changes them. This
  spec does not.

## Appendix A. Accountant research

Research on October 10, 2026, from DGII, bank and regulator sources. Items
marked "not verified" need a check with the pilot accountant.

**Formato 606 and 607.** Each has 23 detail fields. Both are due on the 15th
of the next month, also with no activity.

- A photo can give the supplier RNC, the NCF, the date, the amounts, ITBIS,
  ISC, the legal tip and often the payment method.
- Only the accountant decides the purchase type, the split between goods and
  services, each withholding field, and the ITBIS treatment.

**NCF and e-CF.**

- A paper NCF has 11 characters: "B", a 2-digit type and an 8-digit sequence.
- An e-NCF has 13 characters: "E", a 2-digit type and a 10-digit sequence.
- A B02 consumer receipt does not support an ITBIS credit or an ISR deduction.
- The DGII portal checks validity. Cuadrao marks each value "not verified"
  until an authorized approver signs off under D4.

**Missing receipts and supplier status.** A missing receipt does not establish
that a supplier is unregistered. J1 records the missing receipt and leaves supplier status unknown for the
accountant. Norma 05-2019 Article 7 requires registry verification for its
Comprobante de Compras treatment and specifies retention of invoiced ITBIS.
The accountant determines whether B11 or E41 applies. The June 2025
consultation concerns a bakery buying inputs from state farmers-market
sellers without NCF. It is not a ruling on every receiptless purchase. Sources:
[Norma 05-2019](https://dgii.gov.do/legislacion/normasGenerales/Documents/NG%20sobre%20Comprobantes%20Fiscales/Norma05-19.pdf)
and [DGII Consulta 10](https://dgii.gov.do/legislacion/consultas/Consultas%20Tecnicas%202025/Junio/Consulta%2010-Reporte%20compras%20proveedores%20informales.pdf).

**Owner spending.**

- The owner's personal expenses are not deductible.
- B13 is for work expenses that staff pay. It is not for the owner's spending.
- A payment over RD$50,000 must go through a bank to be deductible.
- The accounting entries for owner contributions, owner withdrawals and mixed
  receipts are practitioner convention. Not verified.

**Banks (historical research, outside the pilot finish line).**

- The named Banreservas commercial-loan product asks for 3 years of financial statements, proof of filing with
  DGII and 3 months of bank statements. If the last close is more than 6
  months old, it asks for interim statements. Applications above RD$10M
  require audit-firm financials. This is one product's list. Source:
  [Banreservas commercial loans](https://www.banreservas.com/empresarial/financiamientos/prestamos-comerciales/).
- The 2017 Superintendencia de Bancos table uses consolidated debt in the
  financial system, not an individual loan amount. Below RD$5M, the debtor
  signs. From RD$5M to below RD$10M, the company CPA prepares the statements
  (a contracted CPA for individuals). From RD$10M to below RD$25M, an
  independent CPA prepares them. From RD$25M, an audit firm audits them.
  Later amendments are not verified. This is not a claim about current rules.
- The 6-month interim rule supports a monthly package.

**Accounting software.** QuickBooks Online bill import needs bill number,
supplier, bill date, due date, account, line amount and line tax code. Import
formats for Alegra, Monica and Contasis: not verified.

The full notes, with each source, are in
[DR accountant package research](../../research/2026-10-10-cuadrao-dr-accountant-package-research.md).

## Appendix B. Evidence

- Code audit at `df208f7ec` on `codex/cuadrao-business-sandbox`, October 10,
  2026. Four read-only agents. No paid calls and no deploys.
- PR #925 at `1426404d8`.
- Base `codex/private-alpha-next` at `cd14c9883`.
