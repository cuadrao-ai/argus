# Argus Research Lab Thesis

**Status:** Historical thesis draft, refined by
`docs/specs/evidence-aware-idea-loop.md`.
**Branch:** `codex/private-alpha-conversation-trust`
**Last updated:** June 9, 2026

This is not an implementation plan for the current conversation-trust milestone.
It preserves the product direction that emerged during private-alpha hardening so
future work does not accidentally reduce Argus to "chat plus a calculator."
The active refined direction is the evidence-aware idea loop, which keeps
research optional and supports direct testing, education, light evidence, and
deep research as separate lanes into the same durable idea loop.

## Thesis

Argus should become a simplified investing research lab where a person's market
thinking accumulates over time.

The durable product loop is:

1. observe or ask a broad finance question;
2. research with citations;
3. extract supported, testable hypotheses;
4. run historical simulations through existing Argus backtest paths;
5. explain what happened, including assumptions and limits;
6. compare or refine the idea;
7. optionally monitor it later through inbox-style updates;
8. share a readable artifact when useful.

Buy-and-hold, DCA, and signal/indicator strategies remain important, but they
become executable test types inside a broader evidence layer. The product is not
"a strategy builder with chat"; it is a place where investing ideas become
grounded, testable, reusable, and inspectable.

## Why Perplexity Is A Candidate

Perplexity's Agent API is a candidate research provider, not a replacement for
the Argus runtime. The official docs describe the Agent API as a multi-provider
interface with model access, real-time web search, tool configuration,
reasoning/token controls, and a unified endpoint at
`POST https://api.perplexity.ai/v1/agent`.

Relevant docs:

- [Agent API quickstart](https://docs.perplexity.ai/docs/agent-api/quickstart)
- [Presets](https://docs.perplexity.ai/docs/agent-api/presets)
- [Finance Search](https://docs.perplexity.ai/docs/agent-api/tools/finance-search)
- [Web Search](https://docs.perplexity.ai/docs/agent-api/tools/web-search)
- [People Search](https://docs.perplexity.ai/docs/agent-api/tools/people-search)
- [Fetch URL Content](https://docs.perplexity.ai/docs/agent-api/tools/fetch-url-content)
- [Prompt Guide](https://docs.perplexity.ai/docs/agent-api/prompt-guide)

## Provider Ownership

OpenRouter remains the conversational runtime provider for Argus voice,
interpretation, result readouts, and normal chat behavior unless a later canon
decision changes that.

Perplexity is a research and citation provider. It should answer external,
current, source-grounded research tasks and return structured evidence packets.
It must not become the source of truth for simulation results, backtest metrics,
or Argus result prose.

Alpaca, Kraken, and any future market-data providers remain the source of truth
for executable market data availability and historical data used by the backtest
engine.

FRED remains a curated macro-data provider candidate when deterministic,
low-cost, or structured macro series matter. Perplexity may cite macro context,
but it should not silently replace deterministic series where Argus owns a
structured provider.

Supabase owns durable research artifacts, hypotheses, citation snapshots,
source metadata, saved ideas, inbox jobs, and user state.

Render Workflows or another execution plane should own slow research jobs only
when latency, quotas, or tool-call duration make inline API execution unsafe.

## First Buildable Slice: Research-To-Test Bridge

The first implementation milestone should stay narrow:

1. User asks a broad finance question, for example "is the semiconductor
   industry outperforming gold?"
2. Argus classifies it as a research-to-test opportunity through the existing
   LLM-first interpretation path. Do not add regex gates.
3. Argus calls a bounded research task through Perplexity.
4. The research task returns cited findings plus structured candidate
   hypotheses.
5. Argus filters candidates through the existing capability contract:
   supported assets, same-asset constraints, max symbol limits, supported
   strategies, supported indicators, date windows, and available providers.
6. The UI presents cited research and only the test ideas Argus can actually
   execute.
7. Selecting a test idea produces the normal confirmation card and uses the
   current workflow-backed backtest execution path.
8. The completed result uses the established Argus result explanation path,
   not Perplexity-generated result prose.

## Artifact Shape

Avoid a giant generic artifact system. Use concrete artifact types first:

- `research_session`: one user research task and its answer;
- `research_source`: normalized citation/source metadata;
- `research_hypothesis`: a supported or rejected candidate idea;
- `research_to_test_link`: mapping from hypothesis to confirmation/backtest job;
- `research_brief`: later, an inbox or recurring digest artifact.

Minimal citation fields:

- title;
- URL;
- source/publisher when available;
- published date or source date when available;
- last-updated/fetched-at timestamp;
- snippet or evidence quote within allowed copyright limits;
- provider/tool used;
- confidence or freshness metadata when available.

## Citation Rules

Every user-visible external research claim needs citations. If Argus cannot
cite it, the prose should be framed as an assumption, a prompt to clarify, or an
unsupported direction, not as a fact.

Backtest metrics do not need research citations because their provenance is the
Argus engine and persisted `backtest_runs`. They do need normal result
assumptions, benchmark context, and no-advice language.

Citations should be visible in the chat UI without overwhelming the first
viewport. Prefer compact inline/source chips plus an expandable source list or
drawer.

## Config And Cost Controls

No model or provider choice should be hardcoded into user-facing code.

Suggested future config:

```bash
```

The model chain above reflects the product hypothesis discussed on June 9,
2026, not a verified availability guarantee. Before implementation, verify
current model IDs and pricing through Perplexity.

Route receipts should record:

- research provider;
- model selected;
- tools used;
- latency;
- source count;
- citation count;
- filtered hypothesis count;
- rejected hypothesis reasons;
- cost/usage when available.

## Caching And Freshness

Research caching should be separate from market-data caching.

Recommended first cache:

- Supabase-backed source and research artifact snapshots keyed by normalized
  research intent, source URL, provider/tool, user locale, and freshness window.

Do not cache all research forever. Use freshness policies by topic:

- market/current events: short TTL;
- company background or definitions: longer TTL;
- user-specific research sessions: durable as user artifacts;
- provider result payloads: store only sanitized, display-safe metadata.

Market OHLCV cache remains a separate system keyed by provider, asset class,
symbol, timeframe, data window, and schema version.

## UI Direction

Stay chat-first.

The first research answer should be readable in the conversation, with sources
available near the claim they support. Supported test ideas should appear as
explicit "testable idea" cards that can become the existing confirmation card.

Do not add a dashboard as the first version. Do not expose provider plumbing.
Do not show unsupported ideas as runnable actions.

The sidebar inbox/daily brief idea is promising but deferred. It likely belongs
after the first research-to-test loop proves people want recurring monitoring.

## Acceptance Gates

The first implementation PR is not acceptable unless:

- no uncited external factual claims are presented as fact;
- no unsupported backtest cards are generated;
- Perplexity output is filtered through Argus capability contracts;
- backtest result prose still comes from the established Argus explanation path;
- provider/tool details remain internal unless intentionally surfaced as source
  metadata;
- the feature is gated by `[removed obsolete setting]`;
- no service-role or provider secret reaches the frontend;
- route receipts give enough evidence to debug cost, source quality, and tool
  usage.

## Deferred Questions

- Which Perplexity model IDs are available and cost-effective at implementation
  time?
- Should research jobs run inline, through Render Workflows, or through a
  separate queue once tool latency is measured?
- What exact legal/privacy language is needed before storing and sharing
  research artifacts?
- Which citation UI pattern feels trustworthy without cluttering the chat?
- Should FRED remain a first-class provider for macro series, or should it be
  used only when Argus needs deterministic macro data?
- Does a memo-style product surface add value, or does chat plus saved research
  artifacts cover the need?
