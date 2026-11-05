# Evidence-Aware Idea Loop

**Status:** Source thesis / strategic background. This spec directly informed
`docs/specs/private-alpha-next-decision-memo.md`; use the decision memo as the
current strategic north star and `docs/specs/private-alpha-next-roadmap.md` as
the execution board.
**Date:** 2026-06-10
**Branch:** `codex/private-alpha-next`
**Audience:** Founder, Codex, future implementation agents, reviewers

## Purpose

This spec defines the product direction after the private-alpha conversation
trust checkpoint. It refines the earlier Research Lab thesis into a flexible,
testable product loop that supports direct backtests, education, lightweight
evidence, and deeper research without forcing every user through the same path.

The goal is not to implement Perplexity immediately. The goal is to align on
the vision, milestone ladder, architecture implications, and open questions so
the first implementation slice can test whether the market actually needs this
product direction.

## Context

Argus is currently a chat-first investing idea validation platform. The hardened
private-alpha system can:

- interpret natural-language investing ideas;
- produce confirmation cards;
- run workflow-backed historical backtests;
- render result cards with Quick take and Explain result surfaces while normal
  typed follow-ups remain available through the chat brain;
- persist conversations, messages, jobs, and runs in Supabase;
- preserve a manual deployment and canary workflow for production trust.

The next strategic question is whether Argus should remain a better chat-driven
backtest calculator or evolve into a place where investing thinking accumulates.

## Research Synthesis

Four external research agents produced strategy memos in `temp/`:

- `gpt-research.md`
- `gemini-research.md`
- `deepseek-research.md`
- `grok-research.md`

They broadly reconciled on the following conclusions:

- The Research Lab direction is stronger than "AI backtesting chat" if kept
  narrow and grounded in executable tests.
- Argus should not become a brokerage, a trading terminal, a generic finance
  chatbot, or a broad autonomous analyst.
- Perplexity is best treated as a research/citation provider, not the Argus
  runtime, not the simulation engine, and not the source of final result truth.
- OpenRouter remains the conversational/runtime model provider for Argus voice,
  structured drafting, clarification, result explanations, and refinement.
- Deterministic Argus code must own capability checks, asset resolution,
  same-asset constraints, date windows, benchmark defaults, backtest job
  creation, engine execution, and persisted run truth.
- The strongest product wedge is the bridge from messy curiosity to supported
  experiment candidates, not cited answers by themselves.
- The first implementation must be small, feature-gated, observable, and easy
  to reverse if users do not value it.

They differed on ambition:

- The most disciplined memos recommend an in-chat cited answer or research note
  that can become a confirmation card.
- The more ambitious memos push toward "My Lab" dashboards, public artifacts,
  pg_jsonschema constraints, Redis, regulatory sandbox framing, and richer
  artifact systems.
- This spec adopts the disciplined core and defers the heavy surfaces until
  private-alpha behavior proves the loop matters.

## Refined Thesis

Argus should become the place where investing thinking becomes testable,
explainable, and durable.

Not:

- a chatbot that answers finance questions;
- a backtest calculator with chat;
- a Bloomberg-lite terminal;
- a generic research workspace;
- a brokerage or execution platform.

The durable product loop is:

```text
observe -> learn/research -> form hypothesis -> test -> explain -> refine -> remember -> monitor/share later
```

The practical private-alpha promise is:

> Bring Argus a messy investing thought. Argus helps you understand it, ground
> it at the right evidence depth, turn it into something testable when possible,
> show what happened historically, and preserve the reasoning so your thinking
> compounds over time.

## Consumer Simplicity Standard

The user must not feel the machinery behind this spec.

Argus targets broader consumers who may be financially curious but unfamiliar
with finance language, market structure, backtesting terminology, or strategy
design. The product must bridge that literacy gap with simplicity, elegance,
intuition, and speed.

The user should experience:

```text
ask naturally -> learn quickly -> test simply -> understand clearly -> come back later
```

The user should not experience:

- choosing internal lanes;
- configuring research depth by default;
- reading provider/tool explanations;
- being forced through research before a direct test;
- navigating a dashboard or terminal before the chat has earned it;
- reviewing raw strategy JSON;
- feeling like Argus turned learning into homework.

Complexity can exist internally if it keeps the experience simple. It should
not leak into the primary chat unless the user explicitly asks for more depth.

## Core Product Principle

Argus should support multiple entry speeds into the same durable idea loop.
Research is optional, not mandatory.

Users who already know what to test should stay on the fast path. Users who
need education or grounding should get help forming a testable idea. Users who
ask for deeper research should be able to spend more time and cost deliberately,
without slowing down the direct-test experience.

The internal product architecture can use lanes and evidence-depth labels, but
the user-facing experience should feel like natural pacing:

- "I can test that now."
- "Here is the simple version."
- "I found a little context and two ways to test it."
- "This is broader; I can do a deeper pass if you want."
- "I will remember this idea and tell you when something relevant changes."

## Decision Algorithm

Use this filter to keep the milestone small and fast:

1. Question every requirement against the real user goal.
2. Remove or defer anything that does not help the next private-alpha learning
   loop.
3. Simplify or optimize the requirements that remain.
4. Accelerate cycle time with the smallest observable slice.
5. Automate only the signals that protect learning speed or trust.

The practical test:

> Does this help a user move from curiosity to a supported test, a clearer
> explanation, or a remembered idea faster?

If not, defer it. If it leaks unsupported capability, remove it from the
user-facing surface.

### Default Decision Bias

- Prefer one strong loop over many half-supported surfaces.
- Prefer direct test speed over research ceremony.
- Prefer executable candidate experiments over broad strategy breadth.
- Prefer short cited context over report-like answers.
- Prefer message/job/run metadata before new durable tables, unless reload or
  audit breaks.
- Prefer hiding unsupported inventory over showing users what Argus cannot run.
- Prefer explicit user consent before slow/deep research.

## Evidence Lanes

### Lane 1: Direct Test

For users who already know what they want to test.

Example:

> Backtest AAPL vs MSFT from 2020 to today.

Behavior:

- no Perplexity call;
- no citations required;
- existing interpretation, confirmation, workflow backtest, result readout, and
  refinement path remain unchanged.

Evidence depth: `none`

### Lane 2: Education

For users asking about finance concepts, market mechanics, or investing
language.

Example:

> Explain yield curve inversion.

Behavior:

- Argus answers in beginner-friendly language;
- citations are optional unless the answer makes external/current factual
  claims;
- Argus can offer to turn the concept into one or more supported historical
  tests.

Evidence depth: `conceptual`

### Lane 3: Light Evidence

For users with a rough market idea who need quick grounding before testing.

Example:

> Are semiconductors still outperforming gold?

Behavior:

