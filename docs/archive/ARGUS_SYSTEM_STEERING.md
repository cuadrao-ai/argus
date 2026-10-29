# Argus System Steering Map

> [!NOTE]
> Historical context. This document is retained as implementation evidence. For current private-alpha direction, see AGENTS.md and docs/specs/private-alpha-next-integration.md.

**Status:** Pre-private-launch steering reference
**Branch assessed:** `codex/private-alpha-conversation-trust`
**Created:** 2026-05-19
**Purpose:** Preserve the architectural direction from the runtime, brittleness, and modularity audits before future hardening work begins.

This document is a planning reference, not an implementation ticket. It captures what Argus must own, what it should rent or orchestrate, what should stay deterministic, what should become LLM-owned, what must be cleaned up before private launch, and what is intentionally deferred.

The private-launch loop this document protects is:

```text
user idea -> interpretation -> validation -> confirmation card -> run -> persisted result -> reload -> grounded follow-up -> useful next experiment
```

## 1. Current System State

Argus is currently a chat-first, simulation-grounded investing experimentation system with a working but still brittle runtime path.

Known state on the private-alpha conversation trust branch:

- Tiered OpenRouter routing exists through `ARGUS_*` model-tier environment variables.
- OpenRouter tier configuration is `ARGUS_*` only; legacy model aliases are no
  longer part of the active runtime contract.
- FRED environment configuration exists, and the minimal `ContextPacket` contract/provider wrappers now exist.
- Alpaca and Kraken provide the current deterministic market-data truth layer for OHLCV and availability.
- Alpaca should be considered near-term context for scoped news, corporate actions, most actives, and movers, but not as a generic dashboard feed.
- Tier 4 can synthesize from run facts plus attached context-packet fields; completed runs without attached packets still fall back to run-fact-only explanations.
- The OpenRouter signal-repair regression for partial moving-average crossover ideas is green after routing underfilled structured interpretations through focused repair.
- Deterministic run facts, result fact banks, result cards, reload metadata, confirmation artifacts, and action payloads exist.
- `chat_service.py` has been retired; split `api/chat/*` modules are the only
  supported chat helper import paths.
- Several files mix too many responsibilities and should be modularized to reduce brittleness before or during private-launch hardening.

The system is directionally coherent, but not private-launch ready until runtime integrity, semantic flexibility, route observability, reload trust, and context-packet boundaries are tightened.

## 2. Core Product Truth

Argus is not a broad finance research product. Argus is a conversational investing experimentation system grounded by reproducible simulations and enhanced by contextual intelligence.

The conversation is the product surface. The backtesting engine is critical infrastructure. The user should be able to speak a rough investing idea, see what Argus understood, run a supported historical simulation, trust the result, and continue exploring.

### What Argus Owns

Argus should own:

- Workflow: the idea-to-test-to-follow-up loop.
- Memory and continuity: current conversation, persisted messages, saved runs, reload state.
- Orchestration: model routing, retrieval timing, execution timing, result explanation timing.
- Simulation truth: validation, asset rules, default benchmarks, market-data windows, run config, metrics, charts, trades, persistence.
- Strategy normalization: turning natural language into supported, executable or explicitly non-executable strategy drafts.
- Result trust: assumptions, run facts, provider metadata, reproducibility, and clear caveats.

### What LLMs Own

LLMs should own:

- Natural-language interpretation.
- Clarification phrasing.
- Educational responses.
- User-facing explanations.
- Structured extraction when a schema is required.
- Result summaries and follow-ups from fact banks.
- Context synthesis from engine facts plus retrieved context packets.

LLMs should not own:

- Whether an asset exists.
- Whether a provider has data for a date range.
- Whether a backtest can run.
- The benchmark choice.
- The metric values.
- The run config persisted as truth.
- The set of executable strategy mechanics.

### What External APIs Should Do

External APIs should enrich context, not replace simulation truth.

- Alpaca/Kraken own market-data availability and OHLCV source truth for execution.
- FRED should provide macroeconomic context for explanations, regime awareness, and follow-up suggestions.
- Alpaca news and corporate actions should provide scoped market/event context around symbols and periods.
- Tavily, Perplexity, SEC ingestion, transcripts, embeddings, and broad RAG are deferred until the core loop is reliable.

The rule is:

```text
Build proprietary workflows. Rent commodity intelligence.
```

## 3. Pillars

### Runtime Integrity

Current state:

