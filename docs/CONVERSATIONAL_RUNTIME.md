# Argus Conversational Runtime

Status: Active Alpha implementation

Argus treats conversation as the product surface and backtesting as an execution tool. The active `/api/v1/chat/stream` path runs the LangGraph agent runtime with a model-backed interpretation layer before validation, confirmation, execution, persistence, and explanation.

## Runtime Contract

The model proposes meaning. Argus validates it. The user confirms it. The engine executes it.

## Conversational Artifact Contract

Each active chat turn is grounded in one conversational artifact:

- a pending strategy draft awaiting clarification or confirmation, or
- a completed result awaiting follow-up.

Every user turn must start a draft, patch the pending draft, answer a pending field, ask about the draft, confirm the draft, ask about the latest result, or recover the latest failed turn. Argus should not restart from blank state when a prior artifact clearly exists, and it must not execute a completed draft until the user has seen and approved the confirmation state.

This separation is intentional:

- LLM interpretation is used for natural language understanding, strategy type inference, structured strategy drafting, ambiguity detection, correction-aware follow-ups, conversational unsupported handling, confirmation wording, and result explanation.
- Deterministic code is used for capability truth, provider availability, asset class validation, required-field gating, same-asset restrictions, execution defaults, benchmark selection, indicator execution specs, backtest execution, result envelopes, persistence, and stream event shape.
- The LLM cannot silently mark unsupported behavior as executable, invent asset availability, change symbols, skip required confirmation, or fabricate result metrics.
- Before confirmation, Argus runs semantic conservation checks so explicit user constraints outrank defaults. If a user-supplied date, cadence, asset, or money role cannot be preserved or normalized, Argus clarifies instead of emitting a confident `Ready to run` card.
- Asset grounding starts inside interpretation: provider-backed resolution context should help the model extract every clearly mentioned same-class asset before confirmation. Deterministic validation then resolves only the assets the interpreter identified. Ambiguous company-name matches must clarify instead of being silently dropped.
- For DCA / recurring accumulation, `capital_amount` is the recurring contribution. Current DCA execution supports that one executable dollar amount only. Starting principal, total capital budgets, and contribution ceilings may be acknowledged as user intent, but they are future engine capabilities and must not overwrite the contribution amount.
- Deterministic fallback cannot become the normal assistant voice. If the LLM fails, Argus may preserve truth internally, but user-facing copy must be natural recovery language rather than raw fields, enums, or starter prompts.

### Artifact Metadata Spine

Runtime snapshots and message metadata may carry lightweight artifact references
for the active draft, active confirmation, latest completed result, latest failed
action, and saved strategy state. These references are additive continuity
metadata: they help Argus select and hydrate the visible artifact, but they do
not replace LangGraph runtime memory or Supabase product records.

Result references are derived from immutable `backtest_runs` records. The
runtime may expose a result fact bank containing the run id, conversation id,
strategy id, asset class, symbols, benchmark, metrics, config snapshot, result
card, optional structured execution-cost evidence, chart, and trades so
follow-up answers can use actual run facts after reload. Engine metrics,
`backtest_runs.config_snapshot`, and structured result-card evidence remain the
canonical truth; the fact bank is a transport/context projection.

Failed-action references preserve recoverable action context such as the action
type, launch payload, failure classification, and user-safe error. They exist so
"try again" can bind to the latest failed visible action without restarting the
thread from blank. Deterministic code still validates capability, stale state,
and authorization before any retry executes.

Saved-strategy metadata, including `saved_strategy_id`, is result artifact state.
It makes Save Strategy idempotent and allows reload to show that a result was
already saved. Saving still uses a concrete run id and canonical result state,
not frontend prose or regenerated assistant text.

## Voice Boundary

Every user turn is routed by intent and conversation context before slot or field logic can speak.

The runtime rejects assistant responses that are:

- one-word or fragment answers when the user asked for explanation
- stale summaries based on the wrong user turn
- raw internal names such as `asset_universe`, `not specified`, or `requested_field`
- generic starter guidance after a thread already has context

