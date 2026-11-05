# Argus Agentic Market Shift Decision Memo

**Archived September 26, 2026.** This is a dated record, not standing product
or execution guidance. Its original present-tense claims and open questions
belong to the recorded period. Use the [MVEE](../specs/argus-minimum-viable-ecosystem-experience.md)
and [documentation authority](../DOCUMENTATION_AUTHORITY.md) for current work.

---

Date: 2026-06-14

Status: Historical strategic and technical rationale. Conflicting product
experience direction is superseded by the
[MVEE](../specs/argus-minimum-viable-ecosystem-experience.md), September 26, 2026.
See [documentation authority](../DOCUMENTATION_AUTHORITY.md) before taking work.
The original scope and dated pointers below are preserved as historical context,
not a current execution queue.

Audience: Founder, Codex, future product/spec work

Scope: Strategic source for Private Alpha Next product work. It captures the
full reasoning cycle triggered by the Robinhood/Alpaca/ChatGPT agentic trading
discovery and translates it into product, architecture, leverage, and roadmap
implications for Argus. Use `docs/specs/argus-active-roadmap.md` for the current
execution board and use this memo, including the addenda, for slice-specific
onboarding before planning or implementation.

**2026-08-06 pointer.** The active board pulls its five priorities from this
memo; see section 18 for what the 2026-08-06 competitive review changed and
what it did not.

Related product-thesis trial: source context only; not required reading for specs.

## 1. Why This Conversation Started

The conversation began with a sharp founder concern:

> Is Argus cooked?

The immediate trigger was Robinhood's public Agentic Trading support article:

- Robinhood Agentic Trading overview: https://robinhood.com/us/en/support/articles/agentic-trading-overview/

Robinhood describes an Agentic Trading account that can be connected to third-party AI agents through the Robinhood Trading MCP. Robinhood frames MCP as a way for an AI agent to connect to external apps and services and take actions on the user's behalf. The article lists account/portfolio reading, buying power, positions, order history, portfolio/risk analysis, market data analysis, and order placement as things a connected agent may do, depending on setup and permissions.

The second trigger was the founder's live evidence using ChatGPT/Codex with an Alpaca plugin, a Robinhood connection, and bank/Plaid-connected context. In screenshots, the agent:

- verified that the Robinhood connection existed;
- read the brokerage account list and identified account-level capabilities;
- explained what it could do with the Robinhood connection;
- described read-only account analysis, pre-trade review, and real order placement after explicit confirmation;
- explained account-specific option-trading constraints;
- discussed available backtesting capabilities;
- ran a BTC buy-and-hold backtest for the year-to-date prompt in one attempt;
- returned metrics, caveats, and an explanation of the result.

The founder's fear was rational:

- Argus had spent major engineering time hardening a natural-language-to-backtest loop.
- The market appeared to move underneath the product.
- A frontier model plus broker/data MCPs appeared to do the same prompt successfully, faster, with a broader tool surface.
- Robinhood's MCP suggested broker execution and agentic investing workflows were becoming platform primitives rather than defensible startup features.

The first conclusion of the conversation was:

Argus is not cooked, but the old/simple version of Argus is cooked.

The old/simple version means:

- chat prompt;
- basic strategy interpretation;
- basic backtest;
- chart and metrics;
- generic explanation.

That surface is now vulnerable because general-purpose AI agents with financial MCPs can already approximate it. The stronger Argus thesis has to move above raw backtest execution.

## 2. What The Robinhood Discovery Revealed

### 2.1 MCP lowers the barrier for broker-native agent workflows

Robinhood's article is important because it shows that a broker is not merely exposing an API. It is exposing an agent-facing tool surface through MCP.

Source:

- Robinhood Agentic Trading overview: https://robinhood.com/us/en/support/articles/agentic-trading-overview/
- Model Context Protocol introduction: https://modelcontextprotocol.io/docs/getting-started/intro

The practical implication:

Broker integrations are moving from "developer builds custom API integration" to "agent connects to a standardized tool server."

This matters because one possible Argus future was:

> Argus is valuable because it connects natural language to investing/trading actions.

That is less defensible now. If Robinhood, Alpaca, QuantConnect, and others provide MCP/tool surfaces, general agents can connect to those tools directly.

### 2.2 Broker execution is not the moat

Robinhood explicitly positions the agent as capable of portfolio analysis, strategy automation, order placement, and account access. It also warns that users remain responsible for trades and that AI agents can make errors, misinterpret instructions, and act on incomplete information.

Source:

- Robinhood risks and disclosures in the Agentic Trading overview: https://robinhood.com/us/en/support/articles/agentic-trading-overview/

This creates an opening for Argus.

Robinhood can enable the trade.

Argus can become the layer that asks:

- Should this idea survive review?
- What assumptions are embedded in it?
- What happened when we tested similar ideas before?
- What evidence supports or weakens it?
- What risk would the user be accepting?
- Is the user repeating a behavior they later regretted?
- Has this idea been compared against alternatives?

That is the pre-trade intelligence layer.

### 2.3 General AI can do impressive one-off analysis, but one-off analysis is not durable product memory

The founder's screenshots showed that a frontier agent could answer a complicated prompt and produce useful outputs. That is a real competitive signal.

But the output was still fundamentally a chat transcript:

- It did not become a durable Argus idea object.
- It did not create a persistent idea version history.
- It did not become a trusted evidence dossier tied to a canonical spec.
- It did not automatically compare against the user's prior rejected or accepted ideas.
- It did not become a decision journal entry.
- It did not expose a product-native memory inspector.
- It did not become a reusable pre-trade review artifact.

The revised Argus thesis is therefore:

> Argus should not compete to be the agent that can answer one prompt. Argus should compete to be the system where investing ideas become tested, remembered, compared, and trusted before they ever become trades.

## 3. The Updated Moat

The phrase that emerged in the conversation was:

> The moat is the pre-trade intelligence layer plus durable user memory.

This needs to be made concrete.

It is not a vague "AI remembers stuff" feature.

It is not only a note-taking app.

It is not only RAG over chat transcripts.

It is a product system with durable objects and visible user value.

## 4. What "Pre-Trade Intelligence Layer" Means As Product

The pre-trade intelligence layer exists between curiosity and broker execution.

The user has a messy idea:

> Buy and hold ETH for the last 8 months with 100k.

or:

> What if I had bought BTC this year so far?

or:

> Compare Apple to SPY over the last year.

or:

> I like this result. Should I try this in Robinhood?

Argus' job is not merely to answer. Argus' job is to transform the idea into a trustworthy decision object.

### 4.1 The layer includes these feature surfaces

#### Idea Ledger

Every serious user idea becomes a durable idea record.

The user should be able to see:

- ideas they tested;
- ideas they rejected;
- ideas they marked as promising;
- ideas they wanted to revisit;
- ideas grouped by asset, strategy type, or theme.

This is not a generic diary. It is an investing idea ledger.

#### Idea Version History

If the user changes an assumption, Argus stores the change as a version:

- capital changed from 10,000 to 100,000;
- asset changed from BTC to ETH;
- date range changed from year-to-date to last 12 months;
- benchmark changed from SPY to BTC;
- cadence changed from daily to weekly;
- strategy changed from buy-and-hold to RSI.

This gives Argus a durable view of how the idea evolved.

#### Evidence Dossier

Each run becomes an immutable evidence artifact:

- canonical idea spec;
- asset identities;
- date range;
- starting capital;
- benchmark;
- data source;
- market data coverage window;
- engine version;
- assumptions;
- result metrics;
- equity curve;
- caveats;
- failure/retry history;
- explanation generated from facts, not invented prose.

This is where trust compounds.

#### Decision Note

After a result, Argus can lightly ask:

- Save as "watching"?
- Mark as "rejected"?
- Mark as "promising"?
- Add a note?
- Revisit later?

The decision note is not a heavy journaling surface. It is a small decision-journal capture attached to evidence.

#### Comparison Loop

Argus should answer:

- Is this better than my last BTC idea?
- Compare this ETH run to the BTC run I saved last week.
- Show my best ideas by drawdown, not return.
- Which ideas did I reject because the drawdown was too high?
- Did this strategy outperform the benchmark more consistently than my prior one?

This becomes much easier once ideas, versions, and result artifacts are structured.

#### Pre-Trade Review Packet

Before broker handoff, Argus can assemble:

- idea summary;
- assumptions;
- evidence;
- user decision notes;
- risks;
- caveats;
- comparison with alternatives;
- "what would invalidate this" notes;
- whether the user has seen similar failures before.

This is the artifact that can later be passed to Robinhood/Alpaca/Broker MCPs.

## 5. Where The Moat Lives In The Vertical Stack

The stack discussed in the conversation was:

```text
messy user idea
-> language/runtime spine
-> canonical idea spec
-> backtest/evidence engine
-> result artifact
-> shareable sanitized excerpt
-> decision memory
-> comparison loop
-> optional broker/export handoff later
```

Below is what each layer means after the market shift.

### 5.1 Messy user idea

This is the raw user prompt:

- English;
- Spanish;
- code-switched;
- spoken into a microphone and transcribed;
- incomplete;
- slangy;
- typo-ridden;
- sometimes with a ticker;
- sometimes with a company name;
- sometimes with a selected mention through `@`;
- sometimes with a relative date like "this year so far";
- sometimes with an implicit strategy.

Argus should not require perfect wording.

The founder repeatedly emphasized that Spanish-speaking alpha users will be messy and that language agnosticism is not the same as merely translating the UI.

The voice implication is important:

Once Argus can understand messy typed language, voice becomes a natural product extension because spoken investing ideas are even messier than typed ones. Voice should not become a separate conversational brain. It should become another way for the user to put a rough idea into the same language/runtime spine.

Best first product shape:

```text
tap or hold mic
-> record audio
-> transcribe speech to text
-> place transcript in the existing composer
-> user can edit
-> user presses Send
-> normal Argus chat/runtime flow
```

Do not auto-send after recording in the first version. In a financial product, the confirmation moment matters. A mistranscription such as "buy 100k ETH" instead of "backtest 100k ETH" could change the intent category entirely. The user should see the transcript and decide when to send it.

### 5.2 Language/runtime spine

The language/runtime spine is where the LLM interprets messy language into structured intent.

Current Argus docs already support this direction:

- Product truth says conversation is the product and the backtesting engine is critical infrastructure.
- Architecture says OpenRouter is used for chat intelligence, onboarding guidance, strategy extraction, and explanations.
- Architecture says LangGraph owns the conversational runtime and Supabase owns durable product state.

Local sources:

- `docs/PRODUCT.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACT.md`
- `docs/DATA_MODEL.md`

External leverage:

- OpenRouter model routing and auto-router: https://openrouter.ai/docs/guides/routing/routers/auto-router
- OpenRouter provider routing: https://openrouter.ai/docs/guides/routing/provider-selection
- OpenRouter BYOK: https://openrouter.ai/docs/guides/overview/auth/byok
- OpenRouter structured outputs/tool features can be used as part of the same provider surface: https://openrouter.ai/docs
- Perplexity Agent API prompt guide: https://docs.perplexity.ai/docs/agent-api/prompt-guide
- Perplexity Agent API overview: https://docs.perplexity.ai/docs/agent-api/quickstart

Recommendation:

Do not expose a normal-user model catalog in Alpha.

Reason:

- Most users do not want to choose Claude vs Mistral vs GPT.
- It raises cognitive load.
- It may create inconsistent product behavior.
- It can increase costs.
- It turns Argus into a model playground instead of an investing idea product.

Better Alpha surface:

- default smart routing;
- internal task-specific profiles;
- optional later "Fast" vs "Deeper" mode;
- possibly founder/admin-only model override;
- maybe BYOK later for power users, but not a core consumer feature.

The founder's existing architecture already minimizes cost through tiering/fallback. That is the right direction. The next improvement is not a user-facing model catalog. It is:

- better evaluation harnesses;
- task-specific model budgets;
- structured outputs;
- reasoning budget for ambiguous interpretation;
- fallback only when quality fails;
- route receipts for observability.

#### Voice input inside the language/runtime spine

Voice should be integrated at the edge of the existing runtime, not inserted as a new runtime.

The correct boundary is:

```text
Audio capture
-> STT provider
-> transcript
-> composer text
-> existing Argus interpreter
```

This has several advantages:

- the user can inspect and correct the transcript;
- Argus avoids a second "voice brain";
- the canonical idea spec still comes from the same interpreter;
- transcript quality can be measured separately from interpretation quality;
- voice failure does not corrupt the chat state;
- the same product path works for web/PWA now and native iOS later.

Sources for production-grade voice options:

- OpenAI audio overview: https://platform.openai.com/docs/guides/audio
- OpenAI speech-to-text: https://platform.openai.com/docs/guides/speech-to-text
- OpenAI Realtime API: https://platform.openai.com/docs/guides/realtime
- OpenAI voice agents: https://platform.openai.com/docs/guides/voice-agents
- OpenRouter audio input/output: https://openrouter.ai/docs/guides/overview/multimodal/audio
- OpenRouter STT endpoint: https://openrouter.ai/docs/guides/overview/multimodal/stt
- OpenRouter TTS endpoint: https://openrouter.ai/docs/guides/overview/multimodal/tts
- ElevenLabs API pricing and Scribe STT: https://elevenlabs.io/pricing/api
- Wispr Flow pricing and dictation UX reference: https://wisprflow.ai/pricing
- MDN SpeechRecognition browser support warning: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition

Pricing snapshot as of 2026-06-14:

- OpenAI `gpt-4o-mini-transcribe`: about `$0.003/minute`, or about `$0.18/hour`.
- OpenAI `gpt-4o-transcribe`: about `$0.006/minute`, or about `$0.36/hour`.
- OpenAI `whisper-1`: historically about `$0.006/minute`.
- OpenAI `gpt-realtime-whisper`: about `$0.017/minute`, or about `$1.02/hour`.
- ElevenLabs Scribe STT: listed around `$0.22/hour`.
- ElevenLabs Scribe realtime STT: listed around `$0.39/hour`.
- Wispr Flow: consumer dictation app pricing around `$15/user/month`, or lower on annual plans, but this is product inspiration rather than an embeddable Argus backend.

These prices should be refreshed before implementation or vendor lock-in. The useful conclusion is not the exact cents. The useful conclusion is that production-quality STT is affordable enough for Alpha if usage is bounded and measured.

Recommended Alpha path:

```text
Primary: OpenAI or OpenRouter STT, starting with the cheapest acceptable transcribe model
Fallback: higher-quality transcribe model or ElevenLabs Scribe for difficult Spanish/noisy audio cases
Later: realtime speech-to-speech only after the text runtime and memory loop prove value
```

OpenRouter can be useful because it gives Argus a provider-routing surface for audio as well as text. However, voice should still terminate into a transcript before Argus interpretation. Sending raw audio directly into a multimodal reasoning model may be useful later, but it makes evaluation, correction, cost tracking, and safety harder for the first production voice slice.

### 5.3 Canonical idea spec

This is where the LLM output becomes an Argus-owned structured product object.

The spec should not be VectorBT-shaped, LEAN-shaped, Alpaca-shaped, or Robinhood-shaped.

It should be Argus-shaped.

Example fields:

- `idea_id`
- `idea_version_id`
- `conversation_id`
- `user_id`
- `language_observed`
- `language_preference`
- `asset_universe`
- `asset_class`
- `strategy_type`
- `strategy_parameters`
- `strategy_conditions`
- `indicator_requirements`
- `date_range`
- `starting_capital`
- `cadence`
- `benchmark`
- `fees_assumption`
- `slippage_assumption`
- `data_requirements`
- `confidence`
- `evidence_spans`
- `unsupported_or_ambiguous_fields`

Current Argus has basic canonical strategy/backtest structure. The market shift says this layer needs to be promoted from internal plumbing to the foundation of durable product memory.