- SSE streaming, final payloads, confirmation cards, result cards, message metadata, and reload recovery exist.
- LangGraph is the active chat runtime.
- Result facts and result cards are persisted.
- Metadata fallback paths exist for confirmation, pending strategy, latest result, and failed action recovery.
- Provider metadata is explicitly stamped for Alpaca equity, Alpaca crypto, and Kraken currency-pair paths; this must stay covered by tests as provider routing evolves.
- LLM model routing now records route receipts for launch-critical OpenRouter paths.

Production risks:

- Future signal-repair regressions can block normal human strategy phrasing.
- Incorrect provider metadata weakens result trust.
- Reload recovery depends on metadata and checkpoint agreement that must be browser-proven.
- Fallback observability is not visible enough to evaluate model cost, latency, and failures.
- Internal runtime endpoint exposure should be reviewed before private launch.

Deterministic boundaries:

- SSE protocol, event ordering, `[DONE]`, request IDs, auth, quotas, and rate-limit headers.
- Confirmation IDs, payload hashes, stale-card rejection, action payload identity.
- Engine validation, asset class parity, provider availability, date limits, symbol caps.
- Run config snapshots, metrics, chart markers from executed fills, trades, benchmark defaults.
- Persistence and ownership checks.

LLM-owned responsibilities:

- Clarification language.
- Explanation language.
- Recovery language when safe structured facts are available.
- Contextual synthesis after the deterministic facts are assembled.

Immediate priorities:

1. Keep signal-repair coverage green as messy-human prompts expand.
2. Keep provider metadata covered for Alpaca/Kraken/currency-pair paths.
3. Persist route receipts for every launch-critical LLM task and fallback.
4. Continue browser verification for reload and saved-result actions.
5. Gate or remove internal-only runtime endpoints before private launch.

Deferred work:

- Queue workers.
- Distributed tracing.
- WebSockets.
- Advanced quota or monetization systems.

Implementation dependency order:

1. Test-green signal repair.
2. Provider metadata correctness.
3. Route receipts.
4. Reload/persistence browser QA.
5. Context packet attachment.

### Conversation Flexibility

Current state:

- The LLM interpreter is the intended NLU owner.
- Several runtime paths still contain hardcoded assistant phrasing.
- Tests often assert exact strings for clarifications, recovery, breakdown headings, and follow-ups.
- Result follow-ups and breakdowns use fact banks and schemas, which is the correct direction.

Production risks:

- Exact prose assertions make the experience brittle under normal human curiosity.
- Deterministic personality copy can override the LLM and make Argus feel scripted.
- Canned recovery copy can become product logic instead of safety fallback.
- Static next-action prose limits useful continuation.

Deterministic boundaries:

- Semantic intent labels and state transitions.
- Required fields, missing fields, action types, artifact references.
- Forbidden claims: no invented metrics, no unsupported mechanics, no investment advice.
- Confirmation cards and result cards as structured artifacts.

LLM-owned responsibilities:

- User-facing wording for clarifications, educational answers, unsupported-request redirects, and result explanations.
- Tone and phrasing, bounded by semantic contracts.
- Follow-up suggestions from structured next-experiment options.

Immediate priorities:

1. Replace exact-copy tests with semantic contract tests where LLM language is expected.
2. Keep exact assertions for protocols, IDs, facts, action states, and safety constraints.
3. Convert action prompts and recovery copy into semantic intent metadata plus LLM phrasing.
4. Preserve safety fallback copy only for no-LLM or malformed-output paths.

Deferred work:

- Broad personality tuning.
- Additional languages beyond current product support.
- Large prompt experiments before the core loop is browser-proven.

Implementation dependency order:

1. Mark deterministic vs semantic test surfaces.
2. Relax brittle exact-string tests.
3. Route user-facing copy through LLM tiers.
4. Use browser transcripts and semantic evals as acceptance evidence.

### Backtest Adaptability

Current state:

- Buy-and-hold, DCA/recurring buys, indicator threshold rules, and schema-backed signal strategies exist.
- Same-asset-class constraints, default benchmarks, and max-symbol limits are core truth.
- Partial signal repair exists but has a current regression.
- Some human strategy patterns still fail too rigidly or require overly exact language.

Production risks:

- Normal users will say "starts rising", "dips hard", "50 crosses 200", or "around earnings" rather than engine template names.
- If partial signal repair fails, Argus will ask unnecessary questions or produce brittle drafts.
- If unsupported ideas dead-end, users will perceive the product as incapable rather than guided.

Deterministic boundaries:

- Engine-supported strategy families.
- Required executable fields.
- Rule specs and indicator parameter validation.
- DCA contribution semantics.
- Long-only equal-weight execution.
- No mixed asset classes.

LLM-owned responsibilities:

- Mapping messy language to supported strategy drafts.
- Asking for missing executable semantics.
- Redirecting unsupported ideas into nearby testable experiments.
- Preserving the user's intent when simplification is required.

Immediate priorities:

1. Fix moving-average crossover underfill repair.
2. Define a supported-idea contract table for common messy human patterns.
3. Convert next experiments into structured options rather than prose.
4. Preserve unsupported concepts as context or draft-only ideas, not executable truth.

Deferred work:

- Broad quant strategy expansion.
- Shorting, long-short, custom scripts.
- Mixed-asset simulations.
- DCA starting principal plus recurring contribution execution.
- News/sentiment/fundamental signals as executable engine rules.

Implementation dependency order:

1. Repair current signal path.
2. Add semantic coverage for common messy idea patterns.
3. Make unsupported simplification useful.
4. Expand engine mechanics only after private-user evidence shows repeated demand.

### Context Intelligence

Current state:

- FRED API key is configured.
- Alpaca/Kraken execution truth exists.
- The minimal `ContextPacket` schema, Supabase migration, gateway methods, and provider wrappers exist.
- Tier 4 can use packet facts and limitations when packets are attached to the result fact bank.
- Live provider attachment and browser QA for context-enriched explanations remain required before relying on packets in the private-launch loop.

Production risks:

- Without context packets, "why did this happen?" can only be answered from metrics.
- If context is introduced as freeform browsing, explanations can hallucinate causal narratives.
- Generic finance feeds would push Argus toward dashboard territory.

Deterministic boundaries:

- Context never changes run truth after execution.
- Context cannot rewrite metrics, trades, or config snapshots.
- Context facts must include source, scope, date coverage, and limitations.
- The assistant must distinguish "run fact" from "possible context."

LLM-owned responsibilities:

- Synthesizing engine facts plus context packets.
- Explaining macro or event backdrop without claiming unsupported causality.
- Suggesting follow-up experiments from facts and context.

Immediate priorities:

1. Browser-prove packet attachment and replay for completed runs.
2. Keep packet references in result fact banks and message metadata.
3. Use FRED for macro regime context.
4. Use Alpaca corporate actions and scoped news for symbol-specific context.
5. Keep context generation out of the simulation truth layer.

Deferred work:

- Tavily.
- Perplexity.
- SEC ingestion.
- Earnings transcripts.
- Embeddings or pgvector.
- Broad RAG.
- Generic news dashboards.

Implementation dependency order:

1. Schema and storage/reference shape.
2. FRED macro packet builder.
3. Alpaca corporate-action packet builder.
4. Scoped Alpaca news packet builder.
5. Tier 4 synthesis from fact bank plus packets.

### Dead Code / Migration Cleanup

Current state:

- `chat_service.py` is retired and should not be restored.
- Launch router code should import focused runtime/chat modules directly.
- Tests should import focused modules for helpers that now live outside the
  retired facade.
- `ARGUS_*` model-tier config is the active runtime contract; legacy model
  aliases should not be used by launch-path code, tests, or docs.
- Some helpers appear obsolete or compatibility-only.

Production risks:

- New work may restore or target the retired facade instead of actual module
  ownership.
- Compatibility aliases can hide stale code and duplicate behavior.
- Tests anchored to old paths make cleanup harder.
- Old config naming can confuse model-tier operations.

Deterministic boundaries:

- Backward compatibility may remain only where it protects active behavior during migration.
- Public contract stability matters more than internal import stability.
- Do not remove recovery shims until browser QA proves reload continuity without them.

LLM-owned responsibilities:

- None directly. This pillar is codebase hygiene in service of runtime clarity.

Immediate priorities:

1. Keep `chat_service.py` deleted.
2. Keep tests pointed at focused modules.
3. Remove underscored compatibility aliases from focused modules when touched.
4. Make `ARGUS_*` primary in docs and tests.
5. Delete obsolete helpers after usage is proven absent.

Deferred work:

- Removing all compatibility shims in one large sweep.
- Broad refactors unrelated to private-launch risk.

Implementation dependency order:

1. Import rewiring.
2. Compatibility facade reduction.
3. Dead helper deletion.
4. Documentation cleanup.

### Modularity Candidates

Current state:

- Several files now have too many unrelated reasons to change.
- The repo already uses the modular-monolith pattern successfully.
- `engine.py` is already a compatibility facade over focused backtesting modules and can remain stable.

