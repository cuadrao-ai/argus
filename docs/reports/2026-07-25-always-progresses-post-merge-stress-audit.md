# Always Progresses post-merge same-conversation stress audit

Status: **HISTORICAL INTAKE EVIDENCE — FINDINGS ROUTED TO OWNERS**

Disposition (2026-07-26): this audit produced the bounded ownership queues now
recorded in the interim roadmap. #269 is proven Guest-only and carried by PR
#279; #270 is complete after PR #278 landed as `b80d95a2`; #271 is next and
#272 follows serially; #273 is closed after PR #277 landed as `2d5a2b52`; and
updated #249 owns the remaining result/recovery presentation concerns. This
report remains at its original path because issues and PRs cite its exact
observations. It is not an active implementation plan.

- Recorded: 2026-07-25
- Integration branch: `codex/private-alpha-next`
- Exact tested SHA: `b7fd6f08c2fb28166bc67a808ffdad0d65164f06`
- Conversation: `12468b50-7cd1-4dd5-91ea-156057b603fe`
- Surface: production-parity local browser, real interpreter, isolated
  Supabase project, one continuous conversation

This report is the issue-intake precursor for the founder-visible stress test
performed after PR #268 landed. It records what worked, what failed, and what
remained uncertain at capture time. It deliberately proposed no implementation
itself; the later ownership pass created #269-#273 and updated #249.

A later guest-lane reconciliation found a separate ordinary-starter runtime
failure after merging the integration checkpoint. That signal was later
classified as Guest-only terminal-settlement serialization in #269. Its
original observation and bounded proof live in
[`2026-07-25-guest-post-integration-runtime-regression.md`](2026-07-25-guest-post-integration-runtime-regression.md).
It is not evidence that every finding in this report shares one cause.

## Executive verdict

The Always Progresses slice is not fictitious: its bounded lifecycle and
recovery behaviors worked in this conversation. Ordinary edits persisted,
exactly one authorized backtest ran, the result survived reload, and later
turns did not create duplicate jobs or Runs.

The longer exploratory loop is not yet robust enough to call the whole
conversation experience complete. Repeated edits across a completed result,
new confirmations, stale actions, and a strategy-family change exposed several
continuity failures:

- execution costs disappeared after an asset append and could not be restored;
- a rejected stale Run left misleading Running/failed artifact presentation;
- recovery lost already-known facts and asked for them again;
- supported moving-average-crossover refinements repeatedly became
  buy-and-hold confirmations;
- generic recovery copy inherited visible `TRY NEXT` and `WHAT HAPPENED`
  section headings;
- one supported-strategy request produced a semantically incorrect
  clarification and malformed list formatting.

The bounded closure evidence in
[Always Progresses Closure Evidence](always-progresses-closure-evidence.md)
remains true for its tested journeys. This stress audit shows that those
journeys did not cover a long, stateful exploration chain.

## Audit scope

The user goal was to stay in one conversation and repeatedly:

1. edit capital, dates, costs, assets, and benchmark assumptions;
2. run one valid backtest;
3. append, remove, and replace assets;
4. recover from stale or failed actions;
5. change from buy-and-hold to a supported 50/200-day moving-average
   crossover;
6. preserve the latest result and all still-applicable facts throughout.

The audit intentionally remained on daily bars. Intraday-timeframe behavior is
outside this report.

## What remained healthy

| Step | Observed behavior | Health |
| --- | --- | --- |
| Initial drafting and edits | AAPL, capital, date, daily timeframe, benchmark, and costs reached a ready confirmation through conversational edits. | Healthy |
| Asset replacement before Run | AAPL changed to MSFT while capital, dates, daily timeframe, SPY, 10 bps fees, and 5 bps slippage remained canonical. | Healthy |
| Authorized Run | Exactly one job and one immutable Run completed for MSFT. | Healthy |
| Result truth | The MSFT result and Quick take survived reload with the same run identity. | Healthy |
| Asset-set edits | Append, remove, and replace operations changed the asset universe without creating another job or Run. | Structurally healthy |
| Duplicate-compute protection | Later stale or misleading Run interactions did not create a second job or Run. | Healthy at the durable boundary |
| Original result immutability | Later confirmation and recovery failures did not mutate the completed MSFT Run. | Healthy |

At the end of the inspected sequence, the database still contained exactly one
backtest job and one backtest Run for the conversation.

## Confirmed findings

### AP-STRESS-01 — Execution costs disappear after an asset append

Classification: **confirmed durable-fact continuity defect**

Likely user impact: **high**

The ready MSFT confirmation stored:

- `fee_rate: 0.001`;
- `slippage: 0.0005`;
- launch realism of 10 bps fees and 5 bps slippage.