When a response fails this gate, normal ambiguity is sent back through the
structured LLM clarifier with bounded facts and requested fields. Deterministic
user-facing copy is reserved for explicit artifact-action recovery, such as a
stale or non-retryable failed-run action, where code owns the safety boundary.

The edit disclosure boundary: `domain.edit_contract` owns applied-or-disclosed
accounting. Normal and recovery adapters supply requested targets, materialized
targets, actual change status and existing refusals. A reissued card with no
change carries a typed `no_change_applied` receipt even if no operation was
extracted. Rejected flat fields and values discarded by downstream normalization
are explicitly unapplied. This deterministic receipt does not guess user intent.
For a partially understood compound request, a field missed by every structured
read remains unknowable to deterministic code; it cannot name that missing field
without parsing prose. The primary read, planner and stated-run-field audit still
own extraction, with their existing completion and coverage guards unchanged.

Recovery copy may only speak for live artifacts. Argus never contradicts its
own card: a confirmation that was cancelled or superseded is not "still
ready", however much of it survives in runtime state, and recovery paths read
pending confirmation state through one liveness accessor
(`live_pending_confirmation`) rather than testing that a draft merely exists.
If a recovery path cannot honestly speak for an artifact, it says so and
offers something real.

## Language-Agnostic Prose Composition