- Argus performs bounded cited research;
- summarizes only the evidence needed to form testable candidates;
- produces one to three candidate experiments;
- filters candidates through deterministic capability checks;
- only executable candidates can become confirmation cards.

Evidence depth: `light`

### Lane 4: Deep Research

For users exploring a broader thesis where deeper evidence is useful.

Example:

> I am trying to understand whether semiconductor cyclicality is changing
> because of AI capex.

Behavior:

- Argus performs deeper cited research with explicit time/cost expectations;
- may run asynchronously if latency is high;
- produces a thesis summary and candidate experiments;
- stores a durable research artifact later; in the first implementation this can
  still be message metadata if that is enough to reload and audit the turn;
- defers monitoring, shareable pages, and dashboards until later milestones.

Evidence depth: `deep`

### Lane 5: Monitoring And Inbox Later

For saved ideas that should stay alive over time.

Example:

> Tell me when something changes that affects this idea.

Behavior:

- deferred until the first evidence-to-experiment loop proves demand;
- should be tied to user-owned ideas, not generic market news;
- likely uses scheduled jobs, saved ideas, source updates, updated market data,
  and inbox-style notifications;
- must remain educational and non-advisory.

Evidence depth: `monitor`

Retention promise:

> Argus remembers what I am exploring and tells me when something relevant
> changes.

Potential future notifications:

- "Your semiconductor vs gold idea has new evidence this week."
- "The ETF you used as a proxy changed meaningfully."
- "This saved idea may be worth retesting with updated data."
- "A source related to your thesis changed; want a quick update?"
- "Your recurring-buy idea now has another month of data."

## Unified Loop Contract

All lanes converge on the same Argus-owned structure:

```text
user input
  -> interpreted intent
  -> evidence depth
  -> evidence packet when needed
  -> candidate experiments
  -> deterministic capability result
  -> confirmation card
  -> workflow-backed backtest
  -> result card
  -> explanation
  -> next experiment
  -> durable idea memory
```

The product must not fork into separate "research mode" and "backtest mode"
brains. The chat runtime remains one coherent Argus experience.

This is a loop, not a straight line. A user may enter through education,
testing, light evidence, or deep research; after a result they may ask a new
question, refine the test, save the idea, ignore the update, or return later.
Argus should preserve continuity without forcing a rigid wizard.

## Architecture Implications

### Runtime

- Add an explicit evidence-depth concept to the runtime contract.
- Do not add regex gates before LLM interpretation.
- The interpreter may infer likely lane, but Argus can ask the user when the
  evidence depth is ambiguous or expensive.
- Direct-test behavior must remain fast and unchanged.

### Providers

- OpenRouter owns conversation, interpretation, structured drafting,
  clarification, result explanation, and refinement.
- Perplexity owns fresh external research and citations when evidence depth is
  `light`, `deep`, or a current factual education answer needs sources.
- Alpaca, Kraken, and future deterministic data providers own executable market
  data availability and historical data used in simulations.
- FRED remains a structured macro provider candidate when deterministic macro
  series are needed.
- No provider decides whether a backtest is executable except Argus capability
  code.

### Backtesting Engine

The evidence-aware loop does not require the engine to become a professional
quant platform. It requires the engine to cover the simple experiment types that
normal people naturally ask for after learning or researching.

The engine roadmap should prioritize understandable tests that strengthen the
evidence-to-experiment loop:

- compare asset A vs asset B;
- compare an asset, ETF, basket, or crypto against a benchmark;
- test recurring buys over a date window;
- test buy-and-hold windows;
- test selected baskets or proxies such as "semiconductors" through supported
  ETFs or selected tickers;
- later, test event or regime windows such as inflation periods, rate cuts,
  recessions, earnings windows, or Bitcoin halvings.

Signal/indicator strategies are not the near-term product wedge. Keep them as
advanced executable tests only when they already work and the user explicitly
asks for a rule-based idea. Do not surface a discoverable indicator if Argus
cannot execute it.

This changes the engine's role from "run any strategy the user imagines" to
"maintain a library of honest, understandable experiment types." When evidence
suggests an idea, Argus must know whether it can express that idea as a fair
historical test. If it cannot, Argus should explain the gap and offer a simpler
proxy only when the proxy is not misleading.

### Data

First-class future objects may include the concepts below. They are not first
slice table requirements; start with message/job/run metadata unless reload,
audit, sharing, monitoring, or analytics prove a concrete schema is needed.

- `evidence_packet`: cited external context used for one assistant turn;
- `research_source`: normalized source/citation metadata;
- `candidate_experiment`: a proposed hypothesis and capability status;
- `idea_thread`: durable grouping of evidence, candidates, runs, and
  refinements;
- `idea_memory_link`: relationships between source evidence, confirmation card,
  backtest job, run, result readout, and next experiments.

Do not start with a giant generic artifact table unless implementation pressure
proves the concrete objects are too rigid.

### UI

- Stay chat-first.
- Direct tests should not show research ceremony.
- Evidence-backed prompts should show compact source context and candidate
  experiment cards.
- Unsupported ideas can be explained as boundaries in prose, but should not
  render as candidate experiment cards or buttons. If a card exists, it should
  point to a supported next step.
- Research-backed candidate suggestions should behave like clean, pre-baked
  prompt chips: clicking one sends a user turn in natural language, then the
  normal Argus interpretation -> confirmation card path runs. Do not create a
  hidden frontend shortcut that bypasses the chat brain or capability checks.
- Avoid a new dashboard in the first milestone.
- Hide internal labels such as `evidence_depth`, `candidate_experiment`, or
  `capability_status` from the primary user experience.
- Prefer one clear next action over many technically correct options.
- Let users ask for depth, but default to the shortest useful answer that
  preserves trust.

### Cost And Latency

- Evidence depth controls cost.
- `none` and `conceptual` should stay cheap.
- `light` should optimize for speed and candidate formation.
- `deep` can spend more time, but must be explicit and feature-gated.
- Route receipts must record provider, model, tools, latency, source count,
  candidate count, rejected candidate reasons, and cost/usage when available.

## Milestone Ladder

### Milestone 0: Spec And Product Test Design

Goal:

- Align on the vision, lanes, architecture, and learning questions.

Outputs:

- this spec;
- success/failure metrics;
- private-alpha interview/test script;
- first-slice scope and non-goals.

Locked defaults:

- **Primary learning question:** Do users find Argus more valuable when it helps
  them move from a broad investing curiosity into a concrete, testable idea?
- **Success signal:** A tester completes one loop from broad question ->
  candidate idea -> backtest/result -> follow-up/refinement, and says the flow
  helped them think better than a normal chatbot.
- **Failure signal:** Users skip evidence/research help and only use direct
  backtests, or they find candidate suggestions obvious, noisy, untrustworthy,
  or slower than asking a generic chatbot.
