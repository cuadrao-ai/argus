# Conversational Edit Contract — Design Spec

Status: Built + landed on `codex/private-alpha-next` (`0fb32c1`); retained as
the conversational edit contract reference.
Date: 2026-06-28 (updated — chips + iterative back-and-forth are core, not a fast-follow)
Branch family: `codex/private-alpha-next`
Sequence: first build slice of the P2 "make it trustworthy" track; sibling to
P2.1.b (capability honesty). Fixes the founder-reported edit-drop, makes the card's
action chips fully editable by click *or* natural language, and removes a live
English-leak in the edit path (advances the language-agnostic mandate).
Audience: founder, orchestrator, implementing subagents, reviewers.

Read with `docs/specs/private-alpha-next-roadmap.md` (P2 board + the six spine
invariants) and the memory note `conversational-edit-affordances`.

## 1. Problem (grounded in code)

A user editing a pending confirmation card cannot reliably go back and forth.
Two structural gaps:

1. **No canonical edit-operation model.** `ArtifactAssumptionEditPlan`
   (`src/argus/agent_runtime/artifact_edit_planner.py:18-32`) is a flat "set these
   fields" object with append/replace for assets and single values for the rest.
   It cannot cleanly express messy iterative edits like "add AMZN, drop TSLA,
   replace the benchmark, move the start to January," and it has **no date field at
   all** — so a date change is dropped by Pydantic as an unknown key. Worse, the
   LLM-authored `assistant_response` survives validation, so Argus can *claim* it
   changed the date while the card still shows the old one (canonical-payload vs
   UI-prose disagreement — a roadmap stop condition).
2. **Chips and natural language are separate paths.** The card chips
   (`run_backtest`, `change_dates`, `change_asset`, `adjust_assumptions`,
   `cancel_confirmation`; `web/components/chat/types.ts`) set UI/context state and
   route through the full interpret stage, while NL edits route through
   `plan_artifact_assumption_edit`. There is no shared operation set behind both,
   so a chip and a sentence expressing the same edit can diverge.

Adjacent defect on the same surface: the edit planner is **English-only**
(`artifact_edit_planner.py:77-130` takes no language), so edit replies can come
back in English inside a Spanish session.

## 2. Goal

A user shapes a pending confirmation card through messy, iterative back-and-forth —
by **clicking the card's chips, by typing it** (*"add AMZN, drop TSLA, swap the
benchmark to QQQ, move the start to January"*), or both, across one turn or many —
and Argus resolves all of it **cleanly, fast, and accurately, in the user's
language**, against the current card state: applying every operation, or clearly
naming what it could not — never silently dropping and never claiming a change it
did not make.

## 3. The contract

### 3.1 One canonical operation model (chips and NL both produce it)

Edits are an **ordered list of typed operations**, not a flat field set:

```
EditOperation = { op, target, value? }
  op:     add | remove | replace | set | clear      # "update" == set
  target: asset | benchmark | date_window | capital |
          recurring_contribution | cadence | timeframe | fees | slippage
```

Per-target semantics:
- **asset** (a set): `add` symbols, `remove` symbols, `replace` (swap whole set or
  symbol→symbol), `clear`.
- **benchmark / scalars** (capital, fees, slippage, cadence, timeframe,
  recurring_contribution): `set`, `clear`.
- **date_window**: `set` from an LLM-emitted date intent (absolute or relative).

Both a chip click and a natural-language turn produce this **same** list; the
backend applier is identical for both.

### 3.2 Resolution — one fast LLM pass

- A single structured LLM call turns the messy turn into the ordered op list,
  **resolving referents** ("that", "this", "the second one", "the benchmark")
  against the current card passed in context. No regex, no re-scan of the raw
  message, no extra LLM round-trips (latency is a requirement — keep it one call).
- Relative dates ("beginning of this year") resolved by the existing date engine
  (`resolve_date_range_intent` / `parse_date_text` with
  `dateparser_languages_for_user_language` hints, anchored to the conversation's
  reference date).