Production risks:

- Mixed-responsibility files increase the chance of regressions during runtime hardening.
- LLM interpretation, signal repair, artifact edit repair, and validation are too tightly coupled.
- Router responsibilities are too broad.
- Result follow-up code will become harder to extend once context packets arrive.

Deterministic boundaries:

- Public API contract.
- SSE event contract.
- Engine facade behavior.
- Confirmation and result artifact shape.
- Test coverage around protected runtime paths.

LLM-owned responsibilities:

- Not a module boundary by itself. LLM-owned behavior should live behind clear orchestration, schema, rendering, and guardrail modules.

Immediate priorities:

1. Split high-risk files where private-launch work will touch them repeatedly.
2. Preserve facades temporarily where tests or public imports need stability.
3. Avoid architecture-only refactors that do not reduce near-term brittleness.

Deferred work:

- Deep redesign of LangGraph workflow internals.
- Full test-suite reorganization.
- Styling or frontend refactors unrelated to chat/runtime acceptance.

Implementation dependency order:

1. `llm_interpreter.py` split around the signal-repair fix.
2. `agent.py` split around runtime streaming and action dispatch.
3. `interpret_actions.py` split around action categories.
4. `result_followups.py` split before context packets.
5. `result_facts.py` split before structured next experiments.

## 4. Deterministic vs Semantic Contracts

### Must Remain Deterministic

- Auth and ownership checks.
- Rate limits and quotas.
- SSE frame format and event ordering.
- `stage_start`, `token`, `stage_outcome`, `final`, `[DONE]`.
- Conversation, message, run, strategy, artifact, and confirmation IDs.
- Confirmation payload hashing and stale-action rejection.
- Backtest config validation.
- Asset resolution and asset-class parity.
- Provider availability and provider metadata.
- Benchmark defaults: equity `SPY`, crypto `BTC`, currency pair itself.
- Strategy execution constraints: long-only, same asset class, max 5 symbols, supported timeframes.
- Engine metrics, chart markers, trades, and config snapshots.
- Persistence and reload metadata.
- Fact banks and required fact coverage.
- Guardrails against unsupported mechanics, invented metrics, investment advice, and fake causality.

### Should Become Semantic or LLM-Driven

- Clarification wording.
- Educational responses.
- Unsupported-request redirection.
- Recovery copy when structured state is available.
- Result explanations.
- Follow-up answers.
- Next-experiment phrasing.
- Capability answers from deterministic capability facts.
- Context synthesis from retrieved packets.
- Breakdown headings and section ordering.

### Tests That Should Stop Asserting Exact Prose

Tests should stop expecting one exact assistant sentence where language belongs to the LLM. They should assert:

- Required facts are present.
- Forbidden claims are absent.
- Correct state transition happened.
- Correct requested field or semantic need is set.
- Correct action payload or artifact reference is preserved.
- The answer is grounded in fact-bank values.

Exact-string tests should remain only for:

- Protocol literals.
- Enum values.
- IDs and hashes.
- Error codes.
- Static UI labels where product copy is intentionally fixed.
- Safety fallback copy only when no LLM path is available.

## 5. Runtime Brittleness Findings

The audits found these recurring brittleness patterns:

- Rigid deterministic fallback behavior where the LLM should own user-facing language.
- Canned recovery copy that tests treat as product truth.
- Exact-string tests for result breakdowns, clarifications, reload recovery, and follow-ups.
- Deterministic personality leakage in runtime/domain modules.
- Hardcoded next-action prose inside result facts.
- Semantic repair gaps for partial signal strategies, especially moving-average crossovers.
- Facade imports that hide actual module ownership.
- Legacy model env names still taught as primary config.

The fix is not to remove deterministic behavior. The fix is to move deterministic behavior to facts, protocols, validation, state, and guardrails, while letting LLM tiers own language under semantic contracts.

## 6. Modularity / File Responsibility Audit

### `src/argus/agent_runtime/llm_interpreter.py`

Classification: split now before private launch.

Why:

- It mixes OpenRouter candidate loops, prompts, focused extraction, artifact edits, signal repair, shape validation, response normalization, strategy mapping, asset grounding, capability validation, and fallback repair.
- The previous signal-repair regression sat inside this responsibility knot.

Target responsibilities:

- `agent_runtime/interpreter/openrouter_runner.py`: candidate/fallback model loop and route receipt.
- `agent_runtime/interpreter/prompts.py`: system and focused extraction prompts.
- `agent_runtime/interpreter/repairs.py`: focused extraction, artifact edit, signal-rule repair/audit.
- `agent_runtime/interpreter/shape.py`: required-shape checks, replay detection, underfill detection.
- `agent_runtime/interpreter/strategy_mapping.py`: LLM draft to `StrategySummary`, prior merge, grounding, defaults.
- Keep `llm_interpreter.py` as a thin facade until imports settle.

### `src/argus/api/routers/agent.py`

Classification: split now before private launch.

Why:

- It mixes API routing, quota checks, profile loading, conversation loading, recovery selection, onboarding responses, action dispatch, runtime streaming, persistence, artifact naming, and error copy.

Target responsibilities:

- `api/chat/session_context.py`: user, profile, conversation, quota, and history loading.
- `api/chat/recovery_selector.py`: checkpoint vs metadata fallback selection.
- `api/chat/action_dispatcher.py`: cancel, save, breakdown, refine action handling.
- `api/chat/runtime_stream.py`: LangGraph event loop, persistence, final payload assembly, SSE output.
- Router remains transport, auth, request validation, and response construction.

### `src/argus/agent_runtime/stages/interpret_actions.py`

Classification: split now before private launch.

Why:

- It mixes structured confirmation actions, text approval deferral, result refinement, failed-action retry, pending artifact follow-ups, result artifact follow-ups, and user-facing copy.

Target responsibilities:

- `stages/actions/confirmation.py`: run/change/cancel confirmation actions.
- `stages/actions/approval.py`: text approval deferral and approval guardrails.
- `stages/actions/result.py`: result-card actions and refinement.
- `stages/actions/retry.py`: failed-action retry rebuilds.
- `stages/actions/followups.py`: pending and result artifact follow-up dispatch.

### `src/argus/agent_runtime/result_followups.py`

Classification: split now before context packet implementation.

Why:

- It mixes schema, prompts, LLM invocation, fact-bank extraction, rendering, guardrails, fallbacks, and metric formatting.
- Context packets will naturally expand this file unless it is split first.

Target responsibilities:

- `result_followups/schema.py`
- `result_followups/fact_bank.py`
- `result_followups/llm.py`
- `result_followups/render.py`
- `result_followups/guardrails.py`
- `result_followups/fallbacks.py`

### `src/argus/domain/engine_launch/result_facts.py`

Classification: split now before structured next experiments.

Why:

- It mixes deterministic execution facts with user-facing next-test prose.

Target responsibilities:

- `result_facts.py`: execution note, rule summary, factual labels.
- `next_experiments.py`: structured next-experiment option generation.
- LLM/fallback layers phrase next experiments for users.

### Retired `src/argus/api/chat_service.py`

Classification: retired compatibility path.

Why:

- It was mostly a re-export facade over split `api/chat/*` modules.
- It carried underscored compatibility aliases and heavyweight imports.
- Keeping it available encouraged new work to target the wrong path.

Target state:

- The file stays deleted.
- No new code imports `argus.api.chat_service`.
- Tests import focused modules.
- Static guard tests fail if launch code or tests import the retired facade.

### Split Later Candidates

These are real candidates but should wait until the higher-risk launch path is stable:

- `src/argus/api/chat/breakdown.py`
- `src/argus/agent_runtime/stages/interpret.py`
- `src/argus/agent_runtime/stages/execute.py`
- `src/argus/domain/engine_launch/adapter.py`
- `src/argus/agent_runtime/graph/workflow.py`

### Keep As-Is

- `src/argus/domain/engine.py`

It is already a facade over focused backtesting modules and should remain stable as compatibility surface during launch hardening.

## 7. Context Intelligence Roadmap

Context intelligence exists to improve explanation and curiosity, not to determine simulation truth.

### ContextPacket Philosophy

A `ContextPacket` is a structured, source-scoped packet of retrieved facts. It should be attached to result explanation and follow-up flows, not to the run execution contract.

Context packets are immutable snapshots once attached to a completed run explanation. Refreshed news, macro updates, and late provider updates may create new packets, but they must not rewrite prior explanations.

A completed run explanation should remain replayable from persisted run facts plus attached context packet references without requiring live provider fetches. Live provider fetches may enrich future turns; they are not required to replay the completed explanation.

Minimum shape:

```json
{
  "id": "context-packet-id",
  "kind": "macro_regime | symbol_news | corporate_action | market_mover",
  "provider": "fred | alpaca",
  "scope": {
    "symbols": ["AAPL"],
    "asset_class": "equity",
    "benchmark": "SPY",
    "start": "2025-01-01",
    "end": "2026-01-01"
  },
  "retrieved_at": "timestamp",
  "coverage": {
    "start": "timestamp",
    "end": "timestamp"
  },
  "facts": [
    {
      "id": "fact-id",
      "label": "Federal funds rate rose during the period",
      "value": "5.25%",
      "date": "2025-06-01",
      "source_url": "https://...",
      "confidence": "source_reported",
      "applies_to": ["macro_regime"]
    }
  ],
  "limitations": ["Context is explanatory and not part of simulation execution."],
  "used_for": "explanation",
  "not_for": "simulation_truth"
}
```

### FRED Usage

Use FRED for macro regime context:

- Interest rates.
- Inflation.
- Unemployment.
- Recession indicators.
- Broad liquidity or rate-cycle framing.

Default curated series:

- `FEDFUNDS`, `DGS10`, `DGS2`, and `T10Y2Y` for rate-cycle context.
- `CPIAUCSL` and `CPILFESL` for seasonally adjusted inflation context.
- `UNRATE`, `PAYEMS`, and `INDPRO` for seasonally adjusted labor and activity context.
- `USREC` for recession-window context.

FRED should answer questions like:

- "What was the macro environment during this period?"
- "Did this run happen during a rising-rate cycle?"
- "Should we compare this strategy across different regimes?"

FRED should not generate trade signals or alter engine outputs.

### Alpaca Usage

Use Alpaca for scoped symbol and market context:

- Corporate actions around the run period.
- Recent symbol-specific news.
- Market movers or most actives only as scoped context, not generic feed content.

Corporate actions are closer to deterministic event context. News and movers are narrative context and must be framed as possible backdrop, not causal proof.

### Cache / Freshness / Cost Direction

- Supabase Postgres is the durable store for conversations, messages, strategies, runs, route receipts, context packets, and attached packet references.
- Supabase Edge Functions may isolate provider fetches for FRED macro refresh, Alpaca corporate-action/news packets, and provider-health checks.
- Supabase Cron or `pg_cron` may refresh curated FRED series and clean up stale context packets.
- Render in-memory cache or Redis-style key-value storage may cache hot OHLCV/provider responses and short-lived context lookups for latency.
- Cache must not become simulation truth unless the cached object carries provider, scope, timestamp, and reproducible source metadata.
- Context packets must expire or be marked stale by fact type: longer for closed historical OHLCV and FRED releases, medium for corporate actions, short for news, and very short for movers or most actives.
- Context packet collection is best-effort and latency-bounded. Provider failures may remove context enrichment, but they must not block or rewrite completed simulation truth.
- LLM freeform chat should not be broadly cached; cache only structured deterministic inputs or outputs when replay-safe.

### Deferred Context Systems

The following are intentionally deferred:

- Tavily: useful retrieval infrastructure, but not needed before FRED/Alpaca packets prove value.
- Perplexity: useful premium synthesis, but too answer-oriented and costly for default runtime.
- SEC ingestion: too broad for the current loop.
- Earnings transcript ingestion: valuable later, not pre-private-launch.
- Embeddings and broad RAG: deferred by product and data-model direction.
- Generic finance dashboards: violate the chat-first experimentation loop.

## 8. LLM Tiering Architecture

Argus should use the cheapest reliable model per task, with fallbacks in the same capability class.

### Tier 0: Deterministic Runtime

No LLM.

Owns:

- Validation.
- IDs.
- State transitions.
- Persistence.
- Provider metadata.
- Engine execution.
- Metrics.
- Fact banks.
- Safety fallback.

### Tier 1: Utility Text

Current config:

- `CUADRAO_UTILITY_MODEL`
- `CUADRAO_UTILITY_FALLBACK_MODEL`

Owns:

- Conversation titles.
- Strategy names.
- Small labels.
- Tiny rewrites.

### Tier 2: Chat and Clarification

Current config:

- `CUADRAO_CHAT_MODEL`
- `CUADRAO_CHAT_FALLBACK_MODEL`

Known current model intent from branch discussion:

- Primary chat model: `qwen/qwen3.5-9b`
- General fallback model: `deepseek/deepseek-v4-flash`

Owns:

- Normal chat.
- Clarification questions.
- Beginner education.
- Short result summaries.
- Unsupported-request redirection.

### Tier 3: Structured Planning

Current config:

- `CUADRAO_STRUCTURED_MODEL`
- `CUADRAO_STRUCTURED_FALLBACK_MODEL`

