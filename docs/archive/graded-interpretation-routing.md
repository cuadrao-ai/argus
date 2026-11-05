# Graded Interpretation Routing

One lane, end to end: the interpreter ValueError dead end and the routing
defect behind it. Ships together with the diagnosability and recovery
groundwork on this branch.

## The macro pattern

Argus understands part of a message, cannot turn it into a runnable strategy,
and throws away what it understood. Every Tier 1 face is this shape:

| Face | What was understood | What happened to it |
| --- | --- | --- |
| Statistics question (item 4) | S&P 500 resolved to SPY | Discarded; four-field interrogation |
| Suggestion chips (item 3) | The label | Discarded; refusal |
| Bare period reply (item 2) | The period | Discarded; clarify loop |
| ValueError dead end (item 1) | The whole response | Discarded; sticky retry banner |

## Root cause

Routing was binary. `expects_strategy_route` flipped on when the draft carried
any one field, so a single resolved ticker, a date, or a benchmark injected by
our own default repair forced the strategy route over the interpreter's own
non-strategy classification. Partial understanding had no destination, so it
became a failure branch.

## The fix

Route on graded evidence. Every level of understanding has a destination;
there is no discard branch.

| Understanding | Destination |
| --- | --- |
| Full strategy | Confirmation card (unchanged) |
| Execution evidence, gaps | Card plus one targeted question (unchanged) |
| Reference only (asset, date) | Answer or one answerable question, reference kept |
| Nothing | Conversational answer |
| Model returns nothing usable | One in-tier corrective re-ask, then honest non-retryable terminal |

Mechanics, all model-grounded, no regex or language gates:

- `strategy_has_execution_evidence` (interpreter/draft_shape.py) separates
  execution fields from reference fields. Only execution evidence may pull a
  non-strategy turn onto the strategy route (stages/interpret.py).
- Focused extraction cannot invent a strategy frame from a verbatim echo
  (interpreter/focused_extraction.py); a model-asserted thesis or execution
  field is required.
- A reference-only unsupported turn with no text fails required shape, so the
  bounded self-correction demands an answer (llm_interpreter.py).
- Contract rejections log their detail and origin, book a
  `interpretation_contract_rejected` route receipt, and the terminal banner is
  honest and non-retryable only when retrying cannot succeed.

## Live evidence (2026-08-05, grok-4.3 / haiku-4.5)

"Ayúdame con estadísticas sobre el S&P 500"

- Before: `needs_clarification`, missing `[entry_logic, asset_universe,
  exit_logic, date_range]`, empty text. The item 4 interrogation.
- After: "Claro, puedo ayudarte a analizar el S&P 500 ... tengo tres opciones
  concretas para empezar ... ¿Qué enfoque te gustaría usar?"

"Simula comprar y mantener AAPL" (regression probe)

- After: "¿Para qué período te gustaría simular la estrategia de comprar y
  mantener AAPL?" One targeted question; level 2 intact.

## Not in this lane

- Item 4 proper: answering the statistics with actual numbers. The turn now
  lands on an honest, answerable reply instead of an interrogation; a
  knowledge-answer surface is its own slice.
- The last-resort seeded extraction after both tiers and both corrections fail
  (`_focused_strategy_repair_after_candidate_failures`) keeps its old shape.

## Regression locks

`tests/agent_runtime/test_graded_interpretation_routing.py`,
`tests/agent_runtime/test_interpretation_contract_rejections.py`, plus updated
contracts in `tests/test_openrouter_policy.py`.

## The answer router (founder-locked 2026-08-06)

Level 3 is no longer an admission: a facts question gets an answer from the
most authoritative source available, then the Try next surface.

| Source | Owns | Mechanism |
| --- | --- | --- |
| Own market data | asset statistics | `agent_runtime/knowledge_answer.py`: resolved asset + window through `fetch_price_series`, computed return/drawdown/volatility, voiced over the direct JSON transport with a numeric fallback |
| Discovery search provider | current external facts | existing `discovery_search` provider (perplexity_direct), cited sources, also the degrade path when market data cannot serve |
| Interpreter prose | concepts | unchanged |

Routing trusts the interpretation first: a provider-resolved asset on a
knowledge turn is the classification, so the extra `knowledge_route` LLM call
runs only for assetless external questions (the turn-call allowance made a
late classifier unreliable). Every grounded answer carries `next_experiments`
rows; the projection and `ChatMessage` render them on plain messages, and a
row lands a ready-to-run card inheriting the answer's window.

Live journey (2026-08-06, this branch): statistics question → computed SPY
numbers → Try next → buy-and-hold card, Ready to run, window inherited.

Known gaps, recorded not hidden: rows appear on hydrate, not yet during the
live stream; voiced answers follow workspace language rather than message
language (#378, its own item); demo numbers came from the synthetic fixture
provider, the recipe this repo's QA uses.