- **First implementation slice:** Implement Milestone 1 only. Add internal
  evidence-depth and candidate-experiment contracts with fixture-backed routing
  examples. Do not call Perplexity yet, and do not change the direct backtest
  path.
- **Private-alpha test script style:** Use both messy realistic prompts from
  normal users and finance-literate prompts from investor friends. Keep the
  first script to five to eight prompts total so the learning signal stays
  sharp.
- **First-slice non-goals:** No Perplexity provider adapter, citations UI,
  durable idea table, monitoring/inbox, public sharing, vector/semantic search,
  or new UI mode selector. Those remain later milestones unless Milestone 1
  proves they are required earlier.

### Milestone 1: Evidence-Aware Intent Contract

Goal:

- Add the concept of evidence depth and candidate experiments without changing
  the direct backtest path.

Possible implementation shape:

- internal contract/types for evidence depth;
- no Perplexity required yet;
- deterministic tests for routing/capability labels;
- fixture-backed examples of direct test, education, light evidence, and deep
  research prompts.

Learning question:

- Can Argus correctly distinguish "test this now" from "help me understand or
  form a test" without slowing direct users?

### Milestone 2: Light Evidence To Candidate Experiments

Goal:

- Use bounded cited research to turn broad market curiosity into supported
  candidate experiments.

Scope:

- feature flag;
- Perplexity provider adapter;
- compact cited evidence packet;
- one to three candidate experiments;
- capability labels: `testable_now`, `needs_clarification`, `unsupported`;
- confirmation cards only for `testable_now`.

Learning question:

- Do users value Argus more when it helps them decide what to test?

### Milestone 3: Research-Backed Backtest Loop

Goal:

- Link evidence, candidate, confirmation card, job, run, and result readout.

Scope:

- persisted source/citation metadata;
- candidate-to-run linkage;
- result card references originating evidence when helpful;
- Quick take and Explain result remain Argus-owned, not Perplexity prose.

Learning question:

- Does cited context make backtests more understandable and trustworthy, or
  does it add latency/noise?

### Milestone 4: Refinement Loop

Goal:

- Make Try next genuinely useful by generating supported next experiments.

Scope:

- next experiments are grounded in the prior result and capability contract;
- no generic investment advice;
- no unsupported next-step buttons;
- track whether users run a second experiment.

Learning question:

- Do users iterate after seeing a result?

### Milestone 5: Idea Memory

Goal:

- Let user thinking accumulate beyond isolated chat turns.

Scope:

- durable idea object or equivalent linked artifacts;
- recents/history surfaces that show prior ideas clearly;
- no public sharing yet;
- no vector memory unless a concrete retrieval gap is proven.

Learning question:

- Do users return to prior ideas, or is Argus mostly a one-shot tool?

### Milestone 6: Deep Research

Goal:

- Support deliberate, slower, source-rich research when the user asks for it.

Scope:

- explicit depth controls;
- larger source budget;
- asynchronous execution if needed;
- clear cost/latency guardrails.

Learning question:

- Do users need deeper research inside Argus, or do they prefer external
  research plus direct tests?

### Milestone 7: Monitoring And Inbox

Goal:

- Build retention by keeping selected ideas alive over time.

Scope:

- scheduled or user-triggered updates;
- inbox-style notifications;
- only updates tied to user-owned ideas;
- no generic news feed;
- educational framing;
- no brokerage or personalized recommendation behavior.

Learning question:

- Does recurring relevance drive retention without becoming noisy or
  intimidating?

### Milestone 8: Shareable Artifacts

Goal:

- Let users share sanitized, immutable snapshots once privacy and trust design
  are mature.

Scope:

- owner-only create/revoke;
- unguessable public slugs;
- no source conversation IDs, provider metadata, route receipts, or private
  retry payloads;
- no unauthenticated access to source tables.

Learning question:

- Does sharing help distribution without compromising trust or privacy?

## Early Market Test Plan

Before building the full lab, private alpha should test one core behavior:

> Do users value Argus more when it helps them decide what to test, not just run
> what they already know to test?

### Test Method

Use five to eight private-alpha prompts that mix messy consumer language and
finance-literate investor language:

- "Is semis still better than gold or am I late?"
- "Should I just buy NVDA or the chip ETF?"
- "What happens if I bought Bitcoin every week last year?"
- "I keep hearing rates are coming down. What could I test?"
- "Compare SMH vs GLD over the last two years with SPY as context."
- "Test a weekly DCA into NU over the last two years."
- "Compare equal-weight NVDA, AMD, and AVGO versus SPY since 2023."
- "Explain what sector rotation means, then suggest one testable proxy."

For each prompt, observe:

- whether the user accepts Argus's candidate experiment;
- whether they edit it;
- whether they run the backtest;
- whether they ask a follow-up;
- whether they say the candidate captured their intent;
- whether citations improved trust or felt like noise;
- whether latency was acceptable.

### Success Signals

- Users ask broad questions and accept at least one candidate experiment.
- Users run a backtest from an Argus-proposed candidate.
- Users ask follow-up/refinement questions after the result.
- Users say Argus helped them frame the idea, not merely calculate it.
- Users return to prior ideas.
- Users describe Argus as easy, approachable, or clarifying rather than
  technical.
- Users understand what Argus can and cannot test.

### Failure Signals

- Users ignore candidate experiments and only want direct backtests.
- Research/citations slow the experience without increasing trust.
- Candidate experiments feel generic or obvious.
- Users compare Argus to ChatGPT/Perplexity instead of seeing a unique loop.
- The product repeatedly suggests tests Argus cannot support.
- Users feel the flow is too much work.
- Users feel briefs or updates are generic market noise.

### Pivot Implications

If direct tests dominate, focus on expert-speed backtests, asset discovery, and
result interpretation before deeper research.

If broad questions convert into backtests, continue the evidence-aware loop.

If users like research but do not run tests, Argus may need a stronger
education/research product or clearer conversion actions.

If users want alerts and monitoring, move the inbox milestone earlier, but only
after trust and non-advice boundaries are designed.

## Questions, Answers, And Open Decisions

These are stable handles for future discussion and implementation plans:

- `P` = Product
- `L` = Lane / flow
- `C` = Capability
- `E` = Evidence and sources
- `D` = Data / persistence
- `UX` = Experience
- `R` = Retention
- `T` = Trust and compliance
- `CP` = Cost and performance
- `EV` = Evaluation
- `O` = Operations

Each question keeps its current answer directly underneath it. If a question is
not fully settled, the remaining ambiguity is called out immediately.

### Product Questions

- **P1. What makes a broader consumer feel safe asking a naive finance
  question?**

  **Answer:** A simple, non-judgmental chat surface; plain-language responses;
  explicit assumptions; no advice-y language; and supported actions that do not
  make users feel they need to know finance jargon before participating.