Indicators belong here as canonical strategy primitives, not as frontend menu
items or language-specific phrases. They are one of the most neglected parts of
the stack so far because making the basic loop work was correctly more urgent.
That was reasonable for survival, but it cannot remain implicit if Argus is
going to become a serious evidence layer.

The right shape is:

```text
Messy user idea
-> LLM semantic interpretation
-> CanonicalIdeaSpec.strategy_conditions
-> Indicator/capability registry validation
-> BacktestEngine execution
-> EvidenceArtifact
```

Example canonical indicator primitives:

- moving-average crossover;
- RSI threshold;
- price breakout/reversion;
- volatility or drawdown constraint later;
- options greeks later, if options evidence becomes validated demand.

Do not hardcode natural-language indicator phrases into core runtime files.
The LLM should interpret "RSI under 30", "cuando el RSI esté bajo", or
"oversold" into a canonical condition. Code should only validate whether that
condition is executable, which parameters are required, and whether the chosen
engine/data source can support it.

### 5.4 Backtest/evidence engine

This is not the moat by itself. It is trust infrastructure.

Options discussed:

#### Current/simple Argus engine

Pros:

- already integrated;
- matches current product shape;
- easier to control;
- easier to explain;
- no new licensing risk.

Cons:

- too basic;
- may underdeliver once users expect broader metrics;
- limited strategy realism.

#### VectorBT open source

Sources:

- VectorBT terms: https://vectorbt.dev/terms/
- VectorBT license: https://vectorbt.dev/terms/license/
- VectorBT PyPI: https://pypi.org/project/vectorbt/
- VectorBT GitHub license: https://github.com/polakowo/vectorbt/blob/master/LICENSE.md

Observed license issue:

VectorBT open source is "fair-code" under Apache 2.0 with Commons Clause. The source is open and free for individuals and organizations to use, but the Commons Clause removes the right to sell products or services whose value derives entirely or substantially from the software's functionality.

Practical conclusion:

- Reasonable for internal validation and free/non-commercial alpha experimentation.
- Risky for paid Argus if the paid value substantially depends on VectorBT-powered backtesting.
- Wrapping it in MCP does not make the licensing issue disappear.
- Forking or deeply modifying it could increase dependence.
- If VectorBT becomes perfect for Argus, get written commercial permission or a commercial license before monetizing.

Strategic conclusion:

Use VectorBT as a validation accelerator, not as the long-term company spine.

#### VectorBT Pro

Source:

- VectorBT Pro terms: https://vectorbt.pro/terms/terms-of-use/
- VectorBT Pro software license: https://vectorbt.pro/terms/software-license/

Conclusion from earlier conversation:

- Pro has stronger commercial-use restrictions and requires commercial approval/licensing for productized use.
- It is not a clean default commercial backend for Argus.

#### QuantConnect Cloud MCP

Sources:

- QuantConnect MCP key concepts: https://www.quantconnect.com/docs/v2/ai-assistance/mcp-server/key-concepts
- QuantConnect terms: https://www.quantconnect.com/terms/

QuantConnect's MCP is real and powerful. It exposes tools for projects, compilation, backtests, optimizations, live algorithms, research notebooks, datasets, and notifications.

The issue is commercial product fit.

QuantConnect Cloud terms include restrictions around commercial exploitation of the site/content and accessing the site to build similar or competitive products. That makes it risky as the production backend for Argus without a deal.

Conclusion:

- Good research/reference surface.
- Useful to understand what an agentic quant workflow can look like.
- Not a clean production dependency for commercial Argus unless there is explicit agreement.

#### LEAN self-hosted

Sources:

- LEAN site: https://www.lean.io/
- LEAN GitHub license: https://github.com/QuantConnect/Lean/blob/master/LICENSE

LEAN is more promising as a possible self-hosted engine because it is open-source under Apache 2.0. It is much heavier than Argus likely needs for Alpha, but it may be a better long-term candidate than VectorBT if the goal is a powerful, commercially cleaner execution engine.

Caveat:

- Data licensing remains separate.
- QuantConnect datasets are not automatically usable in Argus.
- A self-hosted engine still needs licensed market data and careful product-specific result shaping.

#### Argus-native engine

This is the likely long-term path if Argus validates demand.

The founder proposed:

- keep Argus free while validating;
- use third-party engine leverage as needed;
- learn which backtest capabilities users actually need;
- then build the smallest fast Argus-native evidence engine;
- monetize only once the commercial runtime is clean or licensed.

This is strategically sound.

Important framing:

Do not "replicate VectorBT."

Build the smallest Argus-native evidence engine that supports validated Argus workflows.

#### Indicator capability layer

Indicators are infrastructure, not the product headline. More indicators will
not save Argus by themselves. But without a small trusted indicator layer, Argus
risks feeling like a polished buy-and-hold toy instead of a real investing idea
validation product.

The current state needs a full audit before implementation planning:

- Which indicators and strategy conditions already exist in code?
- Which ones are actually executable by the current engine?
- Which ones only appear as language, labels, examples, tests, or stale docs?
- Which ones are supported in English but brittle or absent in Spanish?
- Which ones are blocked by data requirements, not interpretation?
- Which ones produce evidence that users can trust and edit?
- Which ones are silently overpromised by starter chips or assistant responses?

The audit should produce a current-state map:

```text
Requested condition -> canonical condition -> capability support -> engine support -> evidence output -> UX/editability
```

Recommended near-term posture:

- keep buy-and-hold excellent as the trust baseline;
- support only a tiny indicator set at first;
- make each indicator editable, explainable, and reproducible;
- prefer RSI threshold and SMA/EMA crossover before broader breadth;
- do not ship a giant indicator catalog;
- let user demand and failed prompts decide expansion.

This fits the pivot because indicators strengthen the evidence engine, but the
moat remains the full loop: evidence, memory, comparison, sharing, and eventual
pre-trade handoff.

#### Future coverage pillars

The founder identified a future coverage map:

- traditional equities and buy-and-hold;
- crypto;
- forex/currency pairs plus indicators;
- options.

This is directionally coherent, but options should be treated as a later evidence module, not as a near-term readiness requirement. Options backtesting requires materially more infrastructure than equity/crypto/forex spot testing:

- option chains;
- expirations;
- strike selection;
- bid/ask and spread assumptions;
- greeks;
- liquidity constraints;
- assignment/exercise assumptions;
- multi-leg strategy representation;
- stronger risk and suitability disclosures.

The product principle remains the same: validate demand first, build only the subset users actually need, and keep all engines behind the canonical Argus evidence contract.

### 5.5 Result artifact

Current Argus is building result cards, charts, quick takes, and explanations.

The market shift says the result artifact must become more than:

- a chart;
- ending value;
- gain/loss;
- benchmark comparison;
- max drawdown;
- explanation.

The result artifact should become a compact evidence dossier.

Potential artifact sections:

- setup summary;
- asset class;
- strategy;
- date range;
- starting capital;
- data source;
- benchmark;
- assumptions;
- equity curve;
- key metrics;
- risk readout;
- comparison to benchmark;
- what changed versus previous version;
- caveats;
- reproducibility/provenance;
- decision capture;
- next supported experiments.

The artifact should be durable, shareable internally, and later convertible into a pre-trade review packet.

#### Visual evidence posture

Argus should keep the current chart philosophy: simple, elegant, intuitive, and
chat-native. The result card should not become a dashboard or trading terminal.
The current implementation uses TradingView Lightweight Charts as a compact
baseline portfolio equity curve with executed-fill markers, which matches the
existing product contract: charts are evidence, not a workstation.

The default hero visual should remain:

- one aggregate portfolio equity curve;
- calm positive/negative baseline styling;
- capped executed entry/exit markers;
- high-signal metrics around the chart;
- no symbol spaghetti for multi-asset runs;
- no full technical-analysis panel by default.

Future chart candidates should be optional evidence views, probably inside
details, breakdowns, comparisons, or shared evidence excerpts:

1. **Benchmark comparison view**: indexed strategy vs benchmark line, both
   starting at 100. Answers: when did the idea actually beat or lag SPY/BTC?
2. **Drawdown / underwater view**: compact below-zero area or histogram.
   Answers: how painful was the ride, not just what was the worst drop?
3. **Indicator evidence view**: only for indicator strategies, such as price or
   equity with entry markers plus a small RSI or moving-average pane. Answers:
   why did Argus enter or exit here?
4. **Idea comparison mini-view**: current idea vs prior version vs benchmark,
   likely product-native metric comparison rather than a dense chart. Answers:
   is this version better than the last one?
5. **Period return strip**: small monthly/weekly positive/negative bars.
   Answers: was performance steady or driven by one period?

Recommended posture:

- keep Lightweight Charts for the default result surface;
- use Advanced Charts as research inspiration, not as the default embedded UI;
- never add chart types just because the library supports them;
- add a chart only when it answers a user question that text and the current
  hero chart do not answer cleanly.

### 5.6 Decision memory

This is the largest new pillar.

The founder asked whether this screams RAG and whether an open-source equivalent exists to the memory systems used by OpenAI/Gemini.

Sources:

- OpenAI memory and new controls: https://openai.com/index/memory-and-new-controls-for-chatgpt/
- OpenAI Memory FAQ: https://help.openai.com/en/articles/8590148-memory-faq
- OpenAI Dreaming post: https://openai.com/index/chatgpt-memory-dreaming/
- LangGraph memory concepts: https://docs.langchain.com/oss/python/concepts/memory
- LangMem launch/concepts: https://www.langchain.com/blog/langmem-sdk-launch
- Mem0 OSS docs: https://docs.mem0.ai/open-source/overview
- Mem0 LangGraph integration: https://docs.mem0.ai/integrations/langgraph
- Mem0 LangChain integration: https://docs.mem0.ai/integrations/langchain
- Mem0 tagging and organizing memories: https://docs.mem0.ai/cookbooks/essentials/tagging-and-organizing-memories
- Mem0 search memory: https://docs.mem0.ai/core-concepts/memory-operations/search
- Mem0 async memory: https://docs.mem0.ai/open-source/features/async-memory
- Mem0 GitHub: https://github.com/mem0ai/mem0
- Graphiti GitHub: https://github.com/getzep/graphiti
- Graphiti/Zep product page: https://www.getzep.com/platform/graphiti/
- Supabase vector columns: https://supabase.com/docs/guides/ai/vector-columns
- Perplexity embeddings quickstart: https://docs.perplexity.ai/docs/embeddings/quickstart
- Perplexity embeddings best practices: https://docs.perplexity.ai/docs/embeddings/best-practices

The important product conclusion:

Do not start with generic AI memory as the source of truth.

Start with structured Argus product memory:

- ideas;
- idea versions;
- runs;
- assumptions;
- result artifacts;
- decisions;
- user preferences;
- comparison links.

Then add embeddings and graph retrieval around that structure.

Decision memory should have at least three layers:

#### Structured memory

This is Supabase/Postgres data:

- idea rows;
- idea version rows;
- evidence artifact rows;
- decision note rows;
- user preference rows;
- event/audit rows.

This is the source of truth.

#### Save Idea / decision state

This is the product version of "memory" that users should feel first.

`Save Strategy` means storing an executable setup.

`Save Idea` means storing the tested thought, its evidence, the user's decision,
and how that decision changes over time.

The smallest version:

- user sees a completed result artifact;
- user marks the idea as `watching`, `promising`, `rejected`, or `revisit_later`;
- user may add a short note;
- Argus stores the decision against the evidence artifact.

The better version:

- one `Idea` can have many `IdeaVersion` records;
- each version has its own canonical spec, run, evidence artifact, and decision;
- Argus can show how the user's thinking changed across versions.

Example:

```text
Idea: ETH exposure
Version 1: Buy and hold ETH, 8 months, $100k -> rejected
Version 2: ETH RSI threshold -> watching
Version 3: ETH vs BTC comparison -> promising
```

The strongest version:

- Argus learns decision patterns from explicit product data;
- Argus can say "you usually reject ideas with drawdowns above 25%" only when
  that pattern is supported by saved decisions;
- Argus suggests a memory or decision label, but asks before making it durable;
- users can inspect, edit, delete, or disable memory.

This preserves trust: the canonical decision state lives in Supabase product
tables, while memory tooling can help retrieve and summarize it.

#### Semantic retrieval

This helps retrieve similar ideas, notes, explanations, and past conversations.

Options:

- Supabase pgvector with Perplexity embeddings or another embedding model;
- Mem0 if Argus wants an off-the-shelf memory lifecycle;
- LangGraph/LangMem if Argus wants memory to stay close to its existing LangGraph runtime.

But semantic retrieval should not own the canonical state.

Mem0 is especially promising as a memory accelerator because it already has:

- LangGraph integration, which fits Argus' active chat runtime;
- LangChain integration, which fits surrounding agent/tooling patterns;
- semantic search with filters, thresholds, and optional reranking;
- tagging/category organization for memories;
- Python and Node SDK paths;
- async memory support for Python services;
- OSS/self-hosted options with configurable components;
- a self-hosted server path that can use Postgres + pgvector.

Recommended architecture:

```text
Supabase product tables
  -> canonical ideas, versions, decisions, evidence artifacts

Mem0 / retrieval layer
  -> semantic recall, tagging, ranked search, agent personalization

LangGraph runtime
  -> retrieves relevant memories as context, never as source-of-truth
```

Argus should evaluate Mem0 for memory lifecycle speed, but should not let Mem0
become the only place where a decision exists. If memory data needs to be hosted
by Argus, Supabase/Postgres plus pgvector and Argus-owned compute should remain
the default control plane, with Mem0 OSS/self-hosted evaluated as the memory
service layer.

#### Memory plus freshness as directional north

This is strategy and product north, not a committed Alpha execution spec.

Argus should not become only a memory journal, because investing memories go
stale. A memory records what mattered to the user at a point in time; it does
not prove that the market, the asset, or the user's thesis still looks the
same today.

The directional product idea:

```text
Memory tells Argus what mattered to the user.
Web/search tells Argus what changed in the world.
Backtesting tells Argus what historical evidence says.
The artifact tells the user what to trust, revisit, or discard.
```

This creates three valid entry points:

1. Idea-first: the user already knows what they want to test, so Argus goes
   directly from messy language to canonical idea spec, confirmation, backtest,
   and evidence artifact.
2. Research-first: the user asks for latest context, news, facts, or a digest,
   so Argus uses a source-backed research lane first, then helps turn the
   context into a testable idea.
3. Memory-first: the user revisits a saved idea, so Argus retrieves the prior
   idea/decision, checks whether it may be stale, refreshes facts when needed,
   and explains what changed before suggesting a next test.

The SOTA product shape is not "remember everything and personalize every
answer." It is:

- retrieve only relevant memories;
- know when a memory may be stale;
- ground stale or temporal claims with current facts;
- separate remembered user intent from current market truth;
- attach refreshed facts and updated tests back to the same idea history.

Staleness triggers should include:

- the user asks "latest", "now", "still", "what changed", "today", or similar
  freshness language;
- a saved idea has not been reviewed in a while;
- price, volatility, benchmark, or drawdown moved materially since the last
  evidence artifact;
- source-backed news, earnings, regulatory events, or macro events appear
  relevant to the saved thesis;
- the original thesis depended on a factual claim that may have changed.

Freshness explanation standard:

- canonical run and evidence deltas state what Argus can calculate directly;
- mechanically verified corporate actions may be stated as facts;
- news, earnings, regulatory, macro, analyst, or other event context must be
  source-backed and time-bounded;
- non-mechanical event relationships use cautious language such as "coincided
  with" or "may have contributed" rather than claiming proven causation;
- the readout remains informational and must not become financial advice or a
  recommendation to buy, sell, or hold.

The SOTA small version:

- completed result artifacts are auto-captured into the idea model;
- explicit user save/pin/decision actions promote captured ideas into stronger
  user-commitment states;