After “Add AAPL to the strategy alongside MSFT,” the replacement confirmation
preserved the assets, $12,000 capital, dates, daily timeframe, and SPY, but
stored:

- `fee_rate: null`;
- `slippage: null`;
- no execution-realism launch block.

The visible card changed from fee/slippage assumptions to `No fees` and
`No slippage`. Repeating the costs in natural language and using the card's
Edit costs control did not restore them. Subsequent remove and replace actions
continued from the no-cost state.

This is not a visual-only discrepancy. The persisted confirmation and launch
payload both lost the costs.

### AP-STRESS-02 — Stale Run rejection protects compute but leaves dishonest UI

Classification: **confirmed action-reconciliation and presentation defect**

Likely user impact: **high**

A Run action associated with a superseded confirmation was rejected before
compute. Durable safety held:

- job count remained one;
- Run count remained one;
- the completed MSFT result stayed immutable.

The visible experience did not settle cleanly. The user saw stale-action
recovery while artifact presentation remained Running or later showed a
`Could not run` buy-and-hold card. Reload did not reliably restore the latest
usable confirmation as the obvious next action.

The backend correctly prevented duplicate work, but the frontend did not
convert that durable truth into an honest, actionable state.

### AP-STRESS-03 — Recovery asks again for facts the conversation already owns

Classification: **confirmed semantic-continuity defect**

Likely user impact: **high**

After the stale Run path, the conversation still had a current NVDA
confirmation and a completed MSFT result. Recovery instead asked the user to
choose buy-and-hold again, then asked for the asset and date range again.

The user had to restate NVDA, $12,000, January 3, 2023 through December 31,
2024, daily data, and SPY before receiving another confirmation.

This violates the product meaning of “always progresses.” The system remained
technically responsive, but progress was achieved by making the user rebuild
known state.

### AP-STRESS-04 — Supported strategy refinement silently remains buy-and-hold

Classification: **confirmed capability/continuity correctness defect**

Likely user impact: **critical for trust**

The user repeatedly asked to change the current AAPL/MSFT/NVDA strategy to the
supported 50/200-day moving-average crossover while preserving all other
assumptions.

The resulting confirmations remained buy-and-hold. The final persisted
confirmation contained:

- `strategy_type: "buy_and_hold"`;
- `rule_spec: null`;
- `entry_rule: {"type": "start_of_period"}`;
- `exit_rule: {"type": "end_of_period"}`;
- AAPL, MSFT, and NVDA;
- $12,000;
- January 3, 2023 through December 31, 2024;
- daily data and SPY;
- no fees or slippage.

This was not a card-label-only bug. Canonical runtime and launch state had
actually lost the requested crossover.

### AP-STRESS-05 — Generic recovery leaks result-follow-up headings

Classification: **confirmed UX ownership leak; attribution to PR #268 not yet proven**

Likely user impact: **medium**

Two generic recovery messages rendered with headings that imply useful result
content:

- `TRY NEXT`
- `WHAT HAPPENED`

Both messages contained the same generic body:

> I still have the latest result in this chat, but I could not safely answer
> that follow-up. Please retry in a moment.

Durable metadata explains the visible leakage:

- message `9e55ff52-0ab6-4628-816e-de7680e16125` carried
  `response_intent.kind = "result_followup_chrome"` and
  `heading_key = "next_experiment"`;
- message `091c46e3-0baa-4542-a0c3-ea7730289de3` carried the same intent with
  `heading_key = "general"`;
- both carried recovery code `latest_result_followup_unavailable`.

The frontend rendered those typed keys as localized section chrome. Therefore
this is not the frontend guessing from prose. The typed recovery path supplied
a result-follow-up heading for content that was only a failure message.

The heading mechanism predates PR #268 and was introduced for real
latest-result fact answers. The continuity stress path exposed its misuse; this
audit does not yet prove that PR #268 introduced the underlying defect.

The visible `TRY NEXT` heading is also inconsistent with the active
[result voice bridge design](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-06-11-argus-result-voice-bridge-design.md),
which removes Try next as a visible result surface.

### AP-STRESS-06 — Supported crossover request is misread as an unsupported comparison

Classification: **confirmed interpretation/clarification defect**

Likely user impact: **high**

The user supplied a complete multi-asset 50/200-day crossover request with
capital, dates, daily data, and SPY as benchmark. Argus replied that the engine
could not run the crossover “alongside a buy-and-hold baseline,” even though
the user requested SPY as the benchmark, not a second buy-and-hold strategy.

It then offered:

- the same supported moving-average crossover;
- buy-and-hold;
- RSI threshold.

This turns a fully specified supported request into an unnecessary
clarification and misstates the product limitation.