- **P2. What is the minimum delightful moment: learning something, getting a
  good test suggestion, seeing a result, or returning to a remembered idea?**

  **Answer:** The first delightful moment is not merely "Argus ran a backtest."
  It is "Argus helped me decide what to test, then closed the loop with a
  result." A complete result means the user got what they needed through any
  flexible lane: direct test, education, light evidence, or later deeper
  research.

- **P3. Should the first evidence-aware loop optimize for curious beginners,
  enthusiasts, or finance-literate private-alpha users while still preserving
  consumer simplicity?**

  **Answer:** Optimize for broader consumer simplicity while letting
  finance-literate users move quickly. The first loop should not fork Argus into
  an expert mode. It should keep direct tests fast and make broad questions
  approachable.

- **P4. Should Argus name this surface at all, or should the loop simply feel
  like better chat?**

  **Answer:** Do not name a new surface yet. The first version should feel like
  better chat, not a new dashboard or mode. The durable Research Lab thesis can
  remain a strategic direction until the loop earns a visible product label.

- **P5. What should Argus never optimize for, even if it increases engagement?**

  **Answer:** Do not optimize for advice, hype, trading-terminal complexity,
  generic market-news consumption, provider plumbing, addictive notifications,
  or broad chatbot behavior that does not help users understand and test ideas.

### Lane Questions

- **L1. How much of lane selection should be invisible and automatic?**

  **Answer:** Mostly invisible. The chat brain stays LangGraph; normal language
  reaches LLM interpretation first, then deterministic validation/capability
  checks. Do not add regex gates, a second chat orchestrator, or visible internal
  lanes.

- **L2. When should Argus ask the user before spending more time on research?**

  **Answer:** Direct executable tests stay direct. Argus should ask or expose a
  visible control only when the user wants external/current evidence, broader
  research, or a slower/deeper pass.

- **L3. What user-facing words feel simple: "quick context", "deeper look",
  "test this", "remember this"?**

  **Answer:** For the first slice, prefer one polished composer control:
  **Search**. It is clear enough for users, maps cleanly to cited evidence, and
  avoids forcing an "instant vs expert" model onto Argus. "Deep research" is a
  later explicit mode/preset once users prove they want slower source-rich work.
  The control should teach itself through progressive disclosure: concise
  tooltip copy, accessible label, and first-use empty-state/examples. It should
  not require an onboarding modal for users to understand that Search means
  "use outside evidence before helping me understand or test this."

- **L4. When should an education answer offer a test without making learning
  feel transactional?**

  **Answer:** Offer a test only when the concept naturally maps to a supported
  historical experiment. The offer should feel like "want to see this in
  history?" rather than "now run a backtest."

- **L5. How does a user bypass research and go straight to testing?**

  **Answer:** By asking for a direct test as they do today. The evidence loop
  must not require Perplexity/research when the user already gives a ticker,
  strategy, dates, and assumptions.

### Capability Questions

- **C1. Which strategy templates are eligible for candidate experiments first:
  buy-and-hold, recurring buys/DCA, signal/indicator strategies, or all current
  supported templates?**

  **Answer:** Candidate experiments start with executable launch strategy types:
  `buy_and_hold`, `dca_accumulation`, `indicator_threshold`, and
  `signal_strategy`. Broader template names should not be advertised as runnable
  unless the capability contract maps them into one of these executable paths.

- **C2. Which simple experiment types should the backtesting engine support next
  to make research-derived ideas useful?**

  **Answer:** Preserve everything Argus already does: single ticker vs
  benchmark, equal-weight multi-symbol sets vs benchmark, buy-and-hold, DCA,
  indicator-threshold, and signal-strategy runs. The next expansion should
  enrich comparison/proxy work without regressing those paths: stock vs ETF, ETF
  vs ETF, selected basket vs benchmark, and thesis-to-explicit-proxy candidates.
  DCA cadence supports daily, weekly, biweekly, monthly, and quarterly. Locked
  v1 scope: ETF/stock/basket vs benchmark and ETF vs ETF. Defer winner/loser
  scans because they are more advice-adjacent and need stronger boundaries.

- **C2a. Which asset and indicator universe should users see?**

  **Answer:** Current launch requests support `equity`, `crypto`, and
  `currency_pair`, with same-asset-class runs only and max five symbols per run.
  Executable indicators are RSI, SMA, EMA, MACD, and Bollinger Bands. ATR, VWAP,
  OBV, and stochastic currently exist as catalog/discovery inventory but are not
  executable strategy triggers. Hide non-executable indicators from user-facing
  discovery until they either become executable or are removed.

- **C2b. What provider and benchmark defaults are already canonical?**

  **Answer:** Alpaca is primary for equity and crypto availability; Kraken
  complements crypto and currency-pair coverage. Alpha benchmark defaults are
  `SPY` for equities, `BTC` for crypto, and the tested pair itself for currency
  pairs.

- **C3. Which natural consumer prompts are currently impossible because the
  engine lacks event windows, baskets/proxies, or comparison primitives?**

  **Answer:** Mixed asset-class runs, personalized portfolio advice, real-money
  trading, unsupported indicators, broad sectors without explicit tickers/ETFs,
  event-window questions, complex baskets/proxies, macro-causal claims, and deep
  research claims are outside the current execution contract. Cohesive
  expansions that fit the proposed vision are comparison primitives, explicit
  ETF/ticker proxy mapping, selected baskets within one asset class, and later
  event/regime windows.

- **C4. How should Argus handle ideas that are meaningful but not currently
  testable?**

  **Answer:** Explain the boundary in product language or map to a supported
  adjacent experiment. Do not hide engine failures and do not create
  runnable-looking cards for unsupported work.

- **C5. How should unsupported ideas be explained, hidden, or mapped to
  supported alternatives without making them look runnable?**

  **Answer:** The LLM brain may map a broad thesis to capability-adjacent
  candidates, but deterministic capability code must filter the result.
  Candidate prompt chips are generated by the LLM, then validated before they
  are shown. If a generated chip does not map to a reasonably executable
  configuration, Argus should ask the LLM/tooling layer to repair or replace it
  before display. Unsupported ideas may become educational prose or clearly
  labeled supported proxies, not runnable candidate actions.

- **C6. How should Argus represent proxy tests, for example "luxury stocks"
  requiring selected tickers or ETFs?**

  **Answer:** Proxy tests must name the selected instruments, explain that they
  are proxies, and pass the same asset-class, symbol, date, timeframe, and
  benchmark validation as any other run. For v1, prefer transparent ETF/ticker
  proxies over opaque baskets.

- **C7. What is the line between a supported experiment and a misleading
  proxy?**

  **Answer:** A proxy is supportable only when Argus names the instruments,
  states the assumption plainly, avoids causal claims, keeps the action inside
  current engine constraints, and lets the user edit or reject the proxy before
  running it.

### Evidence And Source Questions