- saved ideas show `Last reviewed`;
- users can ask "what changed since I saved this?";
- Argus can offer "Refresh context" on a saved idea;
- if an old memory is used, Argus says it is old and asks or automatically
  performs a source-backed refresh when the user is clearly asking about now;
- Perplexity/Sonar/Search produces cited fact packets only when the user asks
  for freshness or when the memory staleness trigger is strong.

The larger version:

- opt-in monitors for saved ideas;
- weekly or on-demand "ideas that changed" digests;
- thesis invalidation alerts when the reason an idea was saved no longer
  appears supported;
- change-aware comparison loops that show old evidence, new facts, new test,
  and whether the decision should remain `watching`, `promising`, `rejected`,
  or `revisit_later`;
- user-controlled memory inspector where users can edit/delete memories,
  disable monitors, and see why Argus brought a memory back.

This is where Mem0, Supabase, LangGraph, and Perplexity fit together:

- Supabase stores the durable idea, decision, run, and evidence truth;
- Mem0 helps retrieve and organize relevant user memories, tags, and semantic
  links;
- LangGraph decides whether the current turn is idea-first, research-first, or
  memory-first;
- Perplexity/Search/Sonar grounds current facts when freshness matters.

#### Temporal/graph memory

This can later represent:

- the same idea evolving over time;
- user preference changes;
- contradictions;
- replaced beliefs;
- "the user used to prefer X, then changed to Y";
- strategy themes;
- recurring mistakes;
- evidence relationships.

Graphiti/Zep is interesting here because it is designed for temporal knowledge graphs and provenance.

But this is not MVP unless comparison and memory needs become too complex for relational + embeddings.

### 5.7 Comparison loop

Comparison becomes a natural product surface once decision memory exists.

Examples:

- Compare current backtest to prior version.
- Compare ETH buy-and-hold to BTC buy-and-hold.
- Compare strategy A against strategy B over the same period.
- Show all ideas with lower drawdown than this one.
- Show ideas that beat benchmark but had worse drawdowns.
- Show the user's best-performing rejected ideas.
- Show ideas marked "promising" that have not been revisited.

This is where Argus differentiates from a one-off ChatGPT output.

### 5.8 Sharing and virality through public excerpts

Sharing is already part of the broader Argus product imagination, but the repo is clear that it must be a real sanitized artifact, not a shortcut that exposes conversation IDs.

Local source-of-truth guidance:

- `AGENTS.md` says not to restore "copy conversation link" or "share conversation id" as pseudo-sharing.
- `AGENTS.md` says future public conversation excerpts must be immutable, sanitized snapshots behind owner-only create/revoke and an unguessable public slug.
- `docs/archive/private-alpha-conversation-trust.md` has a design-only slice for public conversation excerpts.
- `docs/specs/evidence-aware-idea-loop.md` says sharing should wait for privacy, revocation, and artifact sanitization, but also recognizes sharing as a future distribution question.

Strategic interpretation:

Public sharing can become the virality layer for Argus, but only if what is shared is an evidence artifact, not a private conversation.

The right share unit is:

```text
EvidenceArtifact
-> sanitized public snapshot
-> unguessable public slug
-> owner can revoke
-> public view hides private/runtime metadata
```

The shared artifact should include:

- idea title;
- asset(s);
- strategy;
- date range;
- assumptions;
- result metrics;
- chart or static visual;
- educational/not-advice framing;
- optional founder/user note;
- Argus branding.

The shared artifact should not include:

- source conversation ID;
- private user identifiers;
- provider/model metadata;
- route receipts;
- retry payloads;
- raw transcripts;
- private broker/account data;
- nonterminal queued/running job cards;
- direct anonymous access to owner tables.

Why this matters:

- Users can show an idea result to friends without exposing their workspace.
- Shared results can drive curiosity and acquisition.
- The artifact itself markets Argus' core loop: "I had an idea, Argus tested it, here is the evidence."
- It reinforces the moat because the shareable object is not a generic chat transcript. It is a reproducible decision artifact.

This should not be Private Alpha work. It becomes strategically important for Public Alpha or Beta once privacy, revocation, and artifact sanitation are designed.

### 5.9 Broker/export handoff

Broker handoff should be future integration, not core moat.

Sources:

- Robinhood Agentic Trading overview: https://robinhood.com/us/en/support/articles/agentic-trading-overview/
- MCP introduction: https://modelcontextprotocol.io/docs/getting-started/intro
- Alpaca MCP Server: https://docs.alpaca.markets/us/docs/alpaca-mcp-server
- TradingView Broker API tutorial: https://www.tradingview.com/charting-library-docs/latest/tutorials/tutorials/implement-broker-api/
- TradingView brokerage integration: https://www.tradingview.com/brokerage-integration/
- Interactive Brokers API home: https://www.interactivebrokers.com/campus/ibkr-api-page/ibkr-api-home/
- Schwab Trader API: https://developer.schwab.com/products/trader-api--individual
- Tradier API: https://docs.tradier.com/
- tastytrade Open API: https://tastytrade.com/api/
- E*TRADE API: https://developer.etrade.com/home
- SnapTrade brokerage integrations: https://snaptrade.com/brokerage-integrations
- SnapTrade API docs: https://docs.snaptrade.com/

Argus should eventually hand off:

- not raw chat;
- not "buy this";
- but a structured pre-trade dossier.

The word "export" is better than "trade" for the near-term roadmap because it covers several safety levels:

#### Export Level 1: Evidence export

The user exports a sanitized evidence dossier:

- public link;
- PDF/image;
- CSV/JSON for the run;
- TradingView-friendly symbol/date/context;
- decision note.

No broker account connection required.

#### Export Level 2: Research/chart destination

The user sends context into a destination such as TradingView:

- chart symbol;
- timeframe;
- watchlist;
- annotations;
- possibly a Pine Script scaffold later if Argus supports strategy translation.

Important distinction: TradingView is not a broker account for Argus by default. It is a charting/trading ecosystem and broker-integration destination. Argus should treat TradingView as a visualization/research/export target unless a specific broker path through TradingView is explicitly implemented.

#### Export Level 3: Broker preparation

The user connects a broker or broker aggregator. Argus prepares an order-review packet:

- account eligibility;
- tradability;
- buying power check;
- estimated shares/contracts;
- constraints;
- warnings;
- required user confirmation.

No order is placed yet.

#### Export Level 4: Explicit broker execution

Only later, after legal/privacy/product controls:

- user explicitly confirms;
- broker API/MCP submits the order;
- Argus records what happened;
- user can revisit the decision and outcome.

Possible future flow:

```text
Argus idea survives review
-> user chooses "prepare trade"
-> Argus creates pre-trade review packet
-> broker MCP/API checks buying power, tradability, account constraints
-> user explicitly confirms
-> broker executes or rejects
-> Argus stores decision outcome
```

Potential broker/export targets:

- Robinhood: agentic trading through dedicated account and MCP. Strategic target because it validates the consumer-agent workflow, but it carries high trust/safety burden.
- Alpaca: strong developer/API/MCP target. Good for paper trading, developer testing, and eventually broker handoff. Alpaca's MCP exposes Trading and Market Data API capabilities.
- TradingView: export/chart destination and possible ecosystem bridge. Best first use is evidence/chart/watchlist export, not direct execution.
- Interactive Brokers: powerful API surface and broad market access, but more complex and less beginner-friendly.
- Schwab, Tradier, tastytrade, E*TRADE: possible broker API destinations, especially for equities/options users.
- SnapTrade: possible unified broker connectivity layer that can reduce integration breadth if Argus later needs many broker connections. It should be evaluated carefully for supported trading capabilities, pricing, data rights, and compliance posture.

This is not Alpha scope according to current Argus docs. Current product truth explicitly says real brokerage trading is out of Alpha scope.

Local sources:

- `docs/PRODUCT.md`
- `docs/ARCHITECTURE.md`

### 5.10 Web-first now, iOS shell in parallel for Beta readiness

The current Argus product docs correctly choose web/PWA for Alpha because it is the fastest path to PMF. The founder's updated instinct is also right: if Argus finds PMF on web, mobile can become a retention accelerator, and waiting until after PMF to think about iOS may create avoidable lag.

Strategic split:

```text
Private Alpha: web/PWA only
Public Alpha: web/PWA, mobile-first layout, voice-to-composer
Parallel track: thin iOS shell proof-of-concept
Beta: release iOS if retention loop is proven
```

The iOS shell should not fork product logic. It should share the same backend, same canonical idea/evidence/memory model, and ideally the same web chat surface until there is a proven reason to make native screens.

Possible shell approaches:

- Capacitor: strong fit for web-first teams that want a native runtime around an existing web app and access to native plugins.
- Expo/React Native WebView: viable for a thin shell plus native modules, but still requires careful app-like behavior and bridge discipline.
- Native SwiftUI shell: best long-term Apple feel, but slower and more expensive before retention is proven.

Important App Store constraint:

Apple's App Review Guideline 4.2 says apps should include features, content, and UI that elevate them beyond a repackaged website. A pure webview wrapper is risky. The iOS shell needs native utility that makes sense for Argus, such as:

- native authentication/session handling;
- push notifications for saved idea/revisit reminders later;
- native microphone capture for voice-to-composer;
- share sheet support for public excerpts;
- deep links to idea artifacts;
- local notification reminders;
- offline-safe recent artifact preview later;
- native settings/privacy/memory controls.

Therefore the parallel iOS work should be a proof-of-capability track, not an immediate App Store release target. It exists to de-risk mobile architecture while the web product searches for PMF.

## 6. Is Argus Becoming A Journal?

The founder asked whether UseMemos or similar note systems mean Argus becomes a journal.

Source:

- Memos docs: https://usememos.com/docs

Memos is a self-hosted note-taking and knowledge-base system around Markdown, visibility controls, and lightweight deployment.

The answer:

Argus is not a general journal.

Argus is a decision journal for investing ideas.

That is narrower and more valuable.

Generic journal:

- "I felt nervous about markets today."
- "I read an article about AI stocks."
- "Maybe BTC is interesting."

Argus decision journal:

- "I tested BTC buy-and-hold year-to-date with $100,000."
- "It underperformed versus benchmark under these assumptions."
- "I rejected it because max drawdown exceeded my threshold."
- "I revisited it later with ETH and compared results."
- "I decided not to hand off to broker because risk was too high."

UseMemos can inspire:

- lightweight capture;
- markdown-like notes;
- tags;
- visibility;
- API surfaces.

But Argus should not adopt a notes app as its memory model. The core memory model should be investment-specific.

## 7. What To Build Vs Leverage

The founder asked for leverage to move faster after two months of work and rapid market shift.

The answer is not "build everything."

The answer is to identify which layers are differentiating and which can be borrowed.

### 7.1 Build

Argus should build these because they are product-specific and become moat:

#### Canonical idea model

This is Argus' internal representation of investing ideas.

Do not outsource it.

#### Evidence artifact model

This is how Argus earns trust.

Do not let VectorBT, LEAN, Robinhood, or ChatGPT decide what the result object is.

#### Decision memory

This is the durable user relationship.

Use infrastructure, but own the product model.

#### Comparison loop

This depends on Argus-specific memory and result artifacts.

Build it.

#### Trust UI

Cards, assumptions, provenance, comparison, and decision capture are product surfaces.

Build them.

#### Language/runtime product behavior

The user experience of "Argus understands my messy investing idea" is core.

Use LLMs, but own the behavior and evaluation harness.

#### Voice-to-composer interaction model

The first voice feature should be built by Argus because it is product behavior, not just infrastructure.

The interaction should feel like voice fills the existing composer:

```text
Mic button inside composer
-> recording state with waveform/timer and stop affordance
-> final transcript appears as normal composer text
-> user can edit or clear
-> user presses Send
```

Argus should own:

- the composer state model;
- whether recording replaces or appends to existing text;
- transcript confidence/failure handling;
- retry UX;
- analytics events;
- privacy copy;
- the rule that voice does not auto-send financial instructions.

### 7.2 Leverage

Argus should leverage these to move faster:

#### OpenRouter for model access and routing

Sources:

- Auto Router: https://openrouter.ai/docs/guides/routing/routers/auto-router
- Provider selection: https://openrouter.ai/docs/guides/routing/provider-selection
- BYOK: https://openrouter.ai/docs/guides/overview/auth/byok

Use:

- task-specific routing;
- fallback profiles;
- cost/quality tradeoffs;
- model upgrades without code rewrites;
- optional future BYOK for advanced users.

Avoid:

- exposing a full model marketplace to normal users;
- turning Argus into a model picker;
- letting model choice become product complexity.

#### OpenRouter/OpenAI for production speech-to-text

Sources:

- OpenRouter audio: https://openrouter.ai/docs/guides/overview/multimodal/audio
- OpenRouter STT: https://openrouter.ai/docs/guides/overview/multimodal/stt
- OpenRouter TTS: https://openrouter.ai/docs/guides/overview/multimodal/tts
- OpenAI audio guide: https://platform.openai.com/docs/guides/audio
- OpenAI speech-to-text: https://platform.openai.com/docs/guides/speech-to-text
- OpenAI Realtime: https://platform.openai.com/docs/guides/realtime
- OpenAI voice agents: https://platform.openai.com/docs/guides/voice-agents
- OpenAI API pricing: https://developers.openai.com/api/docs/pricing
- OpenAI pricing page: https://openai.com/api/pricing/

Use:

- browser/mobile audio capture;
- server-side audio upload;
- STT transcription into composer text;
- cheap transcribe model first;
- higher-quality fallback for difficult audio;
- later realtime voice if the text loop proves retention.

Pricing snapshot as of 2026-06-14:

- `gpt-4o-mini-transcribe`: about `$0.003/minute`.
- `gpt-4o-transcribe`: about `$0.006/minute`.
- `whisper-1`: about `$0.006/minute`.
- `gpt-realtime-whisper`: about `$0.017/minute`.

Avoid:

- sending raw audio directly into the investing interpreter for the first version;
- auto-sending a transcript;
- treating voice as a second conversational runtime;
- adding realtime speech-to-speech before mic-to-composer is validated;
- assuming a ChatGPT/Codex subscription covers OpenAI API usage. OpenAI API billing is separate from ChatGPT subscriptions: https://help.openai.com/en/articles/8156019-does-chatgpt-plus-include-api-usage

#### ElevenLabs for premium speech and possible fallback STT

Sources:

- ElevenLabs API pricing: https://elevenlabs.io/pricing/api
- ElevenLabs TTS API: https://elevenlabs.io/text-to-speech-api
- ElevenLabs TTS docs: https://elevenlabs.io/docs/overview/capabilities/text-to-speech

Use:

- evaluate Scribe STT quality for Spanish/noisy audio if OpenAI/OpenRouter is not good enough;
- later premium branded TTS if Argus needs a distinctive spoken assistant voice;
- realtime STT/TTS only after voice usage is validated.

Pricing snapshot as of 2026-06-14:

- Scribe STT listed around `$0.22/hour`.
- Scribe realtime STT listed around `$0.39/hour`.
- TTS pricing varies by model/tier and can be materially more expensive than STT.

Avoid:

- using ElevenLabs only because it sounds premium if the first feature is transcription, not speech output;
- adding custom/branded voice before the product proves users want spoken responses;
- routing every chat response to TTS by default.

#### Wispr Flow as UX inspiration, not Argus infrastructure

Sources:

- Wispr Flow product: https://wisprflow.ai/
- Wispr Flow pricing: https://wisprflow.ai/pricing

Use:

- study the product interaction: fast dictation, polished transcript, cross-app language support, command/edit mode, privacy mode language;
- treat it as proof that users value voice dictation when it is faster than typing;
- learn from its "speak naturally, receive clean text" framing.

Avoid:

- treating Wispr Flow as an embeddable backend for Argus;
- making Argus dependent on a consumer dictation app;
- copying broad dictation features before proving investing-specific voice capture.

#### Open-source STT for later cost/control leverage

Sources:

- `whisper.cpp`: https://github.com/ggml-org/whisper.cpp
- `faster-whisper`: https://github.com/SYSTRAN/faster-whisper
- Vosk: https://alphacephei.com/vosk/
- sherpa-onnx: https://k2-fsa.github.io/sherpa/onnx/index.html

Use:

- evaluate self-hosted or on-device transcription if cloud STT cost/privacy becomes a blocker;
- test offline/native mobile paths later;
- learn whether local STT quality is acceptable for English/Spanish investing prompts.

Avoid:

- self-hosting STT before usage volume justifies ops complexity;
- letting STT infrastructure distract from the core language/runtime and evidence loop.

#### Perplexity for web-grounded facts/search

Sources:

- Prompt guide: https://docs.perplexity.ai/docs/agent-api/prompt-guide
- Agent API: https://docs.perplexity.ai/docs/agent-api/quickstart
- Sonar API: https://docs.perplexity.ai/docs/sonar/quickstart
- Search API: https://docs.perplexity.ai/docs/search/quickstart

Use:

- current market context;
- source-backed research;
- citations;
- later research-to-testable-hypothesis loops;
- fact packets before backtesting when the user asks why something happened.

Strategic placement:

- this is a research-first entry point, not the only Argus flow;
- if the user already knows what they want to test, Argus should skip research
  and preserve the fast idea-first golden path;
- if the user revisits a saved idea and asks about "now", "latest", or "what
  changed", Perplexity/Search/Sonar can refresh the stale factual layer before
  Argus suggests a new test or decision update.

Avoid:

- using web search for every turn;
- making facts a dependency for simple buy-and-hold flows;
- letting research slow down the golden path.

#### Perplexity or other embeddings for semantic retrieval

Sources:

- Perplexity embeddings: https://docs.perplexity.ai/docs/embeddings/quickstart
- Perplexity embeddings best practices: https://docs.perplexity.ai/docs/embeddings/best-practices
- Supabase vector columns: https://supabase.com/docs/guides/ai/vector-columns

Use:

- retrieving similar prior ideas;
- searching decision notes;
- finding semantically similar conversation snippets;
- clustering user themes.

Avoid:

- treating embeddings as canonical memory;
- doing RAG before structured memory exists.

#### Supabase/Postgres for structured memory

Sources:

- Supabase vector columns: https://supabase.com/docs/guides/ai/vector-columns
- Local Argus docs: `docs/DATA_MODEL.md`, `docs/ARCHITECTURE.md`

Use:

- durable ideas;
- runs;
- decisions;
- preferences;
- feedback;
- embeddings with pgvector if/when needed.

Avoid:

- building a separate memory database before Postgres proves insufficient.

#### Mem0 as optional memory lifecycle accelerator

Sources:

- Mem0 docs: https://docs.mem0.ai/open-source/overview
- Mem0 GitHub: https://github.com/mem0ai/mem0
- Mem0 LangGraph integration: https://docs.mem0.ai/integrations/langgraph
- Mem0 LangChain integration: https://docs.mem0.ai/integrations/langchain
- Mem0 tagging and organizing memories: https://docs.mem0.ai/cookbooks/essentials/tagging-and-organizing-memories
- Mem0 search memory: https://docs.mem0.ai/core-concepts/memory-operations/search
- Mem0 reranker-enhanced search: https://docs.mem0.ai/open-source/features/reranker-search
- Mem0 async memory: https://docs.mem0.ai/open-source/features/async-memory
- Mem0 Python SDK quickstart: https://docs.mem0.ai/open-source/python-quickstart
- Mem0 Node SDK quickstart: https://docs.mem0.ai/open-source/node-quickstart

Use if:

- Argus needs faster experimentation with memory extraction;
- structured memory alone is too slow to productize;
- you want an external memory lifecycle with extraction/update/retrieval.
- the LangGraph runtime needs semantically ranked user memory context;
- memory needs tagging by type, such as preference, decision, risk threshold,
  rejected idea, promising idea, revisit reminder, or user correction;
- FastAPI/background-worker paths need non-blocking memory operations.

Best fit:

- use Mem0 as an agent memory/retrieval layer;
- keep canonical `Idea`, `IdeaVersion`, `EvidenceArtifact`, and `DecisionNote`
  records in Supabase;
- test managed Mem0 for speed, then evaluate OSS/self-hosted Mem0 if privacy,
  cost, or control requires Argus-hosted memory;
- use Supabase/Postgres/pgvector as the default owned data/control plane where
  feasible.

Avoid if:

- it makes user memory opaque;
- it stores memories outside the Argus product model;
- it becomes another black box before the memory UX is understood.
- it encourages automatic memory extraction before explicit/assisted decision
  memory proves useful.

#### LangGraph/LangMem for runtime-aligned long-term memory

Sources:

- LangGraph memory concepts: https://docs.langchain.com/oss/python/concepts/memory
- LangMem: https://www.langchain.com/blog/langmem-sdk-launch
- LangMem concepts: https://langchain-ai.github.io/langmem/concepts/conceptual_guide/

Use if:

- Argus wants memory close to its existing LangGraph runtime;
- memory should influence agent behavior through semantic/episodic/procedural patterns;
- the team wants memory integrated into the agent graph rather than a separate service.

Avoid if:

- it encourages premature procedural memory changes;
- it hides product memory from users.

#### Graphiti/Zep for temporal graph memory later

Sources:

- Graphiti GitHub: https://github.com/getzep/graphiti
- Graphiti/Zep platform page: https://www.getzep.com/platform/graphiti/

Use if:

- Argus needs temporal reasoning over changing facts;
- user memory becomes graph-like;
- comparison loops need relationship traversal;
- provenance and fact invalidation become difficult with relational + vector search alone.

Avoid for Alpha:

- too much architecture before user behavior validates memory depth.

#### VectorBT for validation only

Sources:

- VectorBT terms: https://vectorbt.dev/terms/
- VectorBT license: https://vectorbt.dev/terms/license/

Use:

- internal experimentation;
- free alpha validation;
- benchmarking mature vectorized backtesting patterns;
- learning what metrics users actually value.

Avoid:

- commercial production dependency without license clarity;
- deep fork;
- shaping Argus product objects around VectorBT internals.

#### LEAN self-hosted as possible later engine

Sources:

- LEAN: https://www.lean.io/
- LEAN license: https://github.com/QuantConnect/Lean/blob/master/LICENSE

Use if:

- Argus needs a more robust engine with commercially cleaner open-source terms;
- validated user demand requires more engine depth;
- the team can absorb operational complexity.

Avoid for immediate Alpha if:

- it slows readiness;
- it forces advanced quant concepts into a beginner product;
- data licensing remains unresolved.

#### QuantConnect Cloud MCP for inspiration, not production dependency

Sources:

- QuantConnect MCP: https://www.quantconnect.com/docs/v2/ai-assistance/mcp-server/key-concepts
- QuantConnect terms: https://www.quantconnect.com/terms/

Use:

- study agentic quant workflow design;
- understand tool surfaces;
- benchmark what "AI + backtesting + live deployment" can feel like.

Avoid:

- commercial product backend without explicit permission/deal.

#### PostHog for analytics and feedback loops

Sources:

- PostHog install docs: https://posthog.com/docs/getting-started/install

Use:

- activation funnel;
- starter prompt usage;
- first successful backtest;
- failed interpretation paths;
- result card interactions;
- decision capture usage;
- compare action usage;
- language preference flows;
- qualitative surveys later.

Avoid:

- collecting sensitive financial details unnecessarily;
- logging raw prompts/results without privacy design.

## 8. Updated Stack Proposal

This is the updated stack that reflects the new market reality without throwing away the current Argus architecture.

```text
Client:
  Next.js Web/PWA now
  Public Alpha remains web-first
  iOS shell proof-of-capability in parallel
  iOS release target only when Argus moves toward Beta

Input:
  Typed composer
  Provider-backed @ mentions
  Voice-to-composer STT
  Transcript review before Send

Product UI:
  Chat workspace
  Result/evidence cards
  Optional evidence views: benchmark, drawdown, indicator, comparison
  Shareable public excerpts
  Idea ledger
  Decision notes
  Comparison views
  Memory inspector

AI Runtime:
  LangGraph as active chat brain
  OpenRouter for model access/routing/fallback
  Task-specific model profiles
  Optional Perplexity for source-backed research/facts

Research / Freshness:
  Idea-first path stays fast when user already knows what to test
  Research-first path uses Perplexity/Search/Sonar for latest facts/digests
  Memory-first path refreshes stale saved ideas before suggesting action
  Current facts inform hypotheses; they do not silently execute trades/tests

Voice:
  Browser MediaRecorder or native mobile capture
  OpenAI/OpenRouter STT primary path
  ElevenLabs Scribe fallback evaluation if quality warrants
  Realtime speech-to-speech deferred until text loop retention is proven

Interpretation:
  LLM semantic interpreter
  Structured canonical idea spec
  Deterministic guardrails after interpretation
  Language-agnostic input, language-aware output

Persistence:
  Supabase Auth/Postgres
  Conversations/messages
  Ideas
  Idea versions
  Evidence artifacts
  Backtest jobs/runs
  Decisions
  Preferences
  Feedback
  Optional pgvector for semantic retrieval

Memory:
  Phase 1: structured Supabase product memory
  Phase 2: Save Idea / decision state over time
  Phase 3: Mem0/Supabase pgvector retrieval over ideas/notes/conversations
  Phase 4: optional LangMem/Graphiti if graph/procedural memory is needed

Backtesting:
  Current engine for immediate readiness
  VectorBT OSS only for internal/free validation if useful
  LEAN self-hosted evaluation if deeper engine required
  Argus-native validated subset before monetization

Indicator / Strategy Capabilities:
  Full current-state audit required
  Canonical strategy conditions, not phrase gates
  Capability registry validates executable indicators
  Start narrow: buy-and-hold, RSI threshold, SMA/EMA crossover
  Expand only from observed user demand and engine/data readiness

Sharing / Distribution:
  Owner-created public evidence excerpts
  Immutable sanitized snapshots
  Unguessable public slugs
  Owner revoke/delete controls
  No source conversation ids or private runtime metadata

Mobile Shell:
  Capacitor or Expo/React Native shell evaluation
  Shared backend, shared canonical idea/evidence model
  Native mic/share/deep-link surfaces first
  No forked product logic

Analytics:
  PostHog for funnel, event, and feedback instrumentation
  Separate voice transcript success/failure from interpretation success/failure

Regional Readiness:
  Language-agnostic input unlocks region expansion without runtime rewrites
  Supabase regions and DPA/SOC2 posture support data-residency planning
  PostHog Cloud EU and privacy controls support analytics compliance planning
  Locale, consent, memory, and analytics controls must be first-class data

Monetization Readiness:
  Do not activate monetization before PMF signals are clear
  Add an internal entitlement spine before choosing the paywall
  Lemon Squeezy is the likely web-first checkout/subscription/MoR path
  RevenueCat is the likely iOS/mobile subscription entitlement path
  Supabase mirrors canonical entitlement state for product logic

Broker / Export Handoff:
  Level 1: evidence export and public share links
  Level 2: TradingView/charting/research export context
  Level 3: broker pre-trade review packet
  Level 4: explicit execution handoff only after trust/legal controls
  Robinhood, Alpaca, and broker APIs/MCPs are leverage, not the moat
```

## 9. What This Means For The Product Vision

Before the market shift, the product could be described as:

> Speak an investing idea and see a backtest.

After the market shift, that is too small.

The sharper vision is:

> Argus is the place where investing ideas become tested, remembered, compared, and trusted before they become trades.

This preserves the original product truth:

- chat-first;
- AI-first;
- voice-ready without becoming voice-first;
- idea validation;
- beginner-friendly;
- safe by default;
- backtesting as critical infrastructure.

But it adds the missing moat:

- durable idea memory;
- evidence history;
- decision journaling;
- comparison loops;
- pre-trade review.

### 9.1 Region-ready by design

The language-agnostic runtime creates a strategic regional advantage. If Argus
can understand messy user intent across languages while rendering UI and
artifacts in supported locales, then expansion into Spanish-speaking, English-
speaking, Portuguese-speaking, or other regions becomes product/legal/
distribution work rather than a runtime rewrite.

This does not mean Argus is automatically globally launch-ready. The right
framing is:

> Argus should be region-ready by design, not globally compliant by assumption.

Language expansion is not just translation. It touches:

- privacy policy and terms localization;
- consent collection;
- analytics opt-in/opt-out posture;
- memory controls;
- data-region choices;
- local financial-advice language;
- market-data/news/chart licensing;
- broker availability and handoff rules;
- consumer-protection expectations.

Supabase and PostHog are strong enough to support this path if configured
carefully:

- Supabase provides managed Postgres/Auth, SOC 2 Type 2 posture, a DPA path,
  and project region choices such as US, Central EU/Frankfurt, and Singapore.
- PostHog provides product analytics, SOC 2 Type II posture, DPA support, GDPR
  guidance, and PostHog Cloud EU hosted in Frankfurt for stronger EU analytics
  posture.

But vendor compliance does not make Argus compliant by itself. Argus still owns:

- what data it collects;
- whether raw prompts/results are logged;
- whether financial memories are stored;
- how users inspect, edit, delete, or disable memory;
- retention windows;
- deletion/export flows;
- consent versioning;
- provider data display rights.

Recommended product/data fields to make this scalable:

- `locale`;
- `region`;
- `data_region`;
- `consent_version`;
- `terms_version`;
- `privacy_policy_version`;
- `analytics_opt_in`;
- `memory_enabled`;
- `memory_consent_version`;
- `research_sources_region`;
- `legal_disclaimer_variant`.

Regional launch sequence:

1. Private alpha: English/Spanish, explicit alpha consent, minimal analytics,
   memory off or tightly controlled.
2. Public alpha: one primary legal/data region, clear privacy/terms, PostHog
   events designed for data minimization.
3. Regional expansion: localize legal copy, choose data residency posture,
   review financial-promotion/advice language, and confirm provider rights.
4. Beta/mobile: add stronger privacy settings, memory inspector, and regional
   onboarding defaults.

### 9.2 Monetization-ready, not monetization-first

The market shift makes monetization tempting, but Argus should not charge before
it has clear PMF signals. The product does not yet know which behavior users
will repeat, trust, and value enough to pay for.

The correct strategic stance:

> Design the entitlement spine now. Delay the paywall until the retained loop is
> obvious.

Potential future monetizable surfaces:

- more saved ideas and decision memory;
- more backtests or higher compute quotas;
- freshness monitors on saved ideas;
- advanced evidence views such as drawdown, benchmark, indicators, and
  comparisons;
- source-backed research digests;
- export/share artifacts;
- broker handoff or pre-trade review packets;
- voice/mobile convenience;
- higher-quality or faster model tiers.

What should not be monetized first:

- the first successful backtest;
- basic language understanding;
- the first evidence artifact;
- clarifying messy prompts;
- trust/safety explanations.

Those are the product's aha moment. They should create trust before they create
friction.

RevenueCat and Lemon Squeezy are leverage tools, not strategy:

- RevenueCat is the likely iOS/mobile subscription and entitlement layer once
  Argus ships a mobile app.
- Lemon Squeezy is the likely web-first checkout, subscription, hosted checkout,
  usage billing, license key, and merchant-of-record/tax path.
- Supabase should mirror canonical entitlement state so Argus product logic is
  not trapped inside a billing vendor.

Internal entitlement states can exist before monetization:

```text
free_user
trusted_alpha
pro_candidate
pro
```

Use PostHog/Supabase to observe willingness signals before charging:

- repeated saved ideas;
- repeated backtests;
- revisit behavior;
- monitor requests;
- export/share usage;
- advanced evidence view usage;
- users hitting real quota or speed limits;
- users asking for mobile/voice convenience.

Build readiness now:

- canonical entitlement table in Supabase;
- feature checks read from Argus entitlement state;
- billing providers sync into Argus, not the other way around;
- payment UI hidden or disabled until PMF and legal readiness;
- no dark-pattern paywalls around trust-critical explanations.

## 10. What This Means For The Codebase

### 10.1 Do not make the current backtester the product boundary

The product boundary should be:

```text
CanonicalIdeaSpec -> EvidenceArtifact
```

The engine is replaceable.

Argus should not store engine-native output as the main product truth.

### 10.2 Keep a canonical engine adapter boundary

The current launch adapter is sufficient while Argus has one validated engine.
The product boundary remains:

```text
BacktestEngine.run(spec: CanonicalBacktestSpec) -> EvidenceArtifactPayload
```

This is a conceptual contract, not a requirement to add a formal plugin
interface before P2. Current engine-native output must stay behind the existing
adapter and canonical run/evidence objects.

Potential later adapters, only after a concrete second-engine need:

- current Argus engine;
- vectorbt validation adapter;
- LEAN adapter;
- future Argus-native engine;
- remote MCP/tool adapter.

### 10.3 Promote idea/version/result/decision to first-class domain objects

Current docs already include conversations, strategies, collections, and backtest runs. The new memo suggests adding or refining:

- ideas;
- idea versions;
- evidence artifacts;
- decisions;
- comparison links;
- memory preferences.

Strategies may become one saved/executable subtype of idea rather than the only durable non-chat object.

### 10.4 Keep language-agnostic runtime work

Language runtime remains existential because the strongest product loop begins with messy natural language. However, the point is not to build parsers. The point is:

- LLM-first semantic interpretation;
- structured canonical spec;
- deterministic validation after interpretation;
- language-aware artifacts;
- evaluation harness around capability shapes.

### 10.5 Add memory carefully, not as a vague RAG blob

Start with structured product memory.

Then add embeddings.

Then add graph/agentic memory only if user behavior proves the need.

### 10.6 Add analytics before scaling

PostHog should answer:

- Which starter prompts lead to completed backtests?
- Where does interpretation fail?
- How often do users rerun/refine?
- Do users use decision capture?
- Do users compare ideas?
- Which language flows succeed/fail?
- Which metrics do users expand or ask about?
- How many users return to prior ideas?

This matters because the new moat depends on repeated behavior, not one-time curiosity.

### 10.7 Treat sharing as a sanitized artifact pipeline

Sharing should not be a copied conversation link. The codebase should treat
sharing as:

```text
EvidenceArtifact -> PublicExcerptSnapshot -> PublicExcerptView
```

The snapshot should be immutable, owner-created, owner-revocable, and stripped
of private runtime details.

That means the public artifact layer should not query the original private
conversation live. It should render a purpose-built public payload:

- idea title;
- asset and asset class;
- strategy and assumptions;
- date range;
- result metrics;
- visual evidence;
- educational/not-advice framing;
- optional founder/user note.

This protects trust while creating a distribution loop. If a result is worth
showing to someone else, the shareable artifact should make Argus visible as
the place where the idea was tested.

### 10.8 Keep iOS as a shell around the same product spine

The iOS track should not create a second Argus product.

The first useful iOS shell should share:

- the same backend;
- the same language/runtime spine;
- the same canonical idea/evidence contract;
- the same auth and memory model;
- the same web-tested conversation loop wherever possible.

Native iOS should add leverage only where native surfaces matter:

- microphone capture;
- share sheet;
- deep links into idea artifacts;
- push or local reminders later;
- native settings/privacy controls later;
- lightweight saved-artifact viewing later.

This makes parallel development possible without letting mobile split the
product. Web remains the PMF surface. iOS becomes the retention surface once
the loop is strong enough for Beta.

## 11. Updated Roadmap Slices

### Slice A: Keep current readiness path stable

Purpose:

- Do not abandon the readiness work.
- Fix language/runtime failures because they block the core loop.
- Keep the current Alpha path working.

Do not expand scope here into full memory or broker handoff.

### Slice B: Define the canonical idea/evidence contract

Output:

- product spec for `Idea`, `IdeaVersion`, internal `Run`, user-facing
  `Backtest`, `EvidenceArtifact`, `DecisionNote`, and lifecycle labels;
- API contract updates;
- data model proposal;
- minimal migration plan.

This is the first real step toward the moat.

### Slice C: Backtest engine boundary

Output:

- `BacktestEngine` interface;
- current engine adapter;
- canonical evidence output shape;
- engine metadata/provenance;
- no VectorBT leak into product objects.

### Slice D: Indicator and strategy capability audit

Output:

- inventory of all current indicator/strategy-condition code paths;
- map of what is interpreted, validated, executable, rendered, and documented;
- list of overpromised or stale capability surfaces;
- English/Spanish parity check for indicator-shaped prompts;
- recommendation for the first trusted indicator set;
- plan to move supported indicators into canonical strategy conditions and the capability registry;
- no broad indicator expansion until the audit proves the current state.

This slice exists because indicators have been mostly forgotten while the basic
loop was being stabilized. That was understandable, but the next architecture
needs to know exactly what is real before steering toward the broader evidence
vision.

### Slice E: Decision capture MVP

Output:

- result card action to mark decision state;
- optional short note;
- visible history in conversation/recents;
- no heavy journal UI.

Decision states:

- `watching`
- `promising`
- `rejected`
- `revisit_later`

### Slice F: Omnisearch-ledger MVP

Output:

- lightweight view of tested ideas;
- grouped by recent activity;
- shows asset, strategy, date, outcome, decision state;
- opens the selected artifact directly, with conversation shown as provenance.

This should start inside Omnisearch/search rather than a new top-level surface.
Recents should remain primarily chat navigation.

### Slice G: Comparison loop MVP

Output:

- compare current backtest against prior same-asset/same-strategy idea;
- compare current backtest against previous version;
- compare key metrics and assumptions;
- generate a short grounded readout.

### Slice H: Memory inspector MVP

Output:

- settings page surface:
  - language preference;
  - remembered investing preferences;
  - delete/edit memory;
  - disable memory for future chats;
  - temporary/no-memory chat mode later.

This mirrors the control principles visible in ChatGPT/Gemini-like memory products.

### Slice I: Analytics instrumentation

Output:

- PostHog events for:
  - starter prompt clicked;
  - mic recording started/stopped;
  - transcription succeeded/failed;
  - transcript edited before send;
  - interpretation succeeded/failed;
  - confirmation shown;
  - backtest run started/completed/failed;
  - result explained;
  - decision saved;
  - comparison viewed;
  - language changed;
  - user returned to prior idea.

### Slice J: Voice-to-composer STT MVP

Output:

- mic button inside the existing composer;
- audio recording state with clear stop/cancel affordance;
- server-side STT call through OpenAI/OpenRouter first;
- transcript inserted into composer, not auto-sent;
- user can edit, clear, append, replace, then press Send;
- transcription errors do not mutate chat state;
- analytics distinguish STT failure from Argus interpretation failure;
- privacy copy explains that audio is transcribed to create composer text.

Recommended provider path:

- start with OpenAI/OpenRouter `gpt-4o-mini-transcribe`-class pricing if quality is good enough;
- evaluate `gpt-4o-transcribe` or ElevenLabs Scribe only when noisy Spanish/English quality needs justify it;
- keep realtime voice agent work deferred until users actually use voice input.

### Slice K: Public excerpt / sharing MVP design

Output:

- product spec for owner-created public excerpts;
- API contract for create/revoke/delete/read-public snapshot;
- sanitized payload contract;
- share button placement on completed result artifacts;
- public page design that does not expose conversation ids or runtime metadata;
- analytics for excerpt created, copied, opened, revoked, and converted to signup.

Do not ship generic "copy conversation link". Ship a shareable evidence object.

### Slice L: iOS shell proof-of-capability

Output:

- technical spike comparing Capacitor vs Expo/React Native WebView vs SwiftUI shell;
- recommendation for the smallest shell that can reuse the web PMF loop;
- prototype only if it does not fork backend/product logic;
- native mic and share-sheet feasibility notes;
- App Store guideline 4.2 risk note;
- Beta-readiness checklist, not an Alpha launch blocker.

Private Alpha and Public Alpha remain web-first. This slice exists so mobile
does not become a cold start when retention is ready.

### Slice M: Engine leverage experiment

Output:

- read-only/internal experiment comparing current engine vs VectorBT/LEAN for validated workflows;
- no commercial dependency decision yet;
- learn whether external engines materially improve user-facing evidence.

### Slice N: Broker/export handoff design only

Output:

- export-level ladder from evidence export to broker execution;
- target matrix for Robinhood, Alpaca, TradingView, Interactive Brokers, Schwab, Tradier, tastytrade, E*TRADE, and SnapTrade;
- future spec for pre-trade dossier and broker handoff;
- distinction between chart/research export and broker execution;
- no real trading in Alpha;
- no execution integration until the evidence/memory loop proves retention.

## 12. Founder Decisions Still Needed

Status note: the relevant object, memory, engine, PMF, and freshness questions
below were resolved by the 2026-07-16 Founder Resolution Addendum in section 16.
Keep this section as the original decision record, not as an active question
queue.

### 12.1 Is Argus allowed to add new product objects before Alpha launch?

Options:

- no, keep readiness only;
- yes, but only decision notes and evidence artifacts;
- yes, include idea ledger MVP.

### 12.2 Should Strategies remain hidden while idea memory evolves?

The current private-alpha docs say Strategies and Collections are hidden by default. The new idea ledger might be a better first surface than the old Strategies surface.

Decision:

- Keep Strategies hidden for now?
- Replace Strategies roadmap with Idea Ledger?
- Let Strategies become a later filtered view of executable ideas?

### 12.3 How aggressive should memory be?

Options:

- explicit-only memory: user marks decisions/preferences;
- assisted memory: Argus suggests memories but asks for confirmation;
- automatic memory: Argus extracts preferences/events automatically with inspect/delete controls.

Recommendation:

Start explicit or assisted, not fully automatic.

### 12.4 Do we use VectorBT during free validation?

Options:

- no, keep current engine and improve only after evidence;
- yes, internal-only benchmark;
- yes, free-alpha runtime adapter with clear no-monetization dependency;
- commercial license inquiry now.

Recommendation:

Use as internal validation only unless the team is comfortable with license risk.

### 12.5 Is iOS part of the retention test?

The founder wants Argus in everyone's pocket. Current product docs say native mobile is deferred post-Alpha, with web/PWA first.

Recommendation:

Do not release native iOS before the memory/comparison loop proves retention.
But start a narrow iOS shell proof-of-capability in parallel if it stays
non-disruptive: same backend, same canonical contracts, no forked product logic,
native mic/share/deep-link surfaces only. Treat it as Beta readiness, not Alpha
scope.

### 12.6 How should Argus introduce voice?

Options:

- no voice until native mobile;
- browser-native Web Speech API only;
- production STT through OpenAI/OpenRouter into the composer;
- full realtime speech-to-speech agent;
- ElevenLabs-first voice layer.

Recommendation:

Start with production STT into the existing composer. Do not use browser-native Web Speech API as the production truth because browser support is uneven. Do not start with full realtime speech-to-speech because it creates a second interaction loop before the text runtime and memory loop are stable. Do not start ElevenLabs-first unless quality testing proves it beats OpenAI/OpenRouter for the specific English/Spanish audio conditions Argus expects.

### 12.7 When does public sharing enter the roadmap?

Options:

- defer until after Beta;
- design now, ship after memory/evidence contracts are stable;
- ship a minimal public result excerpt during Public Alpha;
- make sharing part of the first retention/distribution test.

Recommendation:

Design sharing now because it affects the evidence artifact contract. Ship only
owner-created sanitized public excerpts, not conversation links. This can become
the first virality loop once the result artifact is trustworthy enough to show
outside the app.

### 12.8 Which broker/export target comes first?

Options:

- Robinhood first because agentic trading validates the MCP direction;
- Alpaca first because paper trading and official MCP tooling are developer-friendly;
- TradingView first as a chart/research export target with lower execution risk;
- SnapTrade first to explore broad account aggregation/trading coverage;
- no broker target until Public Alpha retention is proven.

Recommendation:

Start with export design, not broker execution. The first target should probably
be TradingView-style research/export context or Alpaca paper-trade preparation,
because both teach the product without requiring real-money execution. Robinhood
is important strategically, but execution should wait until Argus has the
pre-trade dossier, consent, legal, and suitability framing.

## 13. Key Risks

### Risk 1: Argus becomes a worse ChatGPT with charts

Mitigation:

- durable idea memory;
- evidence dossiers;
- comparison loops;
- trust UI;
- decision capture.

### Risk 2: Argus overbuilds a quant engine before user demand

Mitigation:

- engine abstraction;
- validate with current/simple engine;
- use external engines only for learning;
- build Argus-native validated subset later.

### Risk 3: Argus builds opaque AI memory that users do not trust

Mitigation:

- memory inspector;
- explicit controls;
- delete/edit;
- no-memory/temporary mode later;
- source-linked memories.

### Risk 4: Language runtime work consumes months

Mitigation:

- LLM-first interpretation;
- capability-shape tests;
- avoid parsers;
- evaluate higher reasoning models for hard turns;
- track failure classes in analytics.

### Risk 5: Broker platforms own the user relationship

Mitigation:

- Argus lives before broker execution;
- broker handoff happens only after Argus builds a pre-trade dossier;
- Argus owns idea history and decision memory.

### Risk 6: Privacy and regulatory expectations rise with memory

Mitigation:

- avoid collecting broker credentials in Alpha;
- avoid real trading in Alpha;
- minimize raw prompt logging;
- user controls for memory;
- clear educational/not-advice framing;
- terms/privacy before broad release.

### Risk 7: Voice turns a safe text product into an accidental execution interface

Mitigation:

- voice fills the composer only;
- no auto-send after recording;
- user can edit transcript before Send;
- transcript confidence/failure is tracked separately;
- ambiguous or unsupported spoken prompts still go through the normal language/runtime guardrails;
- realtime speech-to-speech remains deferred until the product has stronger evidence, memory, and safety controls.

### Risk 8: Public sharing leaks private context

Mitigation:

- share only immutable sanitized excerpt snapshots;
- owner must create and revoke excerpts;
- no direct anonymous access to conversations/messages/backtest internals;
- no source conversation ids, route receipts, provider/model metadata, retry payloads, raw transcripts, or broker/account data;
- public page is a purpose-built evidence view, not a replay of chat.

### Risk 9: iOS becomes a distracting second product before PMF

Mitigation:

- web remains Private Alpha and Public Alpha PMF surface;
- iOS shell is proof-of-capability only;
- no forked runtime, data model, or separate chat logic;
- native work must amplify proven loops: mic, share sheet, deep links, reminders, settings;
- App Store release waits for Beta-level retention evidence.

### Risk 10: Broker export creates premature execution/compliance pressure

Mitigation:

- use a staged export ladder;
- ship evidence export and chart/research export before broker execution;
- separate "prepare/review" from "place order";
- do not connect real-money execution during Alpha;
- make explicit confirmation, consent, suitability framing, and legal review prerequisites for any future execution path.

### Risk 11: Indicators become a feature treadmill

Mitigation:

- audit current indicator state before adding breadth;
- treat indicators as canonical executable conditions, not marketing bullets;
- start with a tiny trusted set;
- make each supported indicator editable and evidence-backed;
- do not add a trading-terminal indicator catalog until user behavior proves demand;
- keep the moat focused on evidence, memory, comparison, sharing, and pre-trade review.

## 14. The Practical Answer To "Are We Cooked?"

No.

But the product must evolve.

Argus is cooked if it remains:

- chat prompt;
- simple backtest;
- chart;
- explanation.

Argus is not cooked if it becomes:

- the user's investing idea memory;
- the user's evidence lab;
- the user's comparison layer;
- the user's pre-trade decision checkpoint.

The market shift is not only bad news. It proves that agentic investing workflows are real and coming fast. Robinhood, Alpaca, and ChatGPT validate that users will expect agents to interact with financial tools.