### 3.3 Apply + report — never silent, never lying

- Apply each op in order against the **current pending card** (backend-canonical
  state).
- The plan carries typed `applied` and `unsupported` op lists. The model-voiced
  reply names exactly what changed and what could not, **in the user's language,
  derived from the typed result — never from a post-hoc re-scan** of the message.
- Compound mixed-support ("add AMZN and switch to MACD"): apply the supported op,
  name the unsupported one with the registry-backed alternative (ties to P2.1.b).

### 3.4 Chips are shortcuts into the same contract

- `change_asset` → asset ops; `change_dates` → date_window; `adjust_assumptions`
  → capital/fees/slippage/…; `run_backtest` / `cancel_confirmation` = terminal
  actions.
- A chip produces operation intents (or focuses the next turn) that flow through
  the **same applier**. The frontend renders backend-returned card state; it never
  invents card state.

### 3.5 Iterative back-and-forth

- Each turn edits the **current** card (after previous edits). State accumulates
  server-side; the card the user sees is always backend truth, so click-then-type,
  type-then-click, and many-turns-in-a-row all compose.

### Spine mapping

LLM resolves messy NL + referents (one structured call, typed output) → #1/#3/#6.
No intent override or text re-scan → #1/#2. Typed-field validation only → #3. Dates
LLM-resolved, not literal-text grounded → #4. Model-voiced reply in-language, no
per-language table → #5. Backend-canonical card, frontend renders it → #6.

## 4. Schema / surface changes

- Replace the flat fields in `ArtifactAssumptionEditPlan` with
  `operations: list[EditOperation]` (keep `outcome`, `assistant_response`,
  `confidence`); add typed `applied` / `unsupported`. Add a `language` parameter to
  the planner call + prompt.
- `date_window` resolved via the existing `resolve_date_range_intent` path.
- Conversion (`llm_interpreter.py:4947-5035`): apply the op list to the draft;
  surface `unsupported` into the model-voiced reply.
- Frontend `web/components/chat/types.ts` + chip handlers: emit operation intents
  through the same contract endpoint; render backend card state.

## 5. Build order (revertable commits on one branch `codex/edit-contract`)

1. **Backend contract** (the heart): operation schema + planner prompt (messy NL →
   ordered ops, referent resolution, add/remove/replace/set/clear, dates) +
   applier + never-silent reporting + language-aware reply. Tested.
2. **Frontend chips → same contract**: chips emit operations; render backend card
   state. Tested.
3. **Prove it**: EN / ES / a third language; messy multi-op; iterative
   back-and-forth; chip↔NL parity.

Out of this slice: the staged reliability fix rides the eventual release (no work);
the deep teardown of the hand-written per-language recovery tables + a reusable
multi-language eval harness is the **next** slice (it is the fragile, spine-sensitive
part — it earns its own revertable slice).

## 6. Verification

- Backend tests: add/remove/replace/set/clear across targets; a messy multi-op turn
  applies all supported ops; date edit applies; mixed supported+unsupported reports
  correctly; iterative turns accumulate against current state; no silent drop and no
  false "I changed it" claim on any path.
- **Chip↔NL parity**: the same edit via a chip and via natural language yields
  identical backend card state.
- Browser QA in English, Spanish, and a third language: "add AMZN, drop TSLA, move
  the start to the beginning of this year," then a follow-up edit turn; confirm
  in-language model-voiced reply, no English leak, no raw enums.
- P2.0 guardrail tripwires stay green.

## 7. Spine stop conditions (escalate, do not work around)

Stop if a fix appears to need: re-scanning the user message for ops/dates,
overriding LLM intent after the call, rejecting an LLM-extracted value for not
appearing literally in the message, a per-language copy table, or a second
sequential LLM call to resolve one edit turn. If the contract cannot express an
edit as typed data, redesign the data, not the gate.