- **E1. Which Perplexity tools are reliable enough for stocks, ETFs, crypto,
  currency pairs, macro, sectors, and companies?**

  **Answer:** First slice should prefer `web_search` and `finance_search` for
  market/company/ETF questions and use `fetch_url` only when Argus needs a known
  source. People search is not a general "search anyone" feature for Argus; it
  should only be considered when the person is finance-relevant to the user's
  thesis, such as an executive, policymaker, fund manager, analyst, or named
  source connected to a market claim. Perplexity's Agent API can return
  searched/fetched result items and financial result items before the final
  assistant text; Argus should use those structured outputs as source truth
  rather than trusting model-authored URLs inside prose.

- **E2. What is the shortest evidence payload that increases trust without
  making the chat feel like a report?**

  **Answer:** Compact context only: two to four cited bullets or a short
  paragraph, followed by one to three executable candidate experiments. The goal
  is to form a testable idea, not produce a research memo.

- **E3. When does a citation help a beginner, and when does it create clutter?**

  **Answer:** Citations help when Argus makes current/external factual claims.
  They create clutter when attached to engine-generated metrics, obvious product
  assumptions, or every sentence. Keep citations compact and scannable.

- **E4. Should Argus use domain allowlists for some question types?**

  **Answer:** Do not ship a heavy source-governance system in v1. Perplexity
  supports domain/date/recency/location filters on `web_search`, so Argus can
  add source controls later if quality issues show up. The first slice should
  record the domains/sources used and keep provider knobs internal.

- **E5. How should Argus show source freshness in plain language?**

  **Answer:** Do not add noisy freshness labels to every citation. Modern AI
  answers usually cite factual claims inline and expose source metadata when the
  user inspects the citation. If the user explicitly asks for recent news or a
  time-bounded search, Argus should pass the right Perplexity recency/date
  filters and mention the time boundary in the answer.

- **E6. How should Argus handle conflicting sources?**

  **Answer:** State uncertainty, avoid unsupported causality, and avoid creating
  a confident runnable candidate from disputed facts unless the test is framed
  as a proxy or hypothesis. The route receipt should preserve enough source
  metadata to debug why Argus chose that boundary.

- **E7. What claims require citations, and what claims can be labeled as
  assumptions?**

  **Answer:** Engine-generated simulation metrics do not need external citations
  because they come from `backtest_runs`. Current market, company, macro, news,
  person, or sector claims need source grounding. Proxy mappings and test
  simplifications should be labeled as assumptions.

### Data Questions

- **D1. What is the smallest durable "idea object" that creates continuity?**

  **Answer:** For the first slice, avoid a new table. The smallest durable unit
  is an assistant message with structured metadata that includes the evidence
  packet, candidate experiment, selected proxy if any, capability result, and
  linked job/run IDs when executed.

- **D2. What should Argus remember that feels useful, not creepy or noisy?**

  **Answer:** Memory is the long-term product moat, but v1 should only remember
  where the product loop is cohesive. Store conversation-scoped memory around
  user-owned ideas, evidence packets, candidate experiments, runs, refinements,
  and explicit saved/monitored topics. Do not introduce hidden personalization,
  inferred sensitive preferences, or broad user profiling before the idea loop
  proves value.

- **D3. Do we store research artifacts as concrete tables or message metadata
  first?**

  **Answer:** Message metadata first. This is an implementation tactic, not the
  user experience. Users still see polished evidence, candidate, and result
  surfaces. Create concrete evidence/candidate tables only when reload, audit,
  sharing, monitoring, or analytics prove metadata is insufficient. The v1 SOTA
  tradeoff is speed with discipline: store a compact, typed JSON metadata
  envelope on the assistant message, validate its shape in code, and index or
  extract later only after a real query/reload/analytics need appears.

- **D4. What citation fields are required for reload, audit, monitoring, and
  future sharing?**

  **Answer:** First slice should store enough to reload and audit: source title,
  URL, domain, retrieved timestamp, Argus-authored cited-claim summary,
  provider/tool metadata, and a stable source ID. Provider response metadata
  should be normalized from actual Perplexity outputs where available: response
  id, model or preset used, tool type, query, result id, result URL, title,
  source, published date, last-updated date, finance result category/ticker when
  present, token usage, and tool invocation counts. Do not persist full fetched
  page content or long snippets as normal conversation memory. Future public
  sharing may require a stricter sanitized snapshot.

- **D5. How long should research source snapshots live?**

  **Answer:** Citation references and compact source snapshots should persist
  with the conversation so old chats can reload with the same grounded links and
  context. This is closer to modern AI chat citation behavior: the link/source
  reference remains attached to the answer unless the conversation is deleted.
  V1 snapshots are conversation memory, not a broad reusable evidence cache.
  Revisit independent retention only for monitoring, public sharing, or a later
  reusable research cache.

- **D6. Do source snippets create copyright or privacy risk?**

  **Answer:** Persistent citation links are not the problem; they should remain
  attached to the chat. The risk is storing long verbatim external excerpts or
  full fetched page contents in Argus-owned tables. First slice should store
  source metadata, links, retrieved timestamps, and Argus-authored compact claim
  summaries. Avoid long copied snippets until copyright, privacy, and public
  sharing rules are reviewed.

- **D7. How should an idea object link to multiple runs and refinements?**

  **Answer:** Today, runs link through conversation/message/job metadata and
  `backtest_runs`. A future idea object should link to messages, candidate
  experiments, jobs, runs, and refinements rather than reconstructing state from
  frontend prose.

- **D8. Should research artifacts be immutable snapshots or regenerable drafts?**

  **Answer:** Evidence that justifies a candidate, monitoring alert, or shared
  artifact should be immutable snapshot truth. Drafts can be regenerable until
  they are used to create a runnable candidate or public/shareable artifact.

### UX Questions

- **UX1. How can Argus hide complexity while preserving trust?**

  **Answer:** Show product-level controls and assumptions, not provider
  mechanics. The user sees Search, candidate cards, confirmation cards, result
  cards, and clear boundaries; the system hides tools, models, and routing.

- **UX2. What does a candidate experiment card look like compared with a
  confirmation card?**

  **Answer:** Reuse the confirmation/artifact lifecycle. Candidate cards should
  feel like polished Argus cards with clear assumptions and edit/run actions,
  not a separate research-card system.

- **UX3. How do we avoid clutter when showing evidence, citations, candidates,
  and backtest results in one chat?**

  **Answer:** Keep evidence compact, show only executable candidates as cards,
  and let the result card remain the dominant artifact after execution. Avoid
  stacking research memo, candidate, confirmation, queue, result, and breakdown
  as competing surfaces.