Argus can use that wave instead of fighting it.

The winning wedge is not:

> We can trade for you.

The winning wedge is:

> Before an agent trades for you, Argus helps you understand, test, compare, and remember why the idea deserves action.

## 15. Recommended Next Product Thesis

Argus is the pre-trade intelligence layer for everyday investors.

It turns messy investing ideas into:

- structured specs;
- reproducible evidence;
- understandable results;
- durable memory;
- comparison loops;
- decision notes;
- eventual broker-ready review packets.

This keeps the product aligned with the original Alpha truth:

- chat-first;
- AI-first;
- safe by default;
- simple;
- trustworthy;
- beginner-friendly.

But it updates the moat for the MCP era.

## 16. Recommended Immediate Action

Do not pivot into broker execution.

Do not expose a model catalog.

Do not build a massive quant engine now.

Do not make a generic journal.

Do this instead:

1. Finish the current readiness/language runtime path enough that the golden path works for English and Spanish users.
2. Specify the canonical idea/evidence/decision memory model.
3. Add a backtest engine boundary so the engine can be replaced.
4. Audit indicators and strategy capabilities so the engine roadmap is based on current truth, not assumptions.
5. Keep the current hero equity chart simple, then specify optional evidence views for benchmark comparison, drawdown, indicator evidence, and idea comparison.
6. Add decision capture to the result artifact.
7. Add lightweight ledger recall through Omnisearch/search, while Recents stays
   primarily chat navigation.
8. Add first comparison loop.
9. Design public excerpts as sanitized evidence artifacts so sharing becomes a distribution loop later.
10. Instrument the loop with PostHog.
11. Add voice-to-composer STT only after the text runtime is stable enough that messy transcripts can flow through the same interpreter.
12. Run an iOS shell proof-of-capability in parallel only if it reuses the web/runtime spine and targets Beta retention.
13. Use VectorBT/LEAN only as validation/reference leverage until commercial runtime requirements are clear.
14. Design broker/export handoff as a staged ladder, not as real-money execution.

## 17. Source Index

### Agentic broker/tooling

- Robinhood Agentic Trading overview: https://robinhood.com/us/en/support/articles/agentic-trading-overview/
- Robinhood Agentic Trading landing page: https://robinhood.com/us/en/agentic-trading
- Model Context Protocol introduction: https://modelcontextprotocol.io/docs/getting-started/intro
- Alpaca MCP Server docs: https://docs.alpaca.markets/us/docs/alpaca-mcp-server
- Alpaca MCP Server landing page: https://alpaca.markets/mcp-server
- Alpaca MCP Server GitHub: https://github.com/alpacahq/alpaca-mcp-server
- TradingView Broker API tutorial: https://www.tradingview.com/charting-library-docs/latest/tutorials/tutorials/implement-broker-api/
- TradingView Advanced Charts API reference: https://www.tradingview.com/charting-library-docs/latest/api/
- TradingView brokerage integration: https://www.tradingview.com/brokerage-integration/
- Interactive Brokers API home: https://www.interactivebrokers.com/campus/ibkr-api-page/ibkr-api-home/
- Schwab Trader API: https://developer.schwab.com/products/trader-api--individual
- Tradier API docs: https://docs.tradier.com/
- tastytrade Open API: https://tastytrade.com/api/
- E*TRADE API docs: https://developer.etrade.com/home
- SnapTrade API docs: https://docs.snaptrade.com/
- SnapTrade brokerage integrations: https://snaptrade.com/brokerage-integrations

### Charting and visual evidence

- TradingView Lightweight Charts: https://www.tradingview.com/lightweight-charts/
- Lightweight Charts docs: https://tradingview.github.io/lightweight-charts/
- Lightweight Charts series types: https://tradingview.github.io/lightweight-charts/docs/series-types
- Lightweight Charts series markers: https://tradingview.github.io/lightweight-charts/tutorials/how_to/series-markers
- Lightweight Charts plugins: https://tradingview.github.io/lightweight-charts/docs/plugins/intro
- TradingView Advanced Charts: https://www.tradingview.com/advanced-charts/
- TradingView Advanced Charts docs: https://www.tradingview.com/charting-library-docs/
- Argus result chart contract: `docs/API_CONTRACT.md`
- Argus conversational runtime chart contract: `docs/CONVERSATIONAL_RUNTIME.md`
- Argus result-card design guidance: `.agent/designs/argus/DESIGN.md`

### Mobile, iOS shell, and app wrapper strategy

- Argus product doc: `docs/PRODUCT.md`
- Argus architecture doc: `docs/ARCHITECTURE.md`
- Argus design system: `.agent/designs/argus/DESIGN.md`
- Capacitor: https://capacitorjs.com/
- Expo docs: https://docs.expo.dev/
- React Native WebView: https://github.com/react-native-webview/react-native-webview
- React Native environment setup: https://reactnative.dev/docs/environment-setup
- Apple App Store Review Guidelines: https://developer.apple.com/app-store/review/guidelines/

### Sharing and public excerpts

- Argus agent guidance on public excerpts: `AGENTS.md`
- Private Alpha Conversation Trust, Slice 7 public excerpt design: `docs/archive/private-alpha-conversation-trust.md`
- Evidence-aware idea loop sharing notes: `docs/specs/evidence-aware-idea-loop.md`

### LLM/model routing and prompting

- OpenRouter Auto Router: https://openrouter.ai/docs/guides/routing/routers/auto-router
- OpenRouter Provider Selection: https://openrouter.ai/docs/guides/routing/provider-selection
- OpenRouter BYOK: https://openrouter.ai/docs/guides/overview/auth/byok
- Perplexity Agent API prompt guide: https://docs.perplexity.ai/docs/agent-api/prompt-guide
- Perplexity Agent API quickstart: https://docs.perplexity.ai/docs/agent-api/quickstart
- Perplexity Sonar quickstart: https://docs.perplexity.ai/docs/sonar/quickstart
- Perplexity Search quickstart: https://docs.perplexity.ai/docs/search/quickstart

### Voice, audio, and speech-to-text

- OpenAI audio overview: https://platform.openai.com/docs/guides/audio
- OpenAI speech-to-text: https://platform.openai.com/docs/guides/speech-to-text
- OpenAI Realtime API: https://platform.openai.com/docs/guides/realtime
- OpenAI voice agents: https://platform.openai.com/docs/guides/voice-agents
- OpenAI API pricing: https://developers.openai.com/api/docs/pricing
- OpenAI pricing page: https://openai.com/api/pricing/
- OpenAI Help, ChatGPT subscription vs API billing: https://help.openai.com/en/articles/8156019-does-chatgpt-plus-include-api-usage
- OpenRouter audio: https://openrouter.ai/docs/guides/overview/multimodal/audio
- OpenRouter speech-to-text: https://openrouter.ai/docs/guides/overview/multimodal/stt
- OpenRouter text-to-speech: https://openrouter.ai/docs/guides/overview/multimodal/tts
- ElevenLabs API pricing: https://elevenlabs.io/pricing/api
- ElevenLabs Text to Speech API: https://elevenlabs.io/text-to-speech-api
- ElevenLabs TTS docs: https://elevenlabs.io/docs/overview/capabilities/text-to-speech
- Wispr Flow product: https://wisprflow.ai/
- Wispr Flow pricing: https://wisprflow.ai/pricing
- MDN SpeechRecognition: https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition
- `whisper.cpp`: https://github.com/ggml-org/whisper.cpp
- `faster-whisper`: https://github.com/SYSTRAN/faster-whisper
- Vosk: https://alphacephei.com/vosk/
- sherpa-onnx: https://k2-fsa.github.io/sherpa/onnx/index.html

### Memory and retrieval

- OpenAI Memory and new controls: https://openai.com/index/memory-and-new-controls-for-chatgpt/
- OpenAI Memory FAQ: https://help.openai.com/en/articles/8590148-memory-faq
- OpenAI Dreaming: https://openai.com/index/chatgpt-memory-dreaming/
- LangGraph memory concepts: https://docs.langchain.com/oss/python/concepts/memory
- LangMem launch: https://www.langchain.com/blog/langmem-sdk-launch
- LangMem conceptual guide: https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- Mem0 open source overview: https://docs.mem0.ai/open-source/overview
- Mem0 LangGraph integration: https://docs.mem0.ai/integrations/langgraph
- Mem0 LangChain integration: https://docs.mem0.ai/integrations/langchain
- Mem0 tagging and organizing memories: https://docs.mem0.ai/cookbooks/essentials/tagging-and-organizing-memories
- Mem0 search memory: https://docs.mem0.ai/core-concepts/memory-operations/search
- Mem0 reranker-enhanced search: https://docs.mem0.ai/open-source/features/reranker-search
- Mem0 async memory: https://docs.mem0.ai/open-source/features/async-memory
- Mem0 Python SDK quickstart: https://docs.mem0.ai/open-source/python-quickstart
- Mem0 Node SDK quickstart: https://docs.mem0.ai/open-source/node-quickstart
- Mem0 GitHub: https://github.com/mem0ai/mem0
- Graphiti GitHub: https://github.com/getzep/graphiti
- Graphiti/Zep platform: https://www.getzep.com/platform/graphiti/
- Supabase vector columns: https://supabase.com/docs/guides/ai/vector-columns
- Perplexity embeddings quickstart: https://docs.perplexity.ai/docs/embeddings/quickstart
- Perplexity embeddings best practices: https://docs.perplexity.ai/docs/embeddings/best-practices

### Backtesting engines and licenses

- VectorBT terms: https://vectorbt.dev/terms/
- VectorBT license: https://vectorbt.dev/terms/license/
- VectorBT PyPI: https://pypi.org/project/vectorbt/
- VectorBT GitHub license: https://github.com/polakowo/vectorbt/blob/master/LICENSE.md
- VectorBT Pro terms: https://vectorbt.pro/terms/terms-of-use/
- VectorBT Pro software license: https://vectorbt.pro/terms/software-license/
- QuantConnect MCP key concepts: https://www.quantconnect.com/docs/v2/ai-assistance/mcp-server/key-concepts
- QuantConnect terms: https://www.quantconnect.com/terms/
- LEAN: https://www.lean.io/
- LEAN GitHub license: https://github.com/QuantConnect/Lean/blob/master/LICENSE

### Analytics and notes inspiration

- PostHog install docs: https://posthog.com/docs/getting-started/install
- Memos docs: https://usememos.com/docs

### Monetization and entitlement tooling

- RevenueCat API v1: https://www.revenuecat.com/docs/api-v1
- RevenueCat SDK quickstart: https://www.revenuecat.com/docs/getting-started/quickstart
- RevenueCat Stripe/web guide: https://www.revenuecat.com/docs/platform-resources/web/stripe
- Lemon Squeezy API: https://docs.lemonsqueezy.com/api
- Lemon Squeezy Merchant of Record: https://www.lemonsqueezy.com/blog/merchant-of-record

### Local Argus source-of-truth docs

- `docs/PRODUCT.md`
- `docs/ARCHITECTURE.md`
- `docs/API_CONTRACT.md`
- `docs/DATA_MODEL.md`
- `docs/specs/private-alpha-next-integration.md`

## Follow-Up Items To Sharpen Before Implementation Planning

The memo is good enough for strategic direction, but these areas are
underweighted and should be made explicit before turning the vision into
implementation slices.

### First killer loop

Argus has several promising loops: research, backtest, memory, comparison,
sharing, and eventual broker handoff. Before building broadly, define the first
PMF loop sharply.

Candidate first loop:

```text
Messy idea
-> canonical test
-> evidence artifact
-> save decision
-> revisit/compare later
```

This loop should answer: why would a trusted alpha user come back next week?

### Evaluation as infrastructure

Argus needs a repeatable evaluation harness, not only browser spot checks.

The eval set should cover:

- messy English prompts;
- messy Spanish prompts;
- language-agnostic prompts where UI language and user language differ;
- action-chip examples as semantic capability examples, not exact phrases;
- research-to-test conversion;
- memory freshness and stale-memory behavior;
- backtest metric correctness;
- graceful recovery when Argus cannot execute.

This is how Argus avoids rebuilding brittle phrase gates and stops relying on
vibes when the runtime changes.

### Compliance, consent, and data-rights boundary

Do not overbuild legal/governance for private alpha, but do define the minimum
safe boundary:

- alpha consent;
- education-only framing;
- no investment advice;
- no real-money execution in Alpha;
- memory controls;
- data deletion/export expectations;
- provider data usage and display rights;
- market data/news/chart licensing constraints before commercialization.
- Supabase data-region, DPA, SOC 2, and project-region posture;
- PostHog Cloud US/EU selection, DPA, SOC 2, GDPR consent, and data-minimizing
  analytics configuration;
- region-specific terms/privacy variants before expanding beyond the first
  launch region.

This should become a readiness checklist, not a blocker for learning.

### Backtest credibility ladder

The current engine can support the learning loop, but the roadmap needs a clear
credibility ladder between basic backtests and an advanced engine.

Audit and stage:

- fees/slippage/spread assumptions;
- splits/dividends;
- missing data behavior;
- benchmark correctness;
- drawdown and risk metrics;
- indicator support;
- options backtesting boundaries;
- crypto/forex differences;
- reproducibility and provenance.

### Cost and latency routing

The future stack may include OpenRouter, Perplexity, Mem0, STT, charting, and
external engines. Argus needs routing rules so the product stays fast and
affordable.

Principle:

- cheap/fast model for simple turns;
- stronger reasoning when interpretation confidence is low;
- Perplexity/Search only when freshness matters;
- memory retrieval only when useful;
- STT only when user records voice;
- never spend premium tokens on a turn that can be answered from canonical
  state.

### Failure and recovery trust

Argus will fail sometimes. The recovery surface must preserve trust.

Requirements:

- preserve the user's idea;
- clarify without making the user feel wrong;
- explain unsupported capability in product language;
- suggest supported next steps;
- avoid raw provider/runtime errors;
- avoid English fallback leaks when the UI/user context is Spanish.

### Memory privacy controls

Memory is a moat only if users trust it.

Controls to define early:

- inspect memories;
- edit/delete memories;
- disable memory;
- temporary/private chat;
- show why a memory was used;
- distinguish explicit saved decisions from inferred preferences.

### Distribution wedge

Sharing is strategically important but still needs a sharper object.

Options:

- public evidence artifact;
- "before money moved" decision receipt;
- idea comparison card;
- research-to-test digest;
- saved idea progress card.

The right object should be useful to the sender even if nobody clicks it.

### Mobile as retention, not salvation

iOS and voice are strategically right, but they should follow proof that the web
loop retains.

Operating stance:

- private alpha and public alpha prove the web loop;
- iOS shell can be explored in parallel if it stays lightweight;
- beta can use mobile/voice to make the habit easier;
- mobile should not distract from the evidence/memory loop.

### Monetization readiness

Do not decide pricing before PMF, but do prepare the product architecture for
clean monetization later.

Follow-up questions:

- Which behavior repeats strongly enough to justify charging?
- Is the value in more usage, more memory, more research, better evidence,
  monitoring, mobile convenience, or broker handoff?
- Which features are trust-critical and should stay free?
- What quota or entitlement checks can be added without changing the product
  feel?
- What legal/privacy state must exist before taking payment?

Implementation posture:

- build an internal entitlement spine in Supabase;
- mirror billing-provider state into Argus;
- evaluate Lemon Squeezy for web checkout/subscriptions/MoR;
- evaluate RevenueCat for iOS/mobile subscriptions and entitlement management;
- keep payment UI disabled until PMF and readiness signals justify it.

## 15. Founder Clarification Addendum - 2026-06-15

This addendum captures the latest founder direction after the first market-shift
memo review. It should be treated as strategy clarification, not an implementation
spec. The next implementation specs should slice these items only after the
readiness/runtime branch is stable.