The response also rendered poorly because the first list item followed
`Which direction would you like to go? -` on the same line.

#### Was this caused by an output-token cap?

No. The full response was persisted as message
`a87d1633-a15b-42d6-ad5e-a923b924f97a`, and its lifecycle completed.

The provider evidence shows:

- one structured interpretation call timed out at approximately 20 seconds;
- fallback interpretation succeeded;
- clarification generation succeeded;
- the final message was completed and stored.

The screenshot therefore shows a timeout/fallback routing event plus malformed
Markdown, not a truncated SSE stream or an output-token cap.

### AP-STRESS-07 — Quick take is factual but feels mechanically degraded

Classification: **quality observation, not a confirmed PR #268 regression**

Likely user impact: **medium**

The visible Quick take was:

> MSFT buy and hold over January 3, 2023 - December 31, 2024 returned +75.7%,
> beating SPY (+53.6%) by 22.1 percentage points. This is a return comparison,
> not causal attribution. Daily data only

The facts match the result card. Durable job evidence shows:

- `result_readout_source: "llm_explain_stage"`;
- `result_readout_fallback_used: false`;
- result-readout generation completed in about 3.5 seconds.

It was therefore a normal LLM-authored Quick take, not deterministic fallback
copy. PR #268 did not change the Quick take generator or the ResultReadout
presentation block. The different feel is best classified as model-output
variance or voice-quality drift, not yet as a continuity regression.

It is still worth retaining for later triage. The line is terse, ends with the
awkward fragment `Daily data only`, and lacks the more readable Tested / Keep
in mind structure illustrated in the API contract.

## QA-operator note: why a new strategy was started

The “Start a new … golden-cross strategy” prompts were submitted by the QA
operator, not invented by Argus.

After in-place crossover refinements repeatedly returned buy-and-hold, the
operator tried a complete fresh crossover request in the same conversation to
separate two hypotheses:

1. only the edit/refinement corridor was broken; or
2. the conversation could no longer create a supported crossover at all.

That diagnostic was relevant, but it was unnecessary for the original
asset-edit stress goal and added noise and provider calls after a ready
confirmation already existed. Future stress runs should stop and record the
first confirmed semantic failure instead of expanding the journey in place.

## Attribution limits

This audit proves the behaviors exist on integration SHA `b7fd6f08`. It does
not yet prove every behavior was introduced by PR #268.

- The result-follow-up heading renderer predates PR #268.
- Quick take generation and its visible wrapper were not changed by PR #268.
- Costs, strategy transitions, stale-action reconciliation, and recovery
  context cross runtime surfaces that PR #268 did modify, but causal attribution
  requires a bounded comparison against the pre-merge parent.
- One provider/model sample cannot establish the frequency of an interpretation
  failure.
- Screenshots support visible UX findings but do not establish accessibility
  compliance.

The resulting issue bodies therefore say **observed after the Always Progresses
integration**, not **introduced by Always Progresses**, unless later bounded
evidence proves causality.

## Completed issue-intake mapping

The later ownership pass routed the findings without turning this report into a
single implementation lane:

1. **Durable assumption preservation** — AP-STRESS-01 is #271, serialized after
   completed #270.
2. **Artifact action reconciliation and truthful status** — AP-STRESS-02 was
   #273 and is complete through PR #277 at `2d5a2b52`.
3. **Semantic continuation and strategy transitions** — AP-STRESS-04 and the
   semantic part of AP-STRESS-06 were completed by #270; AP-STRESS-03 is #272.
4. **Recovery voice and heading ownership** — AP-STRESS-05 and the formatting
   part of AP-STRESS-06 are recorded in updated #249.
5. **Result voice quality observation** — AP-STRESS-07 remains an observation
   inside #249 rather than a separate blocker.

## Recommended acceptance surface before issue closure

A later correction should be judged by one same-conversation stress journey,
not only isolated turns:

- establish daily AAPL / $12,000 / fixed dates / SPY / fees / slippage;
- replace with MSFT and run once;
- append, remove, and replace assets while preserving applicable assumptions;
- reject stale actions without leaving Running or failed-state ambiguity;
- recover without re-asking owned facts;
- change from buy-and-hold to a supported 50/200 crossover and prove canonical
  `strategy_type`, rules, and card identity;
- reload after each material boundary;
- keep exactly one completed historical Run unless another Run is explicitly
  authorized;
- never attach `TRY NEXT` or `WHAT HAPPENED` chrome to generic failure prose;
- record Quick take source and fallback truth without requiring identical model
  wording.

## Current disposition

- No code change is authorized.
- No GitHub issue has been created.
- No additional live turn, retry, or backtest is required for this audit.
- The isolated conversation and database evidence are sufficient for founder
  triage.