- **UX4. Should "Try next" show as chips, cards, or a dedicated follow-up
  section?**

  **Answer:** The current private-alpha branch does not expose visible Try next
  chips, cards, or dedicated result sections. It keeps normal typed follow-ups
  and the result-card Refine idea action while Milestone 4 defines whether
  supported next experiments should return as chips, cards, or another approved
  surface. If restored, they must stay grounded in the prior result and
  capability contract, and must not duplicate Quick take or become generic
  advice.

- **UX5. How do we make unsupported boundaries feel helpful rather than
  frustrating?**

  **Answer:** Use product-language boundaries plus supported alternatives.
  Example shape: "I cannot test that exact causal claim, but I can compare these
  explicit proxies historically."

- **UX6. How should Spanish-language users experience citations and source
  language?**

  **Answer:** Static UI supports English and Spanish Latin America (`en`,
  `en-US`, `es-419`). AI responses should respect the user's language
  preference. V1 should not translate source titles or quoted source metadata
  unless the provider returns translated metadata; Argus can summarize the cited
  claim in the user's language.

### Retention Questions

- **R1. What makes a user come back tomorrow?**

  **Answer:** Deferred beyond the first evidence slice. Current thesis: users
  return when Argus remembers an idea and helps them continue it, retest it, or
  notice relevant changes without becoming a generic news feed.

- **R2. What is the user expected to do after a brief: read, test, refine, save,
  ignore, or mute?**

  **Answer:** Deferred until briefs/inbox exist. Bias toward read ->
  test/refine/save, with ignore/mute as trust-preserving controls.

- **R3. How often is helpful: daily, weekly, event-triggered, or user-triggered?**

  **Answer:** Deferred. Monitoring and inbox should not be built until users
  prove they return to ideas.

- **R4. What kinds of changes are meaningful enough to interrupt someone?**

  **Answer:** Deferred until monitoring is designed. Likely only changes tied to
  explicit saved ideas, source updates, or enough new data to retest.

- **R5. How does Argus avoid becoming a news feed?**

  **Answer:** Only notify around user-owned ideas and explicit saved hypotheses.
  Do not ship generic daily market news as the retention mechanic.

- **R6. What does progress look like for a beginner learning finance?**

  **Answer:** Deferred as a retention/learning design question. Likely progress
  is repeated conversion from naive question to understandable concept,
  supported test, result, and refinement.

- **R7. How should Argus let users pause, mute, or retire an idea?**

  **Answer:** Deferred. Must be designed before monitoring/inbox.

### Trust And Compliance Questions

- **T1. What exact no-advice language belongs on research cards versus result
  cards?**

  **Answer:** Research and result cards should preserve the current educational
  boundary: historical context, assumptions, and no financial advice. Exact copy
  is still implementation-level work.

- **T2. Should Argus avoid words like "recommend", "should buy", and "best" in
  all research-to-test surfaces?**

  **Answer:** Yes. Argus can suggest supported historical tests and explain
  tradeoffs; it should not recommend investments.

- **T3. What logs or artifacts must exist to audit a disputed answer?**

  **Answer:** Persisted messages, structured metadata, `backtest_jobs`,
  `backtest_runs`, route receipts, workflow run IDs, result readout provenance,
  failure codes, timing metadata, fallback flags, evidence source IDs, and
  provider/tool metadata.

- **T4. When does a cited answer become too close to personalized advice?**

  **Answer:** When Argus tells the user what to buy/sell/hold, ranks choices as
  best for them, or turns evidence into a personalized recommendation. It should
  frame historical tests, assumptions, and tradeoffs instead.

- **T5. What additional review is needed before public sharing or monitoring?**

  **Answer:** Public excerpts require separate privacy/revocation/auth and
  sanitization design. Monitoring requires non-advice copy, mute/retire controls,
  and review of what kinds of changes are allowed to interrupt a user.

### Cost And Performance Questions

- **CP1. What is the acceptable cost per `light` evidence turn?**

  **Answer:** Do not let cost define the product prematurely. Founder controls
  cost for now. First pass should optimize for value and learning while keeping
  depth controlled by explicit product choices.

- **CP2. What is the acceptable cost per `deep` research turn?**

  **Answer:** Deep research is deferred and must be explicitly user-chosen. Cost
  can become a monetization/control surface later.

- **CP3. What latency is acceptable before we need async jobs?**

  **Answer:** Latency should be acceptable in the first pass; optimize later.
  Long-running or variable-latency work should cross a durable job boundary if
  it cannot reliably complete inside the chat turn.

- **CP4. What quotas should apply per user/day in private alpha?**

  **Answer:** Mirror Argus's existing usage-counter style instead of adding a
  new quota system. Initial private-alpha defaults should be conservative but
  value-preserving: `Search` light-evidence turns capped per user by hour/day,
  with global backpressure for concurrent evidence jobs if they become async.
  Proposed starting point: 5 Search turns/hour/user, 20 Search turns/day/user,
  2 in-flight evidence jobs/user, and 10 in-flight evidence jobs globally.
  These should be feature-flagged and environment-configurable.

- **CP5. Which provider calls can be cached safely without stale or misleading
  output?**

  **Answer:** Cache aggressively where safe and explicit. Market-data/provider
  catalog caches are acceptable with keys, freshness, and invalidation. Evidence
  retrieval should be fresh by default because source claims can age or become
  misleading. Argus should still persist conversation-scoped source metadata and
  claim summaries so the chat can continue naturally. That is memory, not a
  global stale evidence cache.

- **CP6. What telemetry is enough before adding PostHog or a custom event
  pipeline?**

  **Answer:** Route receipts, service logs, Supabase rows, workflow metadata,
  and canary output are enough for the next stage. Product analytics can be
  added later when the loop is clearer.

### Evaluation Questions

- **EV1. What are the first 20 golden prompts?**

  **Answer:** Use an LLM/Jules to draft messy human-style prompts, then have
  Argus/code review curate them. Do not rely only on clean synthetic prompts.
  The set should include direct backtests, broad evidence-to-candidate prompts,
  education-to-test prompts, unsupported boundary prompts, Spanish prompts,
  provider failure/fallback cases, and at least one proxy-comparison prompt.

- **EV2. What constitutes a good candidate experiment?**

  **Answer:** It is executable by the capability contract, uses supported
  assets/indicators/dates, preserves user intent, states assumptions clearly,
  avoids unsupported causality, and produces a runnable confirmation card.

- **EV3. How do we measure whether the user felt less intimidated?**

  **Answer:** Start with session notes, private-alpha interviews, and a small
  set of observed loop-completion signals before adding analytics complexity.
  A later lightweight in-product micro-question can ask whether a specific
  action helped, similar to short contextual feedback prompts in modern chat
  products. Do not add a telemetry lab before the core product loop exists.

- **EV4. How do we test that citations support claims without overbuilding an
  eval framework?**

  **Answer:** Start with deterministic golden prompts and canaries that inspect
  structured metadata: cited claims, source count, supported candidate shape,
  direct-test preservation, and route receipts. Evaluate external tools only if
  they speed development without workflow drag.