Known current model intent from branch discussion:

- Structured model: `mistralai/mistral-small-3.2-24b-instruct`

Owns:

- JSON/schema extraction.
- Durable artifact IR.
- Strategy draft edits.
- Focused repair passes.
- Signal-rule and artifact edit planning.

### Tier 4: Context Synthesis

Current config:

- `CUADRAO_CONTEXT_MODEL`
- `CUADRAO_CONTEXT_FALLBACK_MODEL`

Owns:

- Retrieved market, macro, and event context synthesis.
- "Why did this happen?" experiences.
- Contextual follow-up suggestions from engine facts plus context packets.

Tier 4 should not browse freely. It should synthesize from structured packets.

### Fallback Philosophy

- Fallbacks must remain observable internally.
- Fallbacks should stay in the same capability class.
- A fallback must not silently downgrade structured reliability or simulation trust.
- Any fallback used for a launch-critical path must appear in route receipts.
- A failed LLM path should degrade to safe deterministic output when possible.
- If no safe deterministic output exists, the user should get a recoverable message and preserved state.

### Route Receipts

Route receipts should exist for every LLM-backed task and should be persisted or logged in a way that supports evaluation.

Minimum receipt fields:

- `task`
- `tier`
- `primary_model`
- `resolved_model`
- `fallback_model`
- `fallback_used`
- `schema_name`
- `latency_ms`
- `outcome`
- `error_code`
- `token_usage` when available
- `context_packet_ids` when available

Route receipts are the internal cost, latency, fallback, and failure-mode record. They support evals, debugging, and production review; they are not user-facing product copy.

### Evaluation Layer

Evals should optimize for normal human curiosity patterns, not idealized quant phrasing. They should assert semantic success, groundedness, recovery, hallucination prevention, and no unsupported investment advice.

Exact strings belong only to protocol, static UI, and safety fallback. Evals should record route receipts, fallback use, latency, and failure mode.

## 9. Private Launch Acceptance Gate

1. Current failing signal-repair test is green.
2. User can run one real browser flow:
   new chat -> messy investing idea -> interpretation -> confirmation card -> run -> persisted result -> reload -> grounded follow-up.
3. No user-facing result/explanation depends on exact deterministic prose except safety fallback.
4. Route receipts exist for LLM task, tier, model, fallback, latency, and outcome.
5. Provider metadata correctly reflects Alpaca/Kraken source.
6. Saved result actions and reload recovery work after refresh.
7. Next experiments are structured options, not only canned prose.
8. FRED/Alpaca context packets are defined before implementation.
9. `chat_service.py` remains deleted.
10. Docs/env examples use `ARGUS_*` as primary config.
11. All critical failures preserve conversation state and give the user a recoverable next step.
12. Tier 4 contextual explanations remain grounded in engine facts and structured context packets, with no unsupported causal claims.
13. The eval harness includes messy-human prompts and semantic groundedness checks, not only unit tests.
14. Cache/freshness rules are defined for OHLCV, FRED, Alpaca corporate actions, news, route receipts, and context packets.
15. There is one authoritative conversational runtime path; no duplicate chat brain or parallel persistence path remains in the launch loop.
16. Completed runs remain replayable and explainable from persisted run facts plus attached context packet references without requiring live provider calls.

This gate excludes authentication and onboarding unless explicitly brought into scope. It defines private-launch readiness for the core experimentation loop only.

## 10. Strategic Non-Goals

These are intentionally not being pursued before validation:

- Tavily integration.
- Perplexity integration.
- SEC ingestion.
- Transcript indexing.
- Embeddings or broad RAG.
- Generic finance dashboards.
- Broad strategy expansion.
- Mobile-first pivot.
- Social platform mechanics.
- Brokerage or real-money trading.
- Enterprise or institutional tooling.
- Custom scripting.
- Mixed-asset backtests.

These may become valuable later. They are not prerequisites for proving the private-launch loop.

## 11. Common Pitfalls / Anti-Patterns to Avoid

- Do not confuse deterministic truth with deterministic personality.
- Do not let exact-string tests control LLM-owned language.
- Do not add Tavily, Perplexity, SEC, transcripts, embeddings, dashboards, or broad retrieval before the core loop is browser-proven.
- Do not make Alpaca movers/news into a generic market feed.
- Do not let context packets alter simulation truth.
- Do not let refreshed context rewrite completed explanations.
- Do not silently mislabel provider metadata.
- Do not restore or route new code through `chat_service.py`.
- Do not refactor for architecture purity without reducing launch risk.
- Do not expand strategy breadth before fixing messy-human interpretation.
- Do not let users dead-end on unsupported requests; redirect to nearby testable ideas.
- Do not optimize model choice before route receipts and evals exist.
- Do not allow silent fallback degradation.
- Do not keep planning once the steering map is production-steerable and browser-loop proof is the next risk reducer.
- Do not make Strategies into a dashboard; keep it as saved investing ideas that relaunch conversation.

