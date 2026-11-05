# Evidence: #434, #489, #482

Three issues, one shape. Deterministic English prose reaching a Spanish reader
because the typed code the presentation boundary needs was missing, absent, or
untranslated.

`browser-qa.json` holds the captured turns: the prompt, the backend payload, and
the string the reader actually saw, for each case in each language.

## What the browser proved

**#434, both languages.** The Spanish confirmation card reads
`Acciones · Datos diarios · Sin comisiones · Sin deslizamiento · Referencia: SPY`
while the backend card payload carries
`["$10,000 starting capital", "Datos diarios", "Benchmark: SPY"]` and
`display_facts: {fees: 0.0, slippage: 0.0, ...}`. The two English literals are
gone from the payload and the card says the same thing from the typed facts. The
English card is unchanged: `No fees · No slippage` still render, from the same
facts.

**#489, both languages.** Forcing `CUADRAO_OPENROUTER_CLARIFICATION_TIMEOUT_SECONDS=1`
makes the LLM clarifier time out, which is the production condition the issue
describes. The stream then carries `prompt_source: "degraded_fallback"`, an
English `assistant_prompt`, and a typed contract with a `reason_code`. The
Spanish workspace renders Spanish; the English workspace renders the same
sentence in English. That is the seam working: English persisted, Spanish read.

## What the browser did not prove, and why

**#482 was not captured in the browser.** A capacity refusal is decided during
Supabase-backed job admission, and this lane ran memory-mode: without a gateway,
`_maybe_create_shadow_job` never reaches the admission call. Standing up a local
Supabase stack means generating env files, which this lane was told not to write,
and pointing at hosted Supabase would put QA rows in production.

So the capacity copy is proven one layer down instead, not skipped:
`tests/agent_runtime/test_capacity_refusal_copy.py` feeds the real
`admission_rejection_envelope` for both ceilings through the real
`execute_stage` and asserts the typed recovery code, the retry affordance, and
that the copy no longer borrows the generic failure sentence.
`web/__tests__/workspace-language-prose.test.ts` renders that code through the
real frontend renderer against both bundles.

To close it in a browser, run a Supabase-backed QA stack with
`ARGUS_BACKTEST_JOBS_GLOBAL_RUNNING_LIMIT=0` and press Run backtest.

## Efficacy of the guards

Both new suites were run against the base file they guard, restored from
`eaf5d52b`:

- `tests/agent_runtime/test_workspace_language_prose.py`: 16 failed on base,
  122 passed on the fix.
- `web/__tests__/workspace-language-prose.test.ts`: 4 failed on base, 11 passed
  on the fix.

A guard that passes on the broken code is not a guard.

## Known residue, not fixed here

`_visible_card_assumptions` in `src/argus/agent_runtime/stages/confirm.py` still
builds its own English strip (`"No fees"`, `"No slippage"`, `"1D bars"`) onto
`strategy.assumptions`. It is visible in the captured payload. It is a second
brain for a fact `display_facts` owns, but it does not reach the card, and
`agent_runtime` beyond `clarification_contract.py` belongs to other lanes. Filed
rather than fixed.

Likewise, `ChatMessage`'s copy-to-clipboard text for a confirmation joins
`confirmation.assumptions` verbatim instead of the localized view model, so a
Spanish reader who copies the card gets English rows. Filed.