- **EV5. When should we introduce LLM-as-judge?**

  **Answer:** Later, after Argus has human-approved examples of good voice and
  candidate quality.

- **EV6. Should OpenAI be the future independent judge provider?**

  **Answer:** Likely yes for a later optional eval path because it separates the
  evaluator from the OpenRouter runtime path. Do not make it a milestone hard
  gate yet.

- **EV7. What acceptance gate proves the feature did not regress direct
  backtests?**

  **Answer:** Acceptance must include at least one direct backtest canary, one
  async workflow-backed result, persisted messages/jobs/runs, and result readout
  provenance that proves the normal Argus result path was used.

### Operational Questions

- **O1. Which feature flags gate the lanes?**

  **Answer:** Existing flags gate strategies, collections, exploratory
  suggestions, onboarding, context packets, and backtest workflow modes.
  Dedicated evidence/research flags do not exist yet and should be added before
  enabling research lanes.

- **O2. How does the canary test direct mode, light evidence mode, and provider
  fallback?**

  **Answer:** Current Render canary covers the direct chat/backtest loop and
  async workflow result path. It does not yet cover light evidence mode, deep
  evidence mode, or evidence-provider fallback.

- **O3. What route receipts are required to debug research failures?**

  **Answer:** Request ID, lane/depth, provider/tool/model, latency, cache hit or
  miss if applicable, citations/source IDs when present, fallback reason,
  surfaced user message, and linked conversation/message/job/run IDs.

- **O4. How do we distinguish provider outage from unsupported idea?**

  **Answer:** Unsupported ideas should resolve to capability/failure codes.
  Provider outages should resolve to provider or upstream failure codes. These
  need different user copy and retry behavior. The first implementation should
  rely on Perplexity's built-in model fallback chain for evidence/research
  availability, record which model/preset actually answered, and fail
  gracefully if the chain exhausts. Do not add Tavily or OpenRouter web-search
  fallback in the first slice unless Perplexity failure becomes a repeated
  blocker. If evidence fails, Argus can continue conceptually or offer a direct
  supported test, but it must not fabricate citations.

- **O5. What must be visible in Supabase after a successful evidence-backed
  test?**

  **Answer:** Persisted conversation/message records, evidence metadata, durable
  job row if async work was used, linked `backtest_run` if executed, and enough
  route metadata to audit the path.

### Perplexity Control Surface Notes

The product should expose simple controls while the backend maps them to
Perplexity parameters and presets:

- **No visible control:** direct tests and simple conceptual answers stay fast.
- **Search:** first visible composer control. Use it for current facts, broad
  evidence, citations, and research-backed candidate experiments. Candidate
  backend shape: `fast-search` or a low/medium `web_search` budget.
- **Deeper research:** deferred explicit slower pass. Candidate backend shape:
  `pro-search` or `deep-research`, higher `max_steps`, larger search context,
  and `fetch_url` for important sources.

External AI apps often separate speed, reasoning, and web-search controls. That
is useful inspiration, but Argus should not copy a generic "instant vs expert"
mode switch. Argus's first control should be product-specific: **Search** means
"ground this with outside evidence before helping me test or understand it."
Recommended first tooltip/accessibility copy: "Search current sources before
answering." Empty-state examples should show the behavior through concrete
prompts instead of explaining the architecture.

Perplexity Agent API supports:

- presets such as `fast-search`, `pro-search`, `deep-research`, and
  `advanced-deep-research`;
- model/tool overrides, `max_steps`, `max_output_tokens`, reasoning controls,
  and tool selection;
- `web_search` with `search_context_size`, domain/date/recency/location filters,
  and explicit token budgets;
- `fetch_url` for known URLs, bounded by `max_urls`;
- `finance_search` for structured public-equity and ETF data, including quotes,
  financials, earnings, peers, analyst coverage, ownership, corporate actions,
  and ETF/index constituents.

Argus should turn these into a small number of product presets instead of
exposing raw API knobs to users.

### Evidence Search Configuration

Use explicit, config-driven names so implementation agents do not invent a new
contract:

- `PERPLEXITY_API_KEY`: secret backend key, already expected in local env.
- `[removed obsolete setting]=false`: frontend gate for the composer
  `Search` control.
- `[removed obsolete setting]=false`: backend gate for evidence-search
  execution.
- `[removed obsolete setting]=25`: first-pass chat-turn timeout.
- `[removed obsolete setting]=low`: default web-search context size for
  light evidence.
- `[removed obsolete setting]=1200`: bound answer/candidate
  verbosity.
- `[removed obsolete setting]=3`: never show more than three
  candidate chips in v1.
- `[removed obsolete setting]=openai/gpt-5.4-nano,google/gemini-3.1-flash-lite,perplexity/sonar,nvidia/nemotron-3-super-120b-a12b,xai/grok-4.3`:
  ordered Perplexity Agent API model fallback chain.
- `[removed obsolete setting]=5` and
  `[removed obsolete setting]=20`: initial private-alpha per-user
  limits.

These defaults are intentionally modest. If Search latency or reasoning quality
is weak, adjust prompts and Perplexity parameters first, then revisit model
choice. Do not add OpenRouter web-search fallback or Tavily until Perplexity
failure becomes a repeated blocker.

### Suggested Perplexity Preset Roadmap

Official Perplexity docs support a staged roadmap because presets already bundle
model, search configuration, max steps, system prompt, and tools, while allowing
parameter overrides when Argus needs tighter control.

Implementation agents must re-check the current official Perplexity docs before
coding against these APIs. The links below anchor product direction; they are
not a frozen API schema.

Docs reviewed for this roadmap:

- Perplexity Agent API presets:
  `https://docs.perplexity.ai/docs/agent-api/presets`
- Perplexity Agent API web search:
  `https://docs.perplexity.ai/docs/agent-api/tools/web-search`
- Perplexity Agent API finance search:
  `https://docs.perplexity.ai/docs/agent-api/tools/finance-search`
- Perplexity Agent API fetch URL:
  `https://docs.perplexity.ai/docs/agent-api/tools/fetch-url-content`
- Perplexity Agent API people search:
  `https://docs.perplexity.ai/docs/agent-api/tools/people-search`
- Perplexity Agent API model fallback:
  `https://docs.perplexity.ai/docs/agent-api/model-fallback`

1. **Argus Search v1: light evidence**
   - Product control: `Search`.
   - Backend shape: explicit Perplexity Agent API request using the configured
     `models` fallback chain, `web_search` with `search_context_size="low"`,
     and `finance_search` for public-equity/ETF data.
   - Tool scope: `web_search`, `finance_search`.
   - Availability shape: Perplexity `models` fallback chain:
     `openai/gpt-5.4-nano`, `google/gemini-3.1-flash-lite`,
     `perplexity/sonar`, `nvidia/nemotron-3-super-120b-a12b`,
     `xai/grok-4.3`.
   - Use when: user asks a broad market/company/ETF question, recent context,
     or wants citations before turning the idea into a candidate experiment.
   - Output: compact cited context and one to three executable candidate
     experiments.