### 15.1 Idea, Strategy, Run, Evidence, and Decision Object Boundary

This remains the main product-model area to formalize before a schema or UI spec
is written. The high-level direction is now clear: Argus should auto-capture
completed evidence into the idea model, while user commitment remains explicit.

Current recommended object shape:

```text
Idea = persistent user thesis/question
IdeaVersion = one canonical snapshot of that idea at a point in time
Strategy = executable method inside an IdeaVersion
Run = internal engine execution of one CanonicalBacktestSpec
EvidenceArtifact = human-readable proof object from run/research/context
DecisionNote = user's judgment after seeing evidence
```

Core principle:

```text
Persistence is automatic.
Commitment is explicit.
```

Once a backtest completes, Argus has enough trusted structure to create or attach
an `Idea`, `IdeaVersion`, internal `Run`, user-facing `Backtest`, and
`EvidenceArtifact`. It should not wait for a manual "Save idea" action before
creating the domain objects. Waiting would trap valuable evidence inside chat
history, weaken Omnisearch, and make learning/comparison harder.

However, Argus must not present every captured object as if the user deliberately
saved or endorsed it. The object should carry lifecycle labels that distinguish
system capture from user commitment:

```text
captured = Argus inferred and stored it from completed work
reviewed = user opened or revisited the object
saved = user explicitly saved, pinned, or promoted it
decided = user attached a DecisionNote
archived = user hid it from active recall
discarded = user rejected or dismissed it
```

This lets Argus learn from the full exploration funnel without lying about user
intent. It also gives Omnisearch enough structure to retrieve work that the user
did not explicitly file, while preserving trust through visible status.

Example:

```text
Idea:
"Should I buy ETH after this pullback?"

IdeaVersion:
"Buy and hold ETH, $100k, last 8 months, benchmark BTC"

Strategy:
buy_and_hold

Run:
the actual backtest execution; user-facing surfaces should label this as
"Backtest" rather than "Run"

EvidenceArtifact:
result card + assumptions + metrics + quick take + breakdown + provenance

DecisionNote:
"Watching. Revisit next week if ETH underperforms BTC again."
```

Key clarification: Quick take and Breakdown should become first-class context
inside the EvidenceArtifact. They are not just UI copy. They are the user-facing
interpretation layer attached to the canonical evidence package, and future
revisit/compare/memory flows should be able to reference them.

Naming clarification: `Run` can remain the backend/domain word for an engine
execution, but the user-facing artifact tag should be `Backtest` when Argus is
showing a completed historical simulation. This matches current product language
and avoids exposing implementation vocabulary in the search/ledger surface.

Recommended lifecycle:

```text
1. User chats normally.
2. Argus interprets and confirms a testable idea.
3. Confirmation creates or updates an IdeaVersion candidate.
4. Running the backtest creates an internal Run.
5. The result card is presented as a Backtest.
6. Argus stores an EvidenceArtifact with assumptions, metrics, quick take,
   breakdown, provenance, and artifact digest.
7. Argus auto-captures the related Idea/IdeaVersion as `captured` if it does not
   already exist.
8. If the user saves, pins, judges, revisits, archives, or rejects it, Argus
   updates lifecycle/status labels without rewriting the historical evidence.
9. If the user adds a decision, Argus attaches a DecisionNote and marks the idea
   or version as `decided`.
```

LLM and deterministic responsibilities:

- The LLM may propose the idea title, thesis summary, grouping into an existing
  idea, preview digest, and lifecycle suggestion.
- Deterministic policy owns object creation, immutable version/evidence records,
  user-commitment labels, permissions, and event logging.
- User actions override LLM classification.
- Nothing becomes `saved` or `decided` without explicit user action.
- Captured objects may be searched, ranked, and used for product analytics, but
  memory/personalization use should still follow the separate memory opt-in
  policy.

Resolved direction:

- DecisionNote is not required for an artifact to become an Idea record. Argus
  can create or attach an Idea from completed evidence alone, labeled as
  `captured`.
- A user save/pin/decision action is required before calling the object
  explicitly saved, decided, or user-endorsed.

Legacy save-strategy salvage decision:

- The existing feature-flagged `Save` action on the result card is a useful
  interaction pattern, but the old `save_strategy` product semantics should not
  be carried forward directly.
- Salvage the good parts: result-card action placement, canonical save from
  structured run/result state, idempotent saved state, and the notion that a user
  can promote evidence after seeing it.
- Do not carry forward the old product center: the `Strategies` sidebar surface,
  broad strategy-template shelf, or the assumption that the destination is a
  saved executable strategy.
- The new meaning should be lifecycle promotion on an already auto-captured
  artifact: `captured` by default, `Save` promotes to `saved`, `Add decision`
  promotes to `decided`, and later archive/discard hide or demote the artifact
  from active recall.
- The successor action should be named around the new object model, for example
  `save_idea`, `save_artifact`, `mark_saved`, or `add_decision`, rather than
  `save_strategy`.
- The destination for promoted artifacts should be Omnisearch/Ledger recall, not
  the old Strategies view.
- Keep the old flagged Strategies surface quarantined behind its existing flag
  for now. Do not depend on it for the next object-model implementation, but do
  not destroy it until the new lifecycle path is proven and a migration/removal
  decision is explicit.

Resolved version/evidence boundary:

- One `IdeaVersion` represents one material experiment definition.
- Material changes to assets, date range, benchmark, strategy or executable
  rules, cadence, capital, or modeled costs create a new version.
- Multiple edits before one confirmed run collapse into one version; wording,
  explanations, retries, and abandoned edits do not create versions.
- A rerun on fresher data may attach new immutable evidence to the same version
  only when the canonical experiment is unchanged.
- An updated date range is material and creates a new version whose assumptions
  and performance can be compared with the prior version.
- Research-only evidence remains outside the A1b contract until the
  freshness/research artifact type and ownership rules are separately specified.

### 15.2 Ledger UI, Recents, and Omnisearch

Founder direction: do not assume the first Idea Ledger must be a heavy top-level
navigation surface. Argus must remain elegant, simple, and intuitive.

Concern: adding a new Recents row every time an idea version updates could create
a long, painful list. Search and scrolling would become poor defaults if every
version or artifact appears as a separate chat-like entry.

Clarified direction:

- Recents can become idea-aware, but it should not become a noisy append-only
  stream of every version. Its primary job remains chat navigation.
- Omnisearch/search should become the first user-facing recall surface for chats,
  ideas, backtests, evidence artifacts, and decision states.
- The Idea Ledger should begin as the underlying object/data spine, not as a
  heavy top-level dashboard. Omnisearch is the wedge that lets users discover
  whether they need a fuller ledger later.
- The left result list should be artifact-first and typed. If the result is a
  conversation, the right panel previews the conversation. If the result is a
  backtest, evidence artifact, decision note, or idea, the right panel previews
  that selected object directly.
- Conversation becomes provenance for artifact results: "from conversation X" or
  "part of idea Y." It should not swallow the artifact preview.
- Search results should tag the object type with clear product language:
  `Conversation`, `Backtest`, `Evidence`, `Decision`, or `Idea`. Internally the
  backend may keep `Run`, but the UI should use `Backtest` for completed
  historical simulations.
- The preview panel should be a grounded, cached/stored digest, not a fragile
  replay of runtime state. It can summarize relevant items, assumptions,
  discoveries, decisions, and related artifacts from the owning conversation or
  idea chain.
- Collapsed mode should stay fast and scan-first. Expanded mode adds the right
  preview panel for context and action. Hovering a result updates the preview;
  clicking or pressing Enter opens the result's default destination.
- The search list should remain scan-first: type pill, optional status pill
  (`Current`, `Saved`, `Decision`, `Archived`), date, highlighted match context,
  and at most one or two safe hover icons plus overflow.
- Do not use press-and-hold as the primary action pattern. It is too hidden for
  desktop/web search and weak for keyboard accessibility. The type pill should
  stay a stable label, not morph into an action cluster.
- Hover actions should be artifact-type aware. They should modify the selected
  object only when that object is naturally user-managed.
- Conversation hover actions may include rename/archive/delete because the
  conversation is a user-managed container.
- Backtest/evidence hover actions should emphasize workflow: open, add decision,
  save/attach to idea, or later compare. Edit/delete should not be primary row
  actions for evidence-like artifacts.
- Decision note hover actions may include edit note, revisit, and archive.
  Destructive actions should live behind overflow and confirmation.
- Idea hover actions may include open, pin, rename, archive, and overflow. Full
  action sets belong in the right panel where there is room for labels and
  context.
- Rows are for finding and previewing. The right panel is for understanding and
  acting.
- Comparison remains undefined for this slice. Omnisearch can expose future
  compare entry points, but it should not try to solve chart/result comparison
  inside the search modal yet.

Roadmap note:

```text
Do not spec a full standalone Idea Ledger UI yet.
Spec Omnisearch vNext first:
1. conversation recall with highlighted context,
2. richer artifact digest in the right panel,
3. typed artifact results for Conversation, Backtest, Evidence, Decision, Idea,
4. artifact-aware hover actions plus right-panel action sets,
5. ledger object spine behind the surface.

Only create a dedicated Ledger surface if usage proves users want to browse and
manage ideas outside chat/search.
```

### 15.3 Memory Product Posture

Founder direction updated: memories should be off by default, but Argus should
offer a SOTA opt-in moment that does not nag the user.

Reference behavior: OpenAI Codex Memories carry useful context from prior threads
into future work, are configurable, can be controlled per thread, and are stored
as user-scoped generated memory state. The docs also note memory generation can
skip active/short-lived sessions, happen in the background after idle time, and
redact secrets from generated memory fields.

Reference:

- OpenAI Codex Memories: https://developers.openai.com/codex/memories
- Codex Config Basics / feature flags: https://developers.openai.com/codex/config-basic

Argus posture:

- Durable `Idea` / `IdeaVersion` / `EvidenceArtifact` / `DecisionNote` recall is
  sufficient for the P2 product-memory promise and does not require
  personalization memory.
- Memory is off by default for early Alpha.
- Argus may invite the user to enable memories only at earned, high-signal
  moments where it can name the exact future benefit.
- Profile menu should eventually expose: Data Controls -> Personalization.
- Users should be able to inspect, edit, delete, reset, and disable memories.
- Argus should support temporary/private chats.
- Argus should explain why a memory was used.
- Existing onboarding flow is a candidate passive education surface if it can be
  adapted without adding friction, but the first session should not default to a
  generic "turn on memories" modal.
- Data Controls remains the permanent user-control surface, but memory should
  not be discoverable only through hidden settings. The product should introduce
  memory through value moments in the core chat/evidence loop.
- The first opt-in should be scoped to "remember saved decisions" before broader
  personalization memory. That is the least creepy memory promise and directly
  supports revisit, compare, and decision history.

Settings and Data Controls adaptive work:

- The current `Data & Information` label should evolve to `Data Controls`.
  "Data & Information" sounds passive; the future surface is where the user
  controls what Argus stores, remembers, hides, deletes, exports, and uses for
  personalization.
- The current `Settings` submenu should be reframed as `Preferences` because it
  contains app behavior choices such as appearance, app language, sidebar, and
  security/account settings. Private-alpha feedback showed that clicking
  `Settings` and then seeing another `Settings` layer is confusing.
- Recommended top-level profile menu shape:

```text
Profile
Preferences
Data Controls
Help
Feedback
Log out
```

- Recommended `Preferences` submenu:

```text
Appearance
App language
Sidebar
Security / Account security
```

- Recommended `Data Controls` submenu:

```text
Personalization / Memory
Chats
Ideas & backtests
Archived items
Recently deleted
Export data
Delete all conversations / Delete account data
```

- The product can sketch the full future settings submodel before every backend
  capability exists. Active items should remain truly functional. Future items
  should be visible but disabled/greyed with clear unavailable states, similar
  to the current disabled Security row.
- Do not turn this into a giant settings dashboard. Keep the lightweight,
  in-context popover model unless later user behavior proves a need for a larger
  settings surface.
- SOTA control pattern: contextual controls where the user is working; durable
  controls in Data Controls; app behavior in Preferences.
- Contextual examples: result cards can expose `Save` and `Add decision`;
  Omnisearch previews can expose artifact actions; memory opt-in moments can
  include `Manage`; memory-used explanations can link back to inspect/edit
  controls.
- Durable examples: archived/deleted chats, personalization/memory inspection,
  idea/backtest data management, exports, and destructive account/data actions
  belong under Data Controls.
- This is adaptive implementation work for the next horizon: adjust labels and
  menu hierarchy surgically while preserving the existing working controls, then
  progressively un-grey future controls as their backing implementation lands.

Canonical memory categories should be defined before implementation. Candidate
categories:

- personalization preferences: preferred language, asset classes, default
  benchmark preferences, risk explanation style;
- workflow preferences: likes buy-and-hold baseline first, wants assumptions
  surfaced before execution, prefers concise result reads;
- explicit saved decisions and notes: user tells Argus to remember a decision or
  preference;
- automation intent: reminders or revisit requests that the user explicitly asks
  Argus to track;
- past-session anchors: references to prior saved ideas, evidence artifacts, and
  decision states.

Sensitive or restricted memory categories should not be captured automatically:

- broker credentials;
- account balances;
- exact holdings;
- tax or legal status;
- personally identifying financial details;
- health, employment, family, or other sensitive context unless explicitly saved
  by the user and supported by policy.

Memory extraction should be LLM-assisted, but constrained by canonical memory
categories and user controls. The LLM brain may propose memory candidates, but
the product must own what is stored, why it is stored, and how users can inspect
or delete it.

SOTA memory proposal model:

```text
Conversation/evidence context
-> LLM proposes MemoryCandidate objects
-> deterministic policy gate validates category, sensitivity, consent, cooldown,
   and trigger quality
-> Argus asks the user with specific benefit and control copy
-> user confirms, edits, declines, or opens Data Controls
-> canonical MemoryRecord is stored only after allowed confirmation
```

The LLM brain should power judgment, not storage authority. It should evaluate
the conversation, EvidenceArtifact, DecisionNote, locale, repeated preference
patterns, and user language to propose memory candidates with:

- candidate category;
- short user-facing label;
- proposed stored value;
- why this would help future Argus sessions;
- source references, such as EvidenceArtifact id or DecisionNote id;
- sensitivity flags;
- confidence;
- suggested prompt copy.

The deterministic policy layer must then enforce:

- memory is enabled or the prompt is an allowed opt-in moment;
- category is allowlisted;
- candidate is not in a restricted/sensitive category;
- broker/export/sensitive financial flows do not trigger proactive memory asks;
- repeated nags are suppressed through cooldowns and dismiss history;
- explicit user confirmation is required before new memory is stored;
- all saved memories remain inspectable, editable, deletable, resettable, and
  disableable from Data Controls.

Locked proposal moments for the memory spec:

- after a user explicitly says "remember";
- after a user saves a decision, with the first ask framed as "remember saved
  decisions like this so you can revisit and compare ideas later";
- after repeated stable preferences appear across conversations, framed as a
  narrow suggested default such as benchmark, language, or explanation style;
- during onboarding only as a passive or optional personalization surface that
  does not block the golden path;
- never during sensitive/broker/export flows without explicit confirmation.

Memory prompt standard:

```text
Argus should propose memory only when it can name:
1. the exact thing it wants to remember,
2. the future user benefit,
3. where the user can inspect, edit, or turn it off.
```

The next memory spec should define:

- `MemoryCandidate` and `MemoryRecord` shapes;
- the LLM proposal prompt/eval set;
- deterministic policy gates and cooldown rules;
- first opt-in copy for saved decisions;
- Data Controls behavior;
- memory analytics events, including candidate proposed, prompt shown, accepted,
  declined, edited, deleted, disabled, and memory used;
- Spanish and English prompt behavior;
- suppression tests for broker/export and sensitive financial contexts.

### 15.4 Voice STT and TTS Provider Clarification