## 12. Historical Architecture Anti-Patterns

These are project-specific mistakes Argus should not repeat:

- Do not patch gates merely to make checks pass. A fix must address the macro pattern, ownership boundary, or contract failure that caused the gate to fail.
- Do not replace one brittle branch with another. If natural language failed, improve interpretation, validation, semantic contracts, or recovery state rather than adding another hardcoded phrase path.
- Do not loosen tests in a way that hides broken behavior. Relax exact wording only where language is LLM-owned; keep facts, state transitions, artifacts, provider metadata, and safety constraints strict.
- Do not confuse a compatibility facade with the new architecture. Facades can protect behavior during migration, but they should not remain the path for new product logic.
- Do not create two chat brains. Router-side orchestration, legacy helpers, fallback copy, and LangGraph runtime state must not compete for conversational ownership.
- Do not mix API transport, persistence, LLM orchestration, domain validation, recovery copy, and result formatting in one module when that coupling raises launch risk.
- Do not let frontend presentation invent runtime truth. The web app renders backend-provided stream events, cards, actions, and persisted metadata; it does not reconstruct strategy state from prose.
- Do not treat deterministic fallback copy as the normal assistant voice. Fallbacks preserve safety and state; LLM-owned tiers should handle ordinary explanation, education, and continuation.
- Do not treat browser QA as optional after tests pass. Chat continuity, reload, result actions, recents, and recovery must be proven in the browser before private launch.
- Do not claim context as causality. FRED and Alpaca context can provide backdrop and hypotheses, but only simulation outputs are result truth.
- Do not fix provider/source bugs cosmetically. Incorrect source metadata is a trust failure and must be corrected at the data/contract boundary.
- Do not optimize locally at the expense of the product loop. A small patch that makes one test pass but worsens idea -> interpretation -> confirmation -> run -> reload -> follow-up is a regression.

## 13. Canon Docs to Read Before Work

Read these planning documents before implementation:

- `docs/PRODUCT.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACT.md`
- `docs/DATA_MODEL.md`
- `docs/CONVERSATIONAL_RUNTIME.md`
- `docs/QA_CONVERSATIONAL_TRANSCRIPTS.md`
- `docs/ARGUS_SYSTEM_STEERING.md`

`docs/ARGUS_SYSTEM_STEERING.md` is the pre-private-launch hardening map. The product, API, data, architecture, conversational runtime, and QA transcript docs remain the canonical source-of-truth documents for their respective domains.

## 14. Implementation Order

The next hardening and validation work should proceed top down:

1. Preserve runtime integrity.
   - Keep OpenRouter signal-repair coverage green as messy prompts expand.
   - Keep provider metadata explicit and tested.
   - Keep route receipts persisted for launch-critical LLM paths.
   - Verify action/reload trust in browser QA.

2. Reduce conversation brittleness.
   - Relax exact-string tests where LLM language is expected.
   - Keep deterministic tests for facts, protocol, state, and safety.
   - Move user-facing deterministic personality copy behind semantic contracts.

3. Modularize the files that block launch hardening.
   - Split `llm_interpreter.py` around repair and shape responsibilities.
   - Split `agent.py` around session, recovery, action dispatch, and runtime stream.
   - Split `interpret_actions.py` by action family.
   - Stop new imports from `chat_service.py`.

4. Keep next experiments structured.
   - Keep next-test generation as structured options, not prose-only copy.
   - Ensure reload/follow-up paths can reuse those options.
   - Let LLM tiers phrase them.

5. Validate context intelligence without overreaching.
   - Browser-prove `ContextPacket` attachment and replay.
   - Attach context packet references to fact banks/message metadata.
   - Use FRED macro context first.
   - Use Alpaca corporate actions and scoped news next.

6. Prove the browser loop.
   - Run the full private-launch flow in a real browser.
   - Verify reload, save, breakdown, refinement, and follow-up continuity.
   - Treat browser evidence as the final acceptance gate.

7. Only then consider new product breadth.
   - Do not add broad retrieval, dashboards, social mechanics, or new strategy families until real private users validate the core loop.