2. **Argus Search v1.5: bounded richer evidence**
   - Product control: still `Search`; no new UI mode yet.
   - Backend shape: dynamic `pro-search` or explicit `web_search` with
     `search_context_size="medium"` when the first pass needs more source
     coverage.
   - Tool scope: `web_search`, `finance_search`, `fetch_url` only for known URLs
     or important cited sources.
   - Use when: cross-company/ETF context, sector proxy selection, or a source
     needs direct reading.

3. **Argus Deep Research later**
   - Product control: explicit `Deep research` or monetized higher-depth choice.
   - Backend shape: `deep-research`, higher `max_steps`, larger search context,
     and bounded `fetch_url`.
   - Tool scope: `web_search`, `finance_search`, `fetch_url`; `people_search`
     only for finance-relevant professionals tied to the user's thesis.
   - Use when: user deliberately asks for slower, source-rich research.

4. **Frozen configs only when needed**
   - The explicit v1 model chain is the default because Argus wants predictable
     fallback behavior and cross-provider redundancy.
   - Dynamic presets remain useful for experimentation because Perplexity keeps
     the same rough cost/latency band while improving quality.
   - Use frozen configurations only for eval reproducibility, regulatory/change
     control, or when preset drift starts affecting Argus behavior.

5. **Future monetization/control path**
   - Free/basic: direct tests plus limited `Search` turns.
   - Paid/pro: higher Search quotas, richer `pro-search` budget, and more
     source coverage.
   - Deep: explicit deep-research runs with higher limits and async execution.

### Explicitly Deferred Or Removed For This Milestone

- **Non-executable indicator discovery:** hide from user-facing discovery. Either
  implement execution later or remove the inventory.
- **Mixed-asset backtests:** defer until benchmark/allocation semantics are
  designed.
- **Personalized portfolio advice and real-money trading:** remove from product
  scope.
- **Public sharing:** defer until privacy, revocation, and sanitization are
  designed.
- **Daily briefs/inbox:** defer until users prove they return to ideas.
- **Deep research by default:** defer. Users must explicitly choose slower/deeper
  work.
- **New durable research schema:** defer until message/job/run metadata proves
  insufficient.
- **LLM-as-judge:** defer until Argus has human-approved examples of good voice
  and candidate quality.
- **Vector/embedding semantic search:** defer until provider-backed discovery or
  text search fails a concrete user workflow.

### Clarified Ambiguities

- "Unsupported candidate" no longer means a visible disabled card by default.
  It means a prose boundary or a supported alternative. Runnable-looking cards
  are only for supported next steps.
- "Signal strategy" is not the core research-lab wedge. It remains an advanced
  executable path when explicitly requested.
- "Research Lab" is not a new dashboard or mode in the next milestone. It is a
  better chat loop: evidence-aware answer, supported candidate, confirmation,
  backtest, result, refinement.
- Perplexity does not own Argus voice or final result prose. It supplies cited
  context. Argus owns interpretation, capability mapping, execution, and result
  explanation.
- The next implementation should prove one loop, not build the whole ladder.
- Persistent citations and copied source text are different. Argus should keep
  citations, source metadata, and compact claim summaries with the conversation;
  it should not persist long verbatim source excerpts as normal product memory.
- Conversation memory and personalization are different. V1 memory means
  durable context around this idea loop, not a hidden profile of the user.
- Evidence cache and Argus memory are different. Provider/catalog caches can be
  reused when freshness is explicit; evidence claims should be freshly retrieved
  by default while their conversation-specific citations remain durable.
- Research-backed candidate chips are not execution shortcuts. They are
  LLM-generated natural-language prompts that are prevalidated against Argus
  capabilities before display. If prevalidation rejects a chip, Argus repairs or
  replaces it before the user sees it. Clicking a chip sends a normal user turn,
  then Argus re-enters the existing interpretation and confirmation-card
  lifecycle and validates again before execution.
- Perplexity model fallback is an availability/reasoning aid for evidence work,
  not a replacement for OpenRouter-owned Argus voice or backtest result
  explanation.

## Current Non-Decisions

These are intentionally not decided yet:

- exact environment variable names, timeouts, and implementation types for the
  deeper Perplexity milestones beyond Search v1;
- exact schema for research artifacts, if message metadata proves insufficient;
- whether deep research later runs inline or through Render Workflows;
- which later milestone should revisit public sharing after privacy and
  revocation design exists;
- whether pg_jsonschema is worth adding now;
- whether a future reusable research cache belongs in Supabase only or also in
  another service, after repeated-evidence workflows prove the need;
- when PostHog becomes worth adding after route receipts and canaries are
  insufficient.

## Guardrails

- Keep the user-facing experience simple, elegant, intuitive, and fast.
- Hide internal architecture from the user.
- Do not force research before direct backtests.
- Do not implement a second chat brain.
- Do not add regex NLU gates before interpretation.
- Do not let Perplexity produce final backtest result prose.
- Do not show unsupported ideas as runnable actions.
- Do not turn daily briefs into a generic news feed.
- Do not add vector search/RAG until a specific retrieval failure is proven.
- Do not add public sharing before privacy, revocation, and artifact sanitation
  are designed.
- Do not make provider/model names user-facing unless they are source metadata.
- Preserve existing benchmark comparison behavior: single ticker vs benchmark
  and equal-weight multi-symbol sets vs benchmark must not regress.

## Next Spec Step

The next step is an implementation plan for **Milestone 1 only** using the
locked decisions above. Milestone 2 remains design context, but agents should
not wire Perplexity, citations UI, durable idea tables, or research jobs until
Milestone 1 proves Argus can preserve direct backtests while recognizing
evidence-seeking turns.

1. evidence-depth contract with direct-test bypass preserved;
2. candidate-experiment contract for comparison/proxy-first tests, represented
   in fixtures only;
3. direct-test, education, light-evidence, and deep-research routing examples
   without provider calls;
4. unsupported-boundary copy and capability filtering;
5. private-alpha test script focused on broad question -> candidate -> run;
6. feature flags, route receipts, and canary requirements;
7. golden prompt harness for direct tests plus first evidence-aware examples.

Milestone 2 starts only after Milestone 1 shows that direct users are not slowed
down and broad-question users can be routed toward supported candidate
experiments without frontend shortcuts or unsupported runnable-looking cards.

The next natural product-design discussion should focus on card copy and
interaction details for the locked v1 comparison/proxy scope:

1. stock, ETF, or explicit basket vs benchmark;
2. ETF vs ETF;
3. no winner/loser scans in v1.