Runtime copy is composed, not templated per language. Since the B4 language-gate
retirement (#154, PRs #174-177), Argus keeps no parallel English/Spanish copy
tables in the runtime:

- LLM-authored conversational prose (clarifications and explanations) is written
  in the workspace language from a typed fact bank. The backend supplies typed
  facts; the model supplies the words.
- Degraded and recovery copy renders from typed codes, not per-language strings.
  When the LLM path is unavailable, the runtime maps a typed recovery/degraded
  code to localized surface text at the presentation boundary, never a runtime
  `if locale == "es-419"` branch or an `_english_*` helper.
- Result-card chrome (labels, headings, chips) renders from typed keys the
  frontend localizes, not from backend-baked language strings.

**Persisted result exception (founder-approved 2026-09-04, #531):** Quick Take,
result breakdown, dossier outcomes, and their copy output voice typed canonical
run facts at the frontend boundary, for both live and historical results. A
workspace-language change must not require a model call or regenerate evidence.
The original explain-stage prose remains private audit/model context; it is
stripped from public result transport and is never a reader fallback. Old
messages derive missing transport facts from an owner-scoped canonical run;
missing evidence is shown honestly in localized copy. This does not replace
ordinary conversational composition with a deterministic assistant.

**Confirmation card turns carry no prose.** The card builder composes no
summary sentence and a card turn persists empty content. Model thread history,
artifact naming and the conversation search text derive from the card's typed
facts (`argus.domain.confirmation_turn_facts`), so none of them carries the
language of the turn; the card itself renders from typed keys.

The invariant: prose follows the workspace language everywhere, English and
Spanish parity is proven by the eval harness (not hardcoded copy), and no runtime
module carries per-language copy tables, localized stop-word lists, or
display-label token matching for semantic choice selection. This is the runtime
expression of the P2.0 guardrail against per-language copy.

**Input language and output language are separate, and that is deliberate
(founder-locked 2026-08-11).** A user may write in any language and Argus
proceeds correctly: that is the language-agnostic spine, and it must never
gate, refuse, or degrade on the language of a message. The language of the
*response* is bound to the workspace setting, which is what the setting is for.
Binding output to the setting removes ambiguity about delivery and guarantees a
predictable flow, while leaving the user free to speak however they like.

So an English question in a Spanish workspace correctly returns a Spanish
answer. That is not a defect. Verified in production on 2026-08-11 and accepted.

Do not build per-message language resolution. Reconciling a workspace setting
against per-message intent reintroduces exactly the ambiguity the setting
exists to remove. #378 is closed to that reading; see its 2026-08-11 comment
before acting on its title.

## Active Layers

1. Conversational intelligence
   - `src/argus/agent_runtime/llm_interpreter.py`
   - Uses OpenRouter through task-scoped client construction and structured output.
   - Preserves raw user phrasing and normalized strategy meaning.
   - Uses bounded model budgets by task so provider defaults cannot request oversized completions.

2. Stateful orchestration
   - `src/argus/agent_runtime/graph/workflow.py`
   - Routes `interpret -> clarify -> confirm -> execute -> explain`.
   - Persists pending and confirmed strategy summaries in the latest task snapshot.

3. Structured strategy contract
   - `src/argus/agent_runtime/state/models.py`
   - Captures strategy type, symbols, asset class, date range, cadence, entry/exit logic, sizing, risk rules, assumptions, unsupported constraints, and refinement metadata.

4. Validation and capability truth
   - `src/argus/agent_runtime/stages/interpret.py`
   - `src/argus/agent_runtime/capabilities/contract.py`
   - `src/argus/domain/market_data/*`
   - Alpaca `/v2/assets` is the primary equity and crypto availability source through `resolve_asset`.
   - Kraken public REST complements Argus for currency pairs and crypto fallback. Kraken OHLC is limited to the latest 720 candles per interval, and requests outside that window must recover conversationally instead of pretending data exists.
   - `src/argus/domain/indicators/registry.py` is the executable indicator contract. pandas-ta discovery can expose draft-only indicators, but an indicator is executable only when its spec defines parameters, output selector, bounds, defaults, and threshold formatting.

5. Execution truth
   - `src/argus/agent_runtime/tools/real_backtest.py`
   - `src/argus/agent_runtime/stages/execute.py`
   - Runs real supported backtests and returns the same result envelope used by the UI.

6. UI integration
   - `web/components/chat/ChatInterface.tsx`
   - `web/components/chat/ChatMessage.tsx`
   - The assistant explanation and result card render as one assistant response.
   - Confirmation actions and result actions are structured events, not fake user text.
   - Result cards render before the summary and own the save-strategy control.

## Action Events

Confirmation actions are available only while a strategy is awaiting approval:

- `run_backtest`
- `change_dates`
- `change_asset`
- `adjust_assumptions`
- `cancel_confirmation`

Result actions are available only after a completed run:

- `show_breakdown`
- `refine_strategy`

Response-option actions may answer a structured clarification choice:

- `select_response_option`

These actions must carry typed option metadata such as `option_index` or
`replacement_values`. The runtime may use that metadata in degraded recovery,
but it must not infer the chosen option from translated display labels.

New result cards never emit or render `save_strategy`. A stale persisted
`save_strategy` action is accepted only as a non-mutating compatibility turn:
Argus explains that the completed run remains in conversation/history.

## Post-Result Continuity

After a completed result, continuity edits are one typed contract with
multiple entry points (shipped by #141 / PR #148):

- The `refine_strategy` result action opens a refinement pending state that
  routes the next turn through the typed artifact-edit operations — the same
  planner used by confirmation-card edits and natural-language edits. Refine
  is a convenience entry point, not a separate interpretation path.
- Refinement pending state is a first-class edit context: date-window and
  cadence changes are planner-expressible edits and must not fall back to
  generic interpretation. Strategy reshapes still fork to full interpretation.
- A new idea immediately after a completed result may borrow that result's
  context: references like "the same time period" bind silently to the latest
  run's date window, and the bound values must appear on the resulting
  confirmation card as visible assumptions, never as hidden defaults.
- A confirmed pending date answer materializes once; repeated affirmatives
  must not re-ask the same confirmation.

Regression coverage: `tests/agent_runtime/test_refine_action_edit_routing.py`,
`tests/agent_runtime/test_post_result_edit_routing.py`, and
`tests/agent_runtime/test_latest_result_window_binding.py`.

## Persistence Boundary

Supabase-backed persistence owns conversation continuity:

- `conversations` stores the active thread.
- `messages` stores user/assistant text and structured card metadata.
- `backtest_jobs` stores durable queued/running/succeeded/failed/canceled/expired
  execution lifecycle state for chat-confirmed backtests.
- `backtest_runs` stores immutable config, metrics, result card, chart, and event markers.
- `strategies` stores saved result-backed ideas for the Strategies surface.

Confirmed backtests should cross the durable job boundary. The API creates or
references a job, Render Workflow execution writes the result, and Supabase
Realtime carries job status changes to the browser. API SSE remains scoped to
the current chat turn.

Reloading or navigating away from chat must hydrate both visible messages and structured UI artifacts, including confirmation cards, queued/running job cards, result cards, latest run ids, and available actions. A reload must not turn a structured result into plain text only.

Runtime memory remains checkpoint-first. The pending card's checkpoint owners are the task snapshot and the run state; the workflow-level `confirmation_payload` channel is the launch hand-off between interpret and execute and is turn-scoped, so nothing parked there outlives its turn or is published over a later turn's own card. If a pending confirmation action arrives after reload, the API validates the LangGraph checkpoint before execution. Message metadata may supply a conservative fallback snapshot only when it contains structured confirmation payload; otherwise the assistant asks the user to reconfirm instead of silently running incomplete state. Result follow-ups may recover the latest canonical run reference from message metadata and `backtest_runs`, but Save Strategy must still use a concrete run id from the result card.

Confirmation cards are durable transcript artifacts, but only the latest active
confirmation is executable. New refinement confirmations supersede older cards,
and a completed result also makes prior confirmation cards historical. The UI may
render superseded cards as muted `Updated` cards, but backend execution still
checks the active confirmation identity before running.

An interpreted question about a pending artifact's assumptions returns the
typed `artifact_assumptions` response intent. Its `display_facts` come from the
same confirmation fact owner used by the card, including zero fees/slippage
and the separate money roles of a recurring plan. The frontend language
bundles voice those facts in both live and hydrated turns. Empty backend prose
is a successful terminal answer when this typed intent is present; it must not
trigger the empty-response recovery or change confirmation liveness.

Existing confirmation artifacts may reconstruct missing facts from their
typed confirmation payload. Original assumption prose remains non-presentational context,
and unavailable facts produce localized unavailable copy. Old freeform
assumptions replies without a stored typed discriminator cannot be recognized
without guessing from prose, so they retain ordinary transcript behavior.
The runtime must not add a language-specific phrase matcher to classify them.

Clarification prompts may persist a single pending resolution candidate, such as
Apple Inc. (`AAPL`) for an ambiguous "Apple" request. If the next user turn is a
short affirmative answer, deterministic guardrails may accept only that stored
candidate for that stored field after LLM interpretation. This keeps ordinary
language LLM-first while preventing repeated binary clarifications.

Legacy Collection rows remain in the schema for owner-scoped historical reads.
There is no sidebar entry, settings link, picker, command/search result, result
action, CRUD endpoint, or new Collection write path.

## Fully Supported

- Basic product and education questions.
- Buy and hold for same-asset supported symbols.
- DCA / recurring accumulation with daily, weekly, biweekly, monthly, or quarterly cadence and one recurring contribution amount.
- Indicator threshold strategies when the indicator registry marks the indicator executable.
- Single-asset-class backtests with up to 5 symbols.
- Equity benchmark default: `SPY`.
- Crypto benchmark default: `BTC`.
- Currency-pair benchmark default: the tested pair.
- Long-only execution.

## Partially Supported

- Compound indicator/price/volume confluence can be drafted and preserved, but execution may require simplification to an executable subset.
- Risk overlays such as stop loss, trailing stop, take profit, and partial/full exits are captured in the strategy object. They are only executable where the engine adapter supports the semantics.
- Strategy comparisons are interpreted conversationally. Execution should run supported strategies separately and explain the comparison from real result payloads.
- DCA requests that include separate starting principal, total capital budget, or investment ceiling are understood conversationally, but those modifiers are not executable in the current DCA engine. Argus should offer a recurring-only run, an adjusted recurring contribution, or a buy-and-hold style test using starting capital.

Deferred(dca-engine): Add first-class support for DCA starting principal, investment ceilings, and recurring contribution combinations across engine config, launch request models, LangGraph semantic contracts, confirmation cards, result assumptions, and model capability wording. This is broader unsupported DCA engine capability work and is outside the Spanish canary/chart attribution fix.

## Unsupported Handling

When a request is not fully executable, Argus must:

- Acknowledge the understood idea.
- Explain the exact limitation.
- Preserve the user intent in the candidate strategy.
- Offer executable simplifications.
- Keep the same thread active.

Examples:

- Mixed equity, crypto, and currency pairs in one run are unsupported. Argus should offer separate runs or an asset-class choice.
- Unverified symbols are unsupported until provider lookup succeeds.
- Unsupported compound logic should be preserved as intent and simplified only with user approval.
- Provider data-window limits, including Kraken's 720-candle OHLC window, must be explained as data availability limits with a concrete shorter range or wider timeframe suggestion.

## Result Experience

Result presentation is a single product moment:

1. Render the result card first.
2. Show a short grounded summary from canonical run/result context, not stale
   original user wording.
3. Offer result actions.

The card owns numerical reporting. Quick take tells the first-glance story;
Breakdown explores the holding experience and historical tradeoffs without
repeating the card or Quick take. The frames, labels, ordering and result card
stay unchanged. Both composers derive their facts from one labeled stored-run
fact sheet with units, meaning, money roles and available dated path relationships.
Quick take receives a projection with plain meanings and display-ready values;
hypothetical capital-scaled losses and storage metadata stay out of the prompt.
Breakdown receives only
its labeled headline scalar facts, such as the tested dates, returns, worst drop,
capital, contributions, costs and purchases/sales versus completed buy-and-sell pairs. The full
chart series, markers and internal field paths never enter the Breakdown request.
The worst drop includes its high, low, dates and dollar decline computed from
unrounded balances. The whole-period peak includes its date. Dated groups enter
the request in chronological order, with arithmetic done before display rounding;
missing endpoint or date evidence remains unavailable.
A figure appears only when a sentence needs it, with its checked fact reference.
Both composers receive the card's precision: one decimal for percentages, whole
dollars for account values, and localized dates. Accuracy instructions guide the
model silently; prose describes the holding experience, not calculation rules.

`result_summary` uses the OpenRouter `readout` tier with
`openai/gpt-5.6-luna`. Both readout model keys select Luna; a failure uses the
existing template, with no weaker-model fallback and no search.
Readout-tier requests omit `temperature` because Luna's available OpenRouter
endpoints do not support it. Other tiers keep their existing request parameters.

The `Show breakdown` action uses that same model through the existing
`PerplexityAgentClient.run_structured` interface. Its model, deadline and bounded
tool configuration are owned by `api/chat/breakdown.py`, not an environment key.
Only `web_search` and `fetch_url` are allowed. There is no Breakdown OpenRouter
task/profile/tier mapping. The `result_breakdown` message kind remains unchanged.
Before provider dispatch, Breakdown uses the request's shared research capacity
claim. An exhausted guest allowance or global ceiling selects the complete
template without a provider call.

The Breakdown request asks plainly what happened to the asset over the tested
window and why, what holding through it was like, and how the test compared with
the benchmark, with a web search for sources. Run facts alone own simulation
numbers; web context must not replace or merge with those facts. Returned
Perplexity sources travel in `metadata.research.sources`, with dates when the
provider supplies them. Breakdown reuses the existing Sources link and panel
both live and after reload. In-text links remain in the prose; no bibliography
is appended. The model does not recreate source lists or per-claim records.

Both structured drafts contain `language`, complete `text` and `figures`; each
run reference carries `fact_key` and the displayed `value`. One reference per
distinct fact is sufficient. The light numerical guard checks only declared
references against their run facts within display rounding. Missing references
or repeated numbers do not reject prose. Quote/occurrence coverage, per-claim web
dates, benchmark-claim regexes and internal-field regexes are not acceptance
checks. Invalid schema, empty text, language mismatch, invalid declared references
or provider failure selects the complete template. This boundary does not prove
that every sentence is true; live review still checks accepted claims. Plain
language, no forecasts and no investing advice remain writing requirements.

Accepted prose is saved once in the closed language-tagged
`result_readout_content` envelope described in `docs/API_CONTRACT.md`. Readers
show it only when their workspace language matches. Older readouts and language
mismatches use today's template; a new Breakdown request composes a new message
in the current language without rewriting the saved Quick take.

Quick take spend retains OpenRouter receipt accounting. Every received Breakdown
invoice, including a rejected draft, reaches the shared research ledger writer
with task `result_breakdown` and feature area `result_readout`. The Agent client
retains existing unpriced-spend recording. There is no second Perplexity client.

Breakdown suggestions must respect capability truth. The assistant may suggest
tests that are runnable now, ideas it can help draft, or future engine
capabilities, but it must not imply unsupported strategies are executable today.
Structured breakdown actions should emit an `explain` stage before final text so
the UI can show a clear working state while preserving canonical SSE frame
types. The existing Breakdown frame owns one localized working state, without
a second generic status line. Durable persistence reserves a `chat.research` job
and saves its acknowledgement before provider work starts. The existing research
task owner and message-first finalizer complete it outside the browser stream;
job polling replaces the pending frame with its saved answer, including after
reload. The Perplexity call still uses its existing structured client interface.
Development memory mode retains completion independently and uses its existing
ordinary-turn finalizer and recovery reader because it has no job endpoint.
Only a completed response selects model prose or the
template; the pending frame does not claim saved facts are insufficient.

The chart is a TradingView Lightweight Charts baseline chart using the aggregate portfolio equity curve. Multi-symbol runs must show the portfolio curve, not a cluttered symbol comparison. Entry and exit markers may be capped for readability. TradingView attribution must remain visible.

## Search And Embeddings

Embeddings are not required for the launch chat/backtest loop. Supabase structured state, run metadata, saved strategy records, provider catalogs, and Postgres text search are enough for Alpha. Add pgvector only when Argus needs semantic recall across large saved-history or strategy corpora.

## Environment

Backend package management uses Poetry.

Frontend package management uses Bun.

Required model and data variables:

- `OPENROUTER_API_KEY`
- `CUADRAO_UTILITY_MODEL` / `CUADRAO_UTILITY_FALLBACK_MODEL`: cheap background
  utility tasks such as titles and labels.
- `CUADRAO_CHAT_MODEL` / `CUADRAO_CHAT_FALLBACK_MODEL`: clarification,
  `chat_composer`, `discovery_voicing` and `knowledge_voicing`.
- `CUADRAO_READOUT_MODEL` / `CUADRAO_READOUT_FALLBACK_MODEL`: Quick take
  (`result_summary`), both set to `openai/gpt-5.6-luna`.
- `CUADRAO_STRUCTURED_MODEL` / `CUADRAO_STRUCTURED_FALLBACK_MODEL`: durable
  JSON-schema artifact interpretation, repair, and draft edits.
- `CUADRAO_CONTEXT_MODEL` / `CUADRAO_CONTEXT_FALLBACK_MODEL`: `capability_conflict`.
- `PERPLEXITY_API_KEY`: existing Agent credentials, also used by Breakdown.
- `ARGUS_FRED_CONTEXT_SERIES`: curated comma-separated macro series for context
  packets. Default: `FEDFUNDS,DGS10,DGS2,T10Y2Y,CPIAUCSL,CPILFESL,UNRATE,PAYEMS,INDPRO,USREC`.
- `ARGUS_CONTEXT_PACKETS_ENABLED`: enables best-effort context packet collection
  for completed run explanations when Supabase persistence is active.
- `ARGUS_CONTEXT_PACKET_BUDGET_SECONDS`: bounds provider collection latency for
  context packets. Simulation results must still persist without context.
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `CUADRAO_PERSISTENCE_MODE`
- Supabase variables from `.env.example` when running with Supabase persistence.

Structured artifact calls use OpenRouter JSON-schema responses directly and
disable reasoning with `reasoning: {"effort": "none"}`. The reason is practical:
for artifact extraction Argus needs complete JSON content, not billable hidden
reasoning tokens. If a provider rejects that reasoning setting, the client may
retry the same request without it before moving to the next configured model.

## Conversational Runtime Decision Filter

When changing conversational runtime behavior, ask:

> *Does this keep the conversation resilient under messy human curiosity while preserving deterministic validation, artifacts, and recovery?*

If no, it likely should wait or be redesigned.
