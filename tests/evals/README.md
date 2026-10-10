# Argus Eval Harness

This folder contains the private-alpha measurement eval harness. Cases live as
data fixtures, and the harness asserts typed runtime outcomes instead of exact
assistant phrasing.

## Business E1 fixture gate

The separate Business corpus is in `business_cases/case_first_flow.yaml`.
Run `PYTHONPATH=src:web poetry run pytest tests/evals/test_business_eval.py -q --no-cov`
for free fixture validation and mutation checks. This command makes no model,
WhatsApp, or database calls. Its green result shows that the assertions detect
altered synthetic observations. It is not runtime or hosted evidence.

Each scripted step names its trusted actor, channel, immutable source alias,
owner message or human web command, and expected saved projection. The projection
checks draft count, revision, facts and fact source links, open questions,
durable action outcomes with actor, grant and issuer, visible sources, money
record count and balance delta. The adapter must map generated database IDs to
the fixture aliases. `web_action` identifies the canonical submitted human
review or approval command. It must not be labeled as an agent proposal.

The pending T1/W1 adapter takes a case's ordered steps and trusted sender scope,
runs each through the real LangGraph turn and declared Business executor against
an isolated database namespace, then reads back the persisted dossier, action
receipts, MoneyService records and balances after each step. It must obtain
Business data through a current grant-scoped service projection. Direct
DataAPI reads cannot supply Business rows. It must also return OpenRouter route
receipts, exact candidate revision, model IDs, cost and latency. No fixture
expectation can serve as its observed state. Until that adapter exists and the
root coordinator authorizes its call budget, the live E1 gate is unavailable.
The scorecard requires the adapter's capture ID, database namespace, graph and
executor run ID, and matching candidate SHA before it can report a pass.

`business_eval.py` holds the deterministic comparator and a structured reply
rubric through the existing OpenRouter adapter. The fixed first judge is
`x-ai/grok-4.3`. `rubric_calibration.yaml` supplies known-good and known-bad
Spanish and English examples. Missing or skipped runtime and judge receipts
remain unavailable in the Business scorecard; fixture checks never produce a
live pass. The approved runtime candidates are `anthropic/claude-haiku-5.5`,
`openai/gpt-6-luna-pro`, and `deepseek/deepseek-v4.1-flash`. Catalog availability
does not measure their latency or reliability.

## Test Tiers

