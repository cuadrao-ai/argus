# Model result readouts: merge evidence

Superseded rounds remain in commit [`0c86bfc903db3834b86c8f4b2cc53b597fce9365`](https://github.com/lagarcess/argus/tree/0c86bfc903db3834b86c8f4b2cc53b597fce9365/docs/reports/evidence/model-result-readouts).

## What this evidence establishes

The integration acceptance at `2a00068b0b75edffeef6cfa6b73b19fa41fc9d81` exercised an English SPY RSI result and a Spanish DOCN buy-and-hold result. All four readouts used Luna without fallback. In both languages the Sources panel opened, exactly one working state appeared before and after a reload during Breakdown generation, the completed answer was saved without Retry, and a what-next follow-up produced Try next rows whose date-range tap sent a typed refine action for the correct run.

The citation fix was then captured at `7d7ea88bbe0b2b66119c249069fb647bd7170fa7`. A new Spanish Breakdown on the same saved DOCN run used Luna without fallback and cost $0.01257. All four inline links have descriptive names and destinations present in the provider's returned sources. The existing panel selected three sources with dates: DigitalOcean's Q2 2026 results (August 4), Yahoo Finance's AI business coverage (July 9), and FinancialContent's market report (April 6). The full provider response contains eleven unique returned URLs; panel selection remains owned by the shared research projection. The 2025 drawdown precedes the June 15, 2026 peak; later company results are explicitly described as later information. The screenshot was taken after reload, proving that the accepted text and sources were saved together.

The combined browser proof remains valid after the citation fix: its only runtime changes are the Breakdown link brief and deterministic link normalization before saving. No chat job, loading-state, Try next, frame, card, or browser projection changed. The other retained screenshots show previously saved readouts; they are not claimed as fresh generations of the latest prompt. Earlier English DOCN and Spanish RSI proof was not invalidated by integration, and DCA was not rerun because the founder narrowed the affected cases.

The app used explicit live market/asset providers, process-only Luna overrides, development memory persistence and mock authentication. This proves browser-disconnect survival, not process-crash or real-database recovery; durable production job ownership and settlement are covered by focused tests. An initial restored-memory DOCN what-next experiment after Refine produced no Try next rows; its cost is included. The requested direct fresh-result follow-up path passed in both languages.

## Screenshots

| Case | Quick take | Breakdown |
| --- | --- | --- |
| DOCN, English (retained) | [Screenshot](docn-en-quick-take.png) | [Screenshot](docn-en-breakdown.png) |
| DOCN, Spanish | [Screenshot](docn-es-quick-take.png) | [Named links and Sources panel](docn-es-breakdown.png) |
| DCA with costs, English (retained) | [Screenshot](dca-en-quick-take.png) | [Screenshot](dca-en-breakdown.png) |
| DCA with costs, Spanish (retained) | [Screenshot](dca-es-quick-take.png) | [Screenshot](dca-es-breakdown.png) |
| SPY RSI, English | [Screenshot](rsi-en-quick-take.png) | [Screenshot](rsi-en-breakdown.png) |
| SPY RSI, Spanish (retained) | [Screenshot](rsi-es-quick-take.png) | [Screenshot](rsi-es-breakdown.png) |

| Combined behavior | English | Spanish |
| --- | --- | --- |
| One working state after reload | [Screenshot](en-working-after-reload.png) | [Screenshot](es-working-after-reload.png) |
| Try next rows | [Screenshot](en-try-next.png) | [Screenshot](es-try-next.png) |
| Date-range tap reaches the right refinement | [Screenshot](en-try-next-tapped.png) | [Screenshot](es-try-next-tapped.png) |

[Consolidated raw provider responses](provider-responses.json) contains source numbers, complete readouts, metadata, sources, typed tap payloads, provider invoices and the Luna billing-rate observations. No raw-response files are scattered through the tree. [Spend summary](spend-summary.json) separates the discarded partial measurement, combined browser proof, citation proof, full measurement and any allowed failure retry. Unpriced transport failures are not assumed to cost zero. The partial measurement contributes spend only, never results to the new scorecard.

## Kept and removed checks

| Check | Disposition and reason |
| --- | --- |
| Declared run figure reference | Keep: the fact key must exist and the cited value must match the run at card display precision. |
| Benchmark beat/lag contradiction | Keep: reject a comparison that contradicts the stored run. |
| Internal schema names in prose | Keep: implementation field names do not belong in the visible explanation. |
| Draft language | Keep: a mismatch produces the complete localized template, with fallback provenance. |
| Inline link destinations | Keep: only returned-source URLs remain linked; title a bare returned URL, unlink an unreturned destination while keeping its words. |
| Three-figure allowance and content caps | Remove: richer accurate explanation is allowed. |
| Required mentions in either readout | Remove: the card owns the figures; prose should add meaning rather than repeat a checklist. |
| Per-occurrence run-quote bookkeeping | Remove: an unreferenced number does not discard the answer; declared references still get value/key validation. |
| Web claim quote, occurrence and date bookkeeping | Remove: the provider's sources travel in the existing panel, with dates when returned. Link membership does not prove every claim true. |

## Final review follow-up

Codex found that GFM autolinks entity-decoded and backslash-escaped URLs. The fix matches the decoded text while preserving original spans outside URLs, so it does not activate unrelated literal Markdown. Shared fixtures in `tests/fixtures/result_readouts/link_encodings.json` prove the accepted backend strings and actual `ChatMessage` rendering in English and Spanish. The focused backend run passes 305 tests and the full web suite passes 1,799 tests. The saved live Spanish draft was revalidated byte-for-byte unchanged; its screenshot remains valid. Model-facing text and the measured fingerprint are unchanged, and no additional paid calls ran.

## Measurement

[Full scorecard](live-measurement.json): **67 passed, 3 failed, 1 infrastructure error**, across 71 cases. [One retry per non-passing case](measurement-retries.json): **4 passed**. [Case-by-case comparison](measurement-comparison.json) retains every first-run failure and its receipt analysis. None reproduced in its single retry; this is not a claim that the first run passed 71/71. Five baseline failures passed in the full run, and both added integration cases passed. Known merge-prep spend: **$3.169720877376**, below the $3.50 billed-spend cap; 12 timed-out requests returned no invoice and remain explicitly unpriced. This is the known billed total, not an assumption that those attempts cost zero. No further paid calls ran.

The complete measurement ran once on the clean pushed citation-fix head, with `ARGUS_MARKET_DATA_PROVIDER_MODE` and `ARGUS_ASSET_PROVIDER_MODE` assigned directly to `live_provider` in the process. Its scorecard includes candidate SHA, fixture identity, runtime, live market-data probe and route receipts. Any surprising-failure retry is separate and does not replace the first result. The case-by-case comparison records structured-tier timeouts beside every flip and receipt review for each case failing in both runs.

## Reconciliation and deterministic verification

Original integration base: `d0884c3de81f8c53d454ac4f68f461d3b5dd77e3`. Reconciled integration: `26d86cb13fa6c451026bd8e544dbb51c7fa7cc6f`. Initial one-way merge: `ae6d6adfde74f5c61d900a73c7ec668012675a23`. Integration subsequently advanced to `ff98fec7aeac19941085b5ad168062a55a1a3399` with three roadmap-only commits. They were merged as `40e9fb9e408043835feb70829bce53c8632330b2`; no runtime, test, prompt, environment or API surface changed, so paid evidence was retained.

The ChatInterface conflict retained result facts, language-stamped readout content and the Try next source run ID in both final-message constructors. Shared chat projections, message types, final transport, agent route, Perplexity client and API contract were audited for semantic overlap. Readouts now use the shared visible-reply punctuation owner. The integration-owned grounded-finance roadmap was restored and left equal to integration.

After reconciliation: 1,036 focused backend/mocked-eval tests, 2,354 hermetic agent-runtime tests and 1,779 web tests passed. The citation delta adds a 280-test focused run, including both languages and the composer-to-panel source handoff. Ruff and the merged-tree modularity budget passed. Final exact-head CI and review are recorded in the PR's terminal audit after review completes.

## Old wiring audit

Searched `src`, `tests`, `docs`, `scripts` and `.github`. Active `result_summary` routing now uses `readout`; the Breakdown OpenRouter task/profile/tier and timeout are removed. Chat and context retain their other tasks and environment keys. The Breakdown message kind, context-building helpers and cost-ledger task label remain intentionally; they are not OpenRouter routing. Historical receipts and initial design sections retain old tier names as history. `docs/specs/argus-grounded-finance-roadmap.md` also describes the old state and is intentionally unchanged because the founder returned it to integration ownership. Current contracts are `docs/API_CONTRACT.md` and `docs/CONVERSATIONAL_RUNTIME.md`.

The founder must provide these local environment lines; this lane never wrote environment files:

```dotenv
CUADRAO_READOUT_MODEL=openai/gpt-5.6-luna
CUADRAO_READOUT_FALLBACK_MODEL=openai/gpt-5.6-luna
```

The founder merges and deploys. This lane does neither.

## Founder side-by-side

On the PR preview, open a new English conversation and enter `Buy and hold DOCN since September 2023 against SPY.` If asked, supply `$1,000 starting capital, no fees, no slippage.` Check the confirmation, run it, read Quick take and choose Explain result; open Sources beside the Breakdown. In a new Spanish workspace, repeat with `Compra y mantén DOCN desde septiembre de 2023 y compáralo con SPY.` Supply `Capital inicial de $1,000, sin comisiones ni deslizamiento.` Choose Ejecutar backtest, then Explicar resultado and Fuentes. Compare the holding experience and sourced historical context with a competitor, not only the card figures. This lane captured the real local app and did not deploy a hosted preview.