Founder direction: voice remains STT into composer. No auto-send, no
speech-to-speech runtime, no second chat brain.

Current provider clarification:

- ElevenLabs Scribe v1/v2 is Speech-to-Text. ElevenLabs API pricing currently
  lists Scribe v1/v2 at $0.22 per hour and Scribe v2 Realtime at $0.39 per hour.
  Source: https://elevenlabs.io/pricing/api
- OpenRouter supports dedicated audio transcription endpoints and notes STT
  pricing can be duration-based or token-based depending on provider. The
  response usage.cost field should be used to track actual request cost. Source:
  https://openrouter.ai/docs/guides/overview/multimodal/stt
- OpenRouter lists OpenAI GPT-4o Mini Transcribe as a speech-to-text model at
  token-based pricing. Source:
  https://openrouter.ai/collections/speech-to-text-models
- hexgrad/kokoro-82m on OpenRouter is Text-to-Speech, not Speech-to-Text. It is
  useful for future spoken response/read-aloud experiments, not the first
  voice-to-composer STT chain. OpenRouter lists Kokoro 82M at $0.62 per million
  input characters. Source: https://openrouter.ai/hexgrad/kokoro-82m

Recommended first voice chain:

```text
User records audio
-> STT provider transcribes
-> transcript fills existing composer
-> user edits transcript
-> user sends
-> normal language/runtime spine handles the turn
```

Provider chain to evaluate and lock for the first voice-to-composer spec:

```text
Default STT candidate:
ElevenLabs Scribe v1/v2 for low-cost multilingual STT

Fallback STT candidate:
OpenRouter-hosted STT model such as GPT-4o Mini Transcribe

Realtime STT candidate:
ElevenLabs Scribe v2 Realtime only if the product needs live transcription

Future TTS/read-aloud candidate, not part of the STT chain:
OpenRouter hexgrad/kokoro-82m or equivalent TTS model.
```

This supersedes earlier draft assumptions that treated OpenAI/OpenRouter STT as
the primary path. The product should start with Scribe v1/v2, then fall back to
OpenRouter/OpenAI GPT-4o Mini Transcribe, then use Scribe v2 Realtime only for
live transcription needs.

Cost note:

Per-hour STT pricing is easier to estimate before launch. Token-priced STT may
be cheaper for short clips or may become expensive depending on audio tokenization
and output length. Argus should not choose purely from listed pricing. The first
voice spec should add a small measurement harness that stores:

- provider;
- model;
- audio duration seconds;
- transcript character count;
- usage.cost when available;
- latency;
- language;
- transcription confidence/error category;
- whether the user edited the transcript before sending.

### 15.5 Evaluation, Cost, and Analytics Instrumentation

Founder direction: raw prompt/result data is acceptable for private Alpha for
learning speed, with the understanding that payload controls can tighten later.

Recommended posture:

```text
raw_alpha -> redacted_default -> metadata_only -> disabled
```

Clarified architecture: PostHog is the product analytics surface, not the source
of truth for provider spend or eval readiness. Argus should define a stable
observability envelope and an append-only internal cost/eval ledger so product
learning, runtime quality, and provider cost can be attributed to the same turn
without sending every sensitive payload to analytics.

Spec posture:

- PostHog tracks product behavior, funnel conversion, retention, and aggregate
  events.
- A first-party `CostLedger` or equivalent append-only operational table tracks
  provider cost, estimated cost, actual cost, latency, provider request ids,
  usage metadata, and feature attribution.
- A portable eval harness tracks readiness categories before memory, STT,
  research/freshness, evidence loops, and broker handoff grow more complex.
- Correlation ids should be generated before provider calls so route receipts,
  cost records, eval cases, and product events can be joined without relying on
  raw transcript payloads.

Recommended event envelope:

```text
schema_version
event_id
occurred_at
environment
privacy_mode
event_type
event_action
feature_area
actor_hash
session_id
conversation_id
turn_id
message_id
job_id
backtest_run_id
route_receipt_id
provider
model
provider_request_id
upstream_id
status
latency_ms
usage
cost
error_category
sampling_rate
retention_class
```

The product should define event categories early so analytics can evolve without
migration pain:

- user_message;
- ai_interpretation;
- ai_response;
- tool_call;
- tool_result;
- research;
- stt;
- storage;
- system;
- recovery;
- decision_saved;
- revisit_opened;
- compare_started;
- memory_candidate_proposed;
- memory_candidate_suppressed;
- cost_ledger_entry;
- eval_case_run;
- eval_suite_run;
- broker_handoff_prep.

Each event should carry an `event_action` such as `started`, `completed`,
`failed`, `suppressed`, `redacted`, `sampled`, or `reconciled` rather than
creating a new event name for every state transition.

Cost attribution should be feature-scoped:

- `chat_interpretation`;
- `result_explanation`;
- `memory_candidate_proposal`;
- `research_light`;
- `research_deep`;
- `freshness_check`;
- `stt`;
- `storage`;
- `broker_handoff_prep`.

Provider telemetry posture:

- OpenRouter usage/cost metadata should be captured per request when available.
- OpenAI request ids and organization cost APIs should be used for reconciliation
  when OpenAI is called directly.
- ElevenLabs Scribe/STT should be costed from audio duration and reconciled with
  provider usage, because duration-based STT may not return per-request cost.
- PostHog should not be treated as the canonical spend ledger.

Eval harness categories to lock before implementation:

- messy English prompts;
- messy Spanish prompts;
- UI language and user language mismatch;
- action-chip examples as semantic capability examples, not phrase gates;
- memory proposal and suppression;
- stale-memory behavior;
- broker handoff suppression and proper export language;
- STT transcript correction and edit-before-send behavior;
- research-to-test conversion;
- graceful recovery when Argus cannot execute;
- backtest metric correctness and result-card consistency.

Private Alpha may retain raw prompt/result/research/transcript payloads for
learning speed when users have consented, but future modes should move raw text
out of broad analytics and into product-owned conversation records or redacted
summaries. Never send broker credentials, auth tokens, payment identifiers,
account balances, exact holdings, full audio recordings, or public-excerpt
route receipts into product analytics.

### 15.6 Broker / Export Handoff Scope

Founder direction: broker/export work should become a proper handoff, not a
generic checklist and not a dump of Argus internals. Argus should hand the user
to a broker-owned review or authenticated preview context where the relevant
order details are already carried over as far as the broker/sandbox allows, then
the user takes over review and submission. Argus does not submit trades for
users.

The handoff should be broker-relevant and minimal. Most Argus data is not useful
to the broker and should not travel with the handoff. Evidence, memory, route
receipts, provider/model metadata, raw conversation text, retry payloads, and
private user context stay inside Argus unless a field is specifically needed for
the broker review packet.

Clarified scope:

- design export and handoff contracts for Alpaca and Interactive Brokers first;
- use sandbox/paper/authenticated-preview environments to develop the handoff in
  a SOTA way before any production brokerage integration;
- do not collect production broker credentials in Alpha;
- do not submit real-money orders;
- carry `buy` / `sell` side into the handoff packet when it comes from the
  user's stated idea or explicit confirmation, but require user review before
  anything reaches broker submission;
- carry notional or quantity only when the user explicitly supplied it. Never
  infer a real order size from backtest starting capital, allocation, simulated
  portfolio value, or generated prose;
- focus on a broker-ready review packet tied to an EvidenceArtifact and
  DecisionNote, with broker-specific fields included only when they are relevant
  to the target handoff.

Locked handoff object:

```text
BrokerReviewPacket
  packet_id
  created_at
  expires_at
  source_evidence_artifact_id
  source_decision_note_id
  instrument
  intent
  candidate_order
  broker_mapping
  validation
  disclosures
  user_acknowledgment
```

Likely packet fields:

- asset symbol and asset class;
- broker-specific identifier only when confidently resolved, such as Alpaca
  symbol/asset id or IBKR conid/conidex;
- intended side, including `buy` or `sell`;
- explicit user-supplied notional or quantity;
- candidate order type;
- time-in-force candidate;
- extended-hours / outside-RTH intent if applicable;
- limit/stop fields only if explicitly supplied by the user;
- source EvidenceArtifact id;
- source DecisionNote id;
- timestamp and expiry;
- assumptions, warnings, and disclosure copy;
- validation tier;
- user confirmation state.

Validation tiers:

```text
argus_supported_intent
broker_static_mapping
broker_sandbox_preview
broker_authenticated_preview
broker_submitted
```

`broker_submitted` must never be set by Argus in Alpha. In sandbox development,
Argus may go as far as needed to test a high-quality authenticated preview or
paper/sandbox handoff, but production user-facing flows remain review/handoff
only until a later legal/product milestone approves anything stronger.

Broker-specific posture:

- Alpaca: use sandbox/paper and official order-estimation or preview-like paths
  to learn the proper handoff shape. Do not use Alpaca MCP/CLI as an Alpha
  execution path. Production handoff should remain review/preview/export until
  explicitly approved.
- Interactive Brokers: prefer a what-if / authenticated-preview / AI
  instructions style handoff where the final order review and submission remain
  in IBKR-owned surfaces. Symbol-only handoff is insufficient when IBKR requires
  broker-specific identifiers such as conid/conidex.

Disclosure and confirmation standard:

- The handoff is educational/export/preparation, not investment advice and not
  an order submission.
- Market prices, fees, margin, permissions, asset availability, and order rules
  can change after Argus creates the packet.
- Broker validation is required before submission.
- The user must review side, quantity/notional, order type, time in force, and
  all broker warnings in the broker-owned surface.
- Argus confirmation means "I reviewed/exported this packet"; broker
  confirmation means "I submitted this order."

The broker handoff spec should include suppression tests for requests to trade,
connect real accounts, submit orders, copy-trade, schedule orders, or infer order
size from simulated backtest capital.

### 15.7 Public Excerpt Timing

Founder direction: public excerpts can become testable right away in mock/internal
development, then later available to allowlist users once ready.

Guardrail remains:

Public excerpt must be a sanitized EvidenceArtifactSnapshot, not a conversation
link. It must not expose source conversation ids, route receipts, provider/model
metadata, retry payloads, raw transcripts, broker/account data, or user-private
memory.

### 15.8 PMF Gates

Founder direction: use the metrics already captured in this memo as the PMF
signal for Beta/iOS/monetization gates.

Primary gates:

- at least 3 of 5 trusted users save a decision;
- at least 2 of 5 voluntarily revisit or ask to compare;
- at least 2 users describe a concrete decision Argus changed, delayed, or
  clarified;
- Spanish-preferring users can complete the same loop without founder help;
- users can explain the artifact assumptions without founder explanation.

These gates should be tracked before activating monetization, shipping native
iOS, or prioritizing broker handoff.

Use one cohort of five trusted users for the formal PMF readout. Do not treat a
smaller founder-guided pilot as PMF closure. As of 2026-07-16 the gate is
unmeasurable because the production Render compute plan prevents users from
completing internet-based Argus tests; record no pass/fail conclusion until that
capacity blocker is removed.

## 16. Founder Resolution Addendum - 2026-07-16

This addendum locks product boundaries before the next interim roadmap steer. It
clarifies truth and completion semantics; it does not authorize implementation
or preserve the current priority order after the founder publishes the next
steer.

### 16.1 P2 Memory Boundary

Durable recall from `Idea`, `IdeaVersion`, `EvidenceArtifact`, and
`DecisionNote` is sufficient for P2. Personalization memory, including a
user-confirmed `MemoryRecord`, stays post-PMF and requires earned opt-in plus
inspect/edit/delete/reset/disable/"why was this used?" controls.

### 16.2 Version And Evidence Boundary

- One material experiment definition maps to one immutable `IdeaVersion`.
- Material changes include assets, date range, benchmark, strategy or
  executable rules, cadence, capital, and modeled costs.
- Multiple edits before one confirmed run collapse into one version.
- Wording, explanations, retries, and abandoned edits do not create versions.
- An unchanged canonical experiment rerun on fresher data creates new immutable
  evidence on the same version.
- An updated date range creates a new version. Argus should compare the new
  version's performance and assumptions with the prior version and explain the
  delta from canonical evidence.

### 16.3 Freshness And Event Context

The minimum freshness product shows when the idea was last reviewed, reruns the
canonical experiment on fresh provider data, and explains numeric deltas.
Freshness should also develop a bounded source-backed research path for relevant
news, earnings, corporate actions, regulatory events, macro events, and other
time-sensitive context.

Mechanically verified corporate actions may be stated as facts. Other events
must be presented as contextual associations using cautious language such as
"coincided with" or "may have contributed." Argus must cite the context, expose
freshness/uncertainty, avoid unsupported causation, remain informational, and
never present the readout as financial advice or a recommendation to buy, sell,
or hold.

### 16.4 PMF Cohort And Current Blocker

Use one cohort of five trusted users for the formal PMF gates in section 15.8.
The current Render compute-plan bottleneck prevents users from completing
internet-based Argus tests, so the PMF gate is unmeasured rather than passed or
failed. Restore sufficient compute capacity before drawing product conclusions
from those gates.

### 16.5 Engine Boundary

The current engine launch adapter is sufficient. Argus continues to own
canonical run/evidence contracts and must not leak engine-native output into
product objects. A formal multi-engine interface remains deferred until a
second validated engine or workflow demonstrates a concrete user-facing need.

## 18. Founder Resolution Addendum - 2026-08-06

A competitor review of [driven.ai](https://driven.ai) produced one finding that
reordered execution without changing this memo's thesis. The active board is
`docs/specs/argus-active-roadmap.md`; this section records what changed here.

### 18.1 What The Review Found

Driven sells an AI investment workspace: agents, skills, live data, persistent
profiles, monitoring, portfolios, and paper trading. Its documented quickstart
does not include backtesting, so it is not competing for the same job.

But its entire first session is a research read, and that is the same first
message Argus receives. Argus currently refuses it. Users are lost before
reaching historical validation, which is the thing Argus is good at.

The threat is not breadth. Breadth is Driven's onboarding tax: Google sign-in
plus a multi-step setup before anything happens. Argus's guest entry, where a
first completed backtest is activation rather than account creation, is a real
advantage that this memo already argued for.

### 18.2 What Changed

Timing, not thesis. Section 5.6's layering, section 10.5's sequencing, section
12.3's assisted-not-automatic rule, section 15.3's memory posture, and section
16.1's P2 boundary all stand unchanged.

Three sequencing consequences:

1. **Answering an ordinary finance question is now the first priority.** This
   memo's section 21 filter asks whether a change makes it easier for a normal
   person to turn curiosity into a grounded experiment. Refusing the opening
   question fails that filter at the first step. Research becomes an explicit
   typed act that produces sources and candidate entities, then offers one to
   three prebaked runnable test cards through the existing typed Try-next
   surface. It does not become a research platform or a skill store.
2. **Mobile readiness is a hard public-exposure gate**, not a decision spike.
   Consistent with section 15.8's PMF gates: the loop must work where people
   actually open it.
3. **Product memory is promoted.** Section 16.1 holds that durable
   Idea/IdeaVersion/EvidenceArtifact/DecisionNote recall is sufficient for P2.
   The review sharpened why it is urgent: backtesting is copyable, an
   accumulated record of a user's own decisions is not. It is the
   differentiation this memo describes and the product has not yet proven.

### 18.3 What Was Explicitly Refused

No agent marketplace, model picker, multi-hundred-API integration story,
autonomous monitoring, portfolio system, messaging channels, or trading
workflow. No auth-gated marketing site between a visitor and their first test.
Argus remains the pre-flight checklist, not an investment command center.

### 18.4 Delivery Model Change

Phased and incubation delivery is retired. A dispatched lane is built
production-ready end to end, including tests, evidence, and docs. Work that is
not ready for users ships behind a default-off flag rather than behind a staged
branch. Personalization memory, delivered this way on 2026-08-06, is the
reference example; its remaining decisions live in its own pull-request docs.