- **Mocked harness - every change (free, no API calls):**
  Run the single [Mocked Run command](#mocked-run) below.
  Validates routing, scorecard provenance, live-environment refusal, state,
  full conversation-step manifests, and the seven session trajectories. This
  is the everyday inner-loop check.
- **Live eval - only the 3 sanctioned moments:**
  1. Pre-merge on a PR that changes runtime behavior.
  2. Main promotion candidate.
  3. After any model/provider change.
- **Browser QA is also real-API:** every turn spends tokens. Use it at gates, not
  per hypothesis.

## Mocked Run

Run the mocked harness checks with:

```bash
poetry run pytest tests/evals/test_measurement_eval_harness.py \
  tests/evals/test_measurement_eval_dca_semantics.py \
  tests/evals/test_measurement_eval_scorecard.py \
  tests/evals/test_measurement_eval_live_environment.py \
  tests/evals/test_chat_runtime_eval_manifest.py \
  tests/evals/test_chat_runtime_trajectory_harness.py \
  tests/evals/test_measurement_availability.py \
  tests/evals/test_measurement_delivery.py \
  tests/evals/test_measurement_outcome.py \
  tests/evals/test_prose_evidence.py \
  -q
```

This run is free. It does not call the LLM, does not spend provider tokens, and
is safe to run anywhere.

## Search Provider Evaluation (Issue #244)

Run the bounded Search fixture validator with:

```bash
poetry run pytest tests/evals/test_search_provider_eval.py -q --no-cov
```

This evaluation is also free. It parses clearly labeled, authored synthetic
Perplexity-direct and OpenRouter web-search fixtures and validates their shape.
URL fields, query-term coverage, declared latency/cost, zero-Search scenarios,
outage scenarios, and the normalizer-applied untrusted-source label are fixture
contract behavior only. They do not prove provider relevance, citation quality,
Search routing, runtime policy,
outage recovery, latency, or cost. Changing an `evidence_kind` string cannot
turn a fixture into empirical evidence; every empirical check stays unproven
until a later sanctioned probe supplies independently captured provider and
runtime provenance.

Generate the non-versioned decision evidence with:

```bash
poetry run python -m tests.evals.search_provider_eval
```

The report is written to
`temp/issue-244-search-provider-evaluation.json`. It must recommend deferral
until real provider evidence and explicit founder activation exist. Its
Perplexity-direct next-probe entry is an official-
documentation-based hypothesis, not an empirical provider comparison or
selection. Any public citation/context schema also remains behind its separate
API-contract approval gate.

## Live Run

Run the live harness with:

```bash
ARGUS_RUN_LIVE_EVALS=1 \
ARGUS_EVAL_ENV_FILE=<path> \
ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider \
ARGUS_ASSET_PROVIDER_MODE=live_provider \
poetry run pytest tests/evals/test_measurement_eval_live.py -q
```

`ARGUS_EVAL_ENV_FILE` must name a file no tracked file feeds, such as the
gitignored `.env`. The harness refuses the file when it, or any step on the way
to it, is a tracked file or tracked symlink, whatever path or link reaches it, so
`.env.example` is refused. Promotion evidence identity compares the tree, never
the eval's environment, so settings fed from a tracked file could change without
a new measurement. An untracked file that is not ignored already fails the
clean-worktree check.

Warning: this deliberately spends real LLM tokens. Use it when you want to
measure the current real interpret path, not for routine local lint loops.
Once `ARGUS_RUN_LIVE_EVALS=1` is set, missing provider credentials fail the
run instead of turning the requested gate into a green skip.
The live harness keeps bar data in the configured market-data mode but uses a
provider-backed asset catalog for company-name grounding. Set
`ARGUS_ASSET_PROVIDER_MODE=recorded_provider_fixture` with a provider-shaped
`ARGUS_ASSET_FIXTURE_PATH` for deterministic catalog input; otherwise the
sanctioned live run requires Alpaca asset-catalog credentials.

The market-data provider mode must be explicit. Before the first LLM call, the
suite asks the configured provider for a fixed equity window that begins on the
2024-01-01 market holiday. A valid live environment starts on 2024-01-02 with
`calendar_alignment`. Synthetic daily data starts on 2024-01-01 and stops the
suite before it can spend tokens or write a scorecard.

## When to Run

Run the mocked suite everywhere; it is free and safe.

Run the live suite at exactly three moments:

1. Once pre-merge on any PR that changes runtime behavior.
2. On every `main` promotion candidate, as a full run with no unexpected
   failures, measured at the candidate or at a commit the measurement cannot
   tell apart from it (`tests/promotion_evidence_identity.py`).
3. After any interpreter model or provider change.

Live results can vary. If one failure is surprising, rerun once, then
investigate. Never delete the case to make the run green.

## Scorecards

Live runs write JSON scorecards to:

```text
temp/argus_eval_scorecards/
```

`temp/` is gitignored, so scorecards are local run artifacts. Measurement
scorecards include per-category totals and pass rates. Seven-session scorecards
include stable trajectory labels, operation names, and failure prefixes only;
they omit prompts, SSE payloads, route receipts, and runtime identifiers.

Measurement scorecards use schema version 3 and cannot be written without this
validated `provenance` object:

- `market_data_provider_mode`
- `asset_provider_mode`
- `candidate_sha`
- `python_version`
- `fixture_sha256`
- `fixture_case_ids`
- `worktree_clean`
- `release_configuration` (API model IDs and on/off flags selected by the release profile)
- `live_market_data_probe` for a live run

The writer rechecks the provider modes, SHA, Python version, fixture hash,
fixture case identities, clean worktree, and measured release configuration
immediately before serialization.
If any value changed during the run, it emits no scorecard. A live scorecard
also requires every fixture case exactly once, `market_data_provider_mode`
set to `live_provider`, and the successful calendar probe.

Configuration keys derive from the API service of the committed release profile:
every `_MODEL` key and every value set to `true` or `false`. Model IDs use runtime
resolution; flags come from the eval process environment, never from the desired
contract values. Set flags explicitly to `true` or `false`: missing values remain
unknown, and aliases are not assumed to have identical runtime semantics. The
promotion gate compares the recorded values with the profile at the candidate
commit and reports each mismatching key with both values. Other settings (such as
timeouts and call allowances) and the web/workflow service settings are excluded.
Past manifests keep their original evidence; new promotions need schema-v3
scorecards and the same `release_configuration` field on baseline and targeted
A/B provenance. This is a configuration-mistake check, not tamper protection.

Expected-fail cases never count as passes. They are reported separately so
known broken behavior stays visible.

### Availability versus prose quality (#365)

Runtime composer attempts come from the captured route receipts, not from
matching recovery wording. When its chat attempts all fail or are skipped,
the requested prose judgment is `unavailable`, with `pass: null` and no failed
quality criteria. The localized recovery is retained as `observed` text; it
was not sent to the judge. A successful fallback remains subject to the ordinary
rubric. Missing text without outage evidence is still a product failure.
An unavailable structured judge response is also a missing measurement, not
an honesty zero. Typed assertions always run, including during an outage.

An outage-only case has status `infrastructure_error`. It blocks the sanctioned
gate, remains in the scorecard with its route receipts and costs, and contributes
neither a pass nor a zero to the quality denominator. With no quality measurements,
the category's `pass_rate` is `null`. A simultaneous typed failure remains `failed`
with the infrastructure evidence beside it. Expected-fail masks cannot hide an
outage. Historical schema-v2 scorecards are not rewritten; new scorecards add
the infrastructure count and per-result `infrastructure_errors`.

There is no automatic retry or paid A/B in this policy. Diagnose the recorded
availability failure and explicitly authorize any later rerun; an unavailable
measurement cannot establish either a product regression or a quality pass.
The deterministic transport reproduction in `test_measurement_availability.py`
costs $0 and does not certify current live-provider quality.

### Delivered outcomes (#520)

Every measurement fixture now has an `expected.offered` assertion. The current
set is 62 cases: the nine existing discovery assertions plus 53 strengthened
cases, including the two DCA cases added since the issue's original count.

- `launch_matches_expected` requires the actual delivered launch payload to
  contain the fixture's assets, strategy/rules, effective dates, benchmark,
  capital, DCA money roles/cadence, and modeled costs where specified. It reads
  the existing expected fields; fixtures do not duplicate their numbers.
- `clarification_matches_expected` requires the delivered clarification
  contract, its requested field, and its specified reason. A launch refusal's
  reason derives from `launch_validation_code`. `response` also requires text;
  `min_recovery_options` requires options for actionable recovery contracts.
- `min_next_experiment_rows` requires a delivered next experiment for Try next.
  Educational answers require `response` and retain their prose rubric.

The harness follows confirmation refusals through `clarify_stage`, just as the
runtime does. Four DCA refusal cases now measure the terminal
`unsupported`/`await_user_reply` response instead of stopping at the intermediate
`needs_clarification` result. Routing expectations elsewhere are unchanged.

`test_measurement_delivery.py` keeps all existing routing/draft facts correct
while removing delivery. Each of the 53 old cases accepted this deterministic
fault on the base; each strengthened case rejects it. Separate tests remove DCA
launch facts one at a time, clear earlier proposals, and exercise real offline
clarification after a confirmation refusal. This proves the assertions detect
missing delivery. It does not establish current live-provider behavior or fix
the separate #364 classification question.

Run the new regression checks without API calls:

```bash
poetry run pytest tests/evals/test_measurement_availability.py \
  tests/evals/test_measurement_delivery.py tests/evals/test_measurement_outcome.py \
  tests/evals/test_prose_evidence.py -q --no-cov
```

## Expected-Fail Cases

An expected-fail case must be tagged with an issue number and scoped
`allowed_failures`. Every mask names one exact `step_id` and one failure
`prefix`. The tag only masks that failure family at that step; the same prefix
at another step, or any unrelated failure, still fails the eval.

The lane that fixes the tagged issue must flip the case to pass as part of that
lane's acceptance. Expected-fail is a truthful baseline, not a permanent waiver.
If a tagged case has no failures, its status is `unexpected_pass`, which also
does not count as a pass. Remove the tag only after verifying the owning issue's
full acceptance criteria.

## Seven Alpha Session Trajectories

`alpha_session_trajectories.json` is an append-only, sanitized fixture set with
stable labels `alpha_session_01` through `alpha_session_07`. The typed adapter
runner dispatches every user or action step through stream, action, disconnect,
reload, retry, or persistence adapters. A disconnect step owns the submission
that is cut before the client observes a terminal; it is never modeled as a
second operation after a visible terminal. The runner rejects a disconnect for
an identity whose terminal was already observed. It checks canonical SSE, visible
response category, stage outcome, artifact and action identity, persistence and
reload state, typed recovery, route budgets, terminal fingerprints, stale
actions, and orphan-turn reconciliation.

Only unresolved trajectories carry one exact owning issue and a narrow set of
step-scoped allowed failure masks. Passing trajectories stay unmasked. The
approved #229 contract now owns the exact reliability vocabulary: `confirmation_id` is the Run `action_identity`, its
`Idempotency-Key` must match, and ambiguous Run responses reconcile through the
owner-scoped by-action lookup before a `404` may permit one exact replay. Ordinary
turns project approved lifecycle states; an unreconciled stale turn becomes
terminal `abandoned` recovery with `turn_abandoned` and a `retry_last_turn`
action keyed by `request_message_id`. Keep the tags until the corresponding
runtime lane lands and the full trajectory passes. The mocked mechanics do not
replace the sanctioned live gate, deployed exact-SHA browser proof, or founder
approval.

## Categories

This slice covers the locked built-surface categories present in the fixtures.
Categories for unbuilt surfaces, including comparison, freshness on return, and
research-to-test, get added when their lanes land.

`ordinary_conversation` landed with the subtract-the-guardrails lane (PR #565).
It holds the plain turns the backtest guardrails used to re-read: concept
questions in both languages, a capability question phrased as education, and a
market curiosity question. Each must reach an honest answer in the user's
language with `ready_to_respond`; the scorecard's route receipts show which
second reads ran, which is the evidence the narrowed gates are measured by.

`asset_discovery_routing` (issue #244) landed with the Grounded Discovery lane.
It asserts the `semantic_turn_act=asset_discovery` routing boundary and its
typed payload (relationship, anchors, category terms), plus near-miss negatives
(direct backtest, post-result "what next", capability questions). Discovery
turns end `ready_to_respond` on both the flag-off recovery path and the flag-on
search path, so the category holds in any sanctioned live environment.

`dca_capital_semantics` (issue #455) covers the two-role capital model PR #491
shipped. Both DCA money roles and the period are asserted from the launch
payload under their own names (`starting_capital`, `recurring_contribution`,
`cadence`), so a role swap is visible instead of hiding behind a shared
`capital_amount`. The cases cover the contribution-phrase capture risk ("I'll
start by putting in $200 a month" is the contribution, never the seed), the
plan-wide ceiling reading of "I only have $5,000", a stated seed reaching
`ready_to_run`, a `$0` seed with a below-bankroll-floor contribution, the named
refusal codes (`contribution_period_exceeds_window`,
`dca_contribution_zero_is_buy_and_hold`, deferred
`unsupported_dca_contribution_ceiling`), calendar alignment measuring the
period against the asked window, and the lane's stated blind spots: a non-zero
seed, multiple symbols, crypto, and a provider-truncated window. The category
is typed-only by design: the one-phrase contribution rendering and card row
copy are frontend facts proven by the #455 browser evidence, and the
next-session buy rule for non-trading-day contributions is proven by
`tests/domain/test_dca_trading_day_rule.py`; this category asserts the typed
facts both of those read from.

## Prose Judge

Judge rubric version: `argus-prose-quality-v1`.

The judge grades prose only: recovery tone, honesty, Spanish language integrity,
and raw runtime error leakage. Typed facts such as intent, assets, dates,
benchmark, stage outcomes, and capability verdict are asserted outside the judge.

### Judged Prose Retention (issue #369)

Every prose-judged case result carries the exact text the judge scored, under
`prose_judge.judged_assistant_text`. Without it, a surprising prose verdict
cannot be attributed to the generator or to the judge, and these cases are
nondeterministic enough that a rerun may not reproduce the failure.

Retention is unconditional, on passes as well as failures. A false pass costs
the same trust as a false failure, comparing a run's failing prose against its
passing prose is what separates a generator regression from judge drift, and
retaining only on failure would make the artifact depend on the verdict.

Retention is additive and inert: it never reaches a verdict, a failed check, or
a status. The record is built from the same value handed to the judge, so a
result cannot attribute a verdict to prose the judge never saw.

| Field | Meaning |
| --- | --- |
| `text` | Retained copy of the judged prose |
| `sha256` | Digest of the exact judged text, so two runs stay comparable |
| `character_count` | Length of the exact judged text |
| `truncated` | Whether `text` is an excerpt |
| `omitted_character_count` | Characters dropped by truncation |
| `redactions` | Redaction kinds and counts applied to `text` |

`text` is the judged prose verbatim when `truncated` is false and `redactions`
is empty, which is the ordinary case.

Prose over 4,000 characters keeps its first 2,500 and last 1,500 characters
around an explicit elision marker. Both ends are kept because judges react to
closing capability claims as often as to opening tone, and first-N truncation
drops exactly the part an `honesty` failure lives in.

Credential-shaped and user-identifying spans are stripped from the retained copy
only: API keys, bearer tokens, JWTs, URL userinfo, `key=value` credential
assignments, credential-carrying HTTP headers such as `Cookie`, `Set-Cookie`,
and `Proxy-Authorization`, email addresses, and the verbatim values of
secret-named environment variables. Raw runtime error text is a graded criterion, so provider
error strings do reach the artifact and could otherwise carry a credential with
them. Every strip is counted in `redactions`, so a reader can tell that the
retained text is not verbatim.

The invariant every redaction rule must hold: a secret's boundary comes from its
own grammar, never from a generic delimiter set. That means three things. The
opener decides the closer, so a quoted value runs to its closing quote. The
escape convention holds, so a backslash-escaped quote is not that closing quote.
Internal separators belong to the value, so an auth value covers its scheme and
credentials, a cookie header covers every `;`-separated pair, and a JWT covers
every segment.

Cutting at the first plausible-looking delimiter publishes the tail, and the
shortened head can also fall under a rule's minimum-length guard, which silences
the rule and publishes the whole value. When adding a rule, test that no
fragment of the secret survives rather than that a marker appears.

Live scorecards land in gitignored `temp/`, but they are routinely promoted into
`docs/reports/evidence/` as durable acceptance evidence. Treat the bound and the
redaction pass as requirements of that committed path, not as local hygiene.
