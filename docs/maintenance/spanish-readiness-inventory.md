# Spanish Readiness Inventory

## Summary

This inventory assesses the Argus application for Spanish localization readiness. It identifies hardcoded English strings and language/locale handling gaps across the frontend UI, backend deterministic copy, and LLM language contracts.

**Decision (2026-11-13):** English and Spanish are always available in every
build. `web/lib/language-features.ts` owns the language list and defaults;
language availability needs no deployment variable. The findings below retain
historical readiness context and do not gate Spanish availability.

**Runtime-state normalization update:** `codex/private-alpha-readiness` adds a
shared `resolution_provenance` normalizer for workflow snapshots, public runtime
payloads, interpreter patches, and LLM interpreter capability validation. This
addresses the known dict-shaped provenance crash class. Bilingual canary and
browser smoke evidence remain quality checks, without gating Spanish availability.

**Interpreter schema update:** `codex/private-alpha-readiness` now asks the LLM
to accept any user language while returning canonical Argus machine values, plus
`language`, `date_range_raw_text`, `date_range_intent`, and `evidence_spans`
metadata. Runtime date repair resolves canonical temporal intent first and only
passes bounded date evidence through `argus.nlp.natural_time`; it does not parse
localized whole-turn prose as a shortcut around the interpreter. This removes
the hardcoded multilingual token-table growth pattern from the normal runtime
spine. Relative endpoint edits use canonical offset math such as
`anchor=today` plus `day_offset=-1` rather than localized words such as
"ayer", "yesterday", or future per-language aliases. The private-alpha CI/CD
SOTA gate now supplies the required bilingual live canary evidence for
controlled production-like exposure; remaining messy-language semantic
continuity gaps are tracked as follow-up correctness work, not as a blanket
Spanish-disable condition.

**Local language-spine QA checkpoint:** focused backend tests and Codex browser
QA now prove that messy Spanish and English buy-and-hold prompts with shorthand
capital, such as `compra y manten eth ultimos 8 meses 100k` and
`buy and hold eth last 8 months 100k`, reach the same canonical confirmation
shape. The Spanish browser run rendered the Spanish shell/card copy and
`$100,000`; the English mirror rendered English shell/card copy and `$100,000`.
This checkpoint validates LLM-first interpretation plus post-interpretation
guardrails for that shape. It does not replace the remaining multi-turn,
result, retry/recovery, indicator/DCA, and production-parity Render QA gates.

**Domain slot normalization update:** LLM-returned strategy and DCA cadence
values are expected to be canonical engine values such as `buy_and_hold` and
`weekly`, while localized source wording stays in evidence spans and user-facing
prose. The strategy capability registry is no longer treated as a
natural-language alias phrasebook in English, Spanish, or future languages;
unknown localized cadence text is preserved as `raw_cadence` metadata and
cleared from the executable cadence field so deterministic guardrails can ask a
follow-up instead of leaking localized prose into the engine contract. The
secondary field-fidelity audit path uses the same canonical cadence validator,
so it cannot reintroduce localized cadence prose after the main interpreter
pass.

**Language-agnostic runtime guardrail:** input language and product locale are
separate contracts. The LLM interpreter may accept English, Spanish,
Portuguese, mixed-language shorthand, or other user turns, but executable fields
must remain canonical Argus values and user-facing artifacts must render in the
resolved product locale (`en` or `es-419` today) unless the user explicitly asks
to switch languages. Do not add regex gates, locale phrase tables, or
language-specific strategy aliases to runtime contracts. If a primary LLM pass
returns raw multilingual strategy phrasing as unsupported while preserving
execution evidence, repair it through a structured capability audit that selects
a canonical supported family or keeps the unsupported constraint. `@` mentions
remain provenance/disambiguation only: they can help preserve the intended asset
identity, but they must not bypass the LLM interpreter, provider-backed resolver,
same-asset validation, capability checks, or execution guardrails.

**Recovery contract update:** recoverable chat failures now use typed recovery
codes, normalized recovery language, and structured `retry_last_turn` metadata
instead of durable English prose as the behavior contract. The user-facing
fallback copy is centralized and localized for English and Spanish, and the
frontend hydrates retry controls from metadata instead of matching message text.
This is covered by the private-alpha gate with live English and Spanish canary
evidence. Keep bilingual quality coverage; if future runtime regressions
appear, capture them as focused issues instead of reverting to a broad
language-disable posture.

The findings are grouped by category:
*   **Static frontend UI copy**: ~100+ strings wrapped in `t()` with hardcoded English fallbacks.
*   **Backend deterministic user-facing copy**: ~20+ strings in API exceptions and artifact labels.
*   **LLM prompt / instruction language contracts**: ~15+ strings in system prompts and context packets.
*   **Artifact/result/status labels**: ~10+ strings defining statuses and outcomes.
*   **Test fixtures/snapshots**: ~10+ strings in validation tests.
*   **Internal logs/debug-only strings**: ~50+ log messages using English.

## Highest Priority Findings

| Area | File(s) | Finding | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Frontend Cards** | `web/components/chat/StrategyConfirmationCard.tsx`, `web/components/chat/confirmation-display.ts`, `src/argus/api/chat/confirmation.py` | Confirmation cards now emit/use stable `status`, `rows[].key`, and i18n label keys instead of using translated labels for behavior. | Resolved | Codex-owned | Keep the `spanish-ui-smoke` guard that rejects `row.label.toLowerCase()` and English status sets in card state logic. |
| **Artifact Status** | `web/components/chat/artifact-history.ts`, `web/lib/chat-backtest-jobs.ts` | Confirmation lifecycle updates now store stable status codes while preserving legacy English fallback labels for old persisted cards. | Resolved | Codex-owned | Continue using `confirmation-display.ts` helpers for new confirmation status behavior. |
| **Backend API Errors** | `src/argus/api/routers/conversations.py` | Hardcoded HTTP exception details: `"Conversation not found."`, `"Strategy not found."` | Medium | Product decision | Implement error code system (e.g., `error_code="CONVERSATION_NOT_FOUND"`) that frontend maps to `t()`. |
| **Backend Results** | `src/argus/domain/benchmark_comparison.py` | User phrases generated in backend: `"Beat by {magnitude}"`, `"In line with benchmark"` | High | Product decision | Return structured data (e.g., `{ type: "beat_benchmark", value: magnitude }`) and localize in frontend. |
| **LLM Prompts** | `src/argus/agent_runtime/stages/interpret.py` | System prompts: `"Supported-strategy facts:"`, `"Available short-lived context packet:"` | High | Codex-owned | Do not change. Treat as Codex-owned runtime contracts.|
| **Runtime State Hydration** | `src/argus/agent_runtime/state/models.py`, `src/argus/agent_runtime/runtime.py`, `src/argus/agent_runtime/graph/workflow.py`, `src/argus/agent_runtime/stages/interpret.py`, `src/argus/agent_runtime/stages/interpret_types.py`, `src/argus/agent_runtime/llm_interpreter.py` | Dict-shaped `resolution_provenance` entries are normalized/deduped before durable snapshot carry-forward, public payload serialization, interpreter patches, and LLM interpreter capability validation. | Partially resolved | Codex-owned | Keep the regression tests and retain live bilingual canaries plus browser smoke as quality coverage. |
| **LLM Interpreter Metadata** | `src/argus/agent_runtime/llm_interpreter.py`, `src/argus/agent_runtime/llm_interpreter_types.py`, `src/argus/nlp/natural_time.py` | Structured interpretation now carries `language`, `date_range_raw_text`, `date_range_intent`, and `evidence_spans`; canonical temporal intent is resolved deterministically, bounded date evidence is resolved through the natural-time wrapper instead of month/date language tables inside runtime contracts, and focused audits can reconcile user-stated capital when the LLM preserved it in draft prose but omitted the canonical field. | Partially resolved | Codex-owned | Keep the canonical-intent, bounded-span, field-fidelity, and contract-boundary tests; track messy semantic-continuity regressions in #119. |
| **Recovery Copy** | `src/argus/agent_runtime/recovery_messages.py`, `src/argus/api/routers/agent.py`, `web/lib/argus-api.ts`, `web/components/chat/ChatInterface.tsx` | Recoverable chat failures now persist typed recovery metadata, localized fallback copy, and structured retry metadata instead of making English prose the durable behavior contract. | Locally resolved | Codex-owned | Keep the recovery contract tests green and keep Spanish recovery inside the bilingual live canary gate. |

## Detailed Inventory

### Static frontend UI copy

| File / Area | Representative examples | Classification | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `web/components/chat/StrategyConfirmationCard.tsx` | Confirmation row behavior now uses `rows[].key` with legacy fallback mapping in `confirmation-display.ts`. | UI Logic | Resolved | Codex-owned | Preserve stable row keys for future languages. |
| `web/components/chat/ChatInput.tsx` | `t("chat.message_empty", "Message is empty")` | Fallback | Low | Jules-safe | Rely on localization JSON files instead of hardcoded fallbacks. |
| `web/components/chat/StrategyResultCard.tsx` | `t("chat.result_card.ending_value", "Ending value")` | Fallback | Low | Jules-safe | Rely on localization JSON files. |
| `web/components/sidebar/ProfileMenu.tsx` | `t("settings.profile.delete_account", "Delete account")` | Fallback | Low | Jules-safe | Rely on localization JSON files. |

### Backend deterministic user-facing copy

| File / Area | Representative examples | Classification | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/argus/api/routers/*.py` | `raise HTTPException(status_code=404, detail="Conversation not found.")` | Error msg | Medium | Product decision | Send error codes instead of strings to allow frontend localization. |
| `src/argus/api/dependencies.py` | `detail="Supabase persistence is required for non-mock authentication."` | Error msg | Medium | Product decision | Send error codes. |
| `src/argus/domain/benchmark_comparison.py` | `user_phrase=f"Beat by {magnitude}"` | Data label | High | Product decision | Move string generation to the frontend, send structured values. |
| `src/argus/agent_runtime/recovery_messages.py` | Centralized `RecoveryMessageCode` values map to localized fallback copy and retry metadata. | Recovery contract | Locally resolved | Codex-owned | Treat this as a fallback safety layer only; normal Argus voice should still come from the LLM runtime when available. |

### LLM prompt / instruction language contracts

| File / Area | Representative examples | Classification | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/argus/agent_runtime/stages/interpret.py` | `{"role": "system", "content": f"Supported-strategy facts: {fact_packet}"}` | Prompt | High | Codex-owned | No action needed. Treat as Codex-owned. |
| `src/argus/agent_runtime/artifact_edit_planner.py` | `{"role": "system", "content": ...}` | Prompt | High | Codex-owned | No action needed. Treat as Codex-owned. |
| `src/argus/agent_runtime/result_followups.py` | `{"role": "system", "content": ...}` | Prompt | High | Codex-owned | No action needed. Treat as Codex-owned. |
| `src/argus/agent_runtime/stages/explain.py` | `{"role": "system", "content": ...}` | Prompt | High | Codex-owned | No action needed. Treat as Codex-owned. |

### Runtime language-agnostic spine

| File / Area | Representative examples | Classification | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/argus/agent_runtime/state/models.py`, `src/argus/agent_runtime/runtime.py`, `src/argus/agent_runtime/graph/workflow.py`, `src/argus/agent_runtime/stages/interpret.py`, `src/argus/agent_runtime/stages/interpret_types.py`, `src/argus/agent_runtime/llm_interpreter.py` | Shared provenance normalization protects persisted snapshot carry-forward, public runtime payloads, interpreter patches, and LLM capability validation from dict/model drift. | State normalization | Partially resolved | Codex-owned | Keep bilingual canaries and browser smoke green; broaden Spanish continuation QA under #119 follow-up scope. |
| `src/argus/agent_runtime/llm_interpreter.py`, `src/argus/agent_runtime/llm_interpreter_types.py` | LLM interpreter schema and prompt now require canonical internal values, detected language, bounded date raw text, canonical `date_range_intent`, and evidence spans; conversion stores that metadata in `StrategySummary.extra_parameters`. Focused field-fidelity audits receive raw user phrasing plus draft-prose evidence so canonical fields can be corrected without adding language-specific parsers. | Interpreter contract | Partially resolved | Codex-owned | Do not make raw text executable by itself; use canonical intent or bounded evidence, keep deterministic validation, and add Spanish runtime transcript coverage. |
| `src/argus/agent_runtime/llm_interpreter.py`, `src/argus/domain/slot_normalizer.py`, `src/argus/domain/strategy_capabilities.py` | Post-LLM strategy and cadence values are expected to be canonical; localized wording stays in `evidence_spans` and prose. The capability registry keeps machine compatibility aliases only and no longer acts as an English or Spanish phrasebook. | Domain slot normalization | Partially resolved | Codex-owned | Add future languages through schema/prompt/test coverage and live QA, not by expanding capability phrase tables. |
| `src/argus/nlp/natural_time.py`, `src/argus/agent_runtime/strategy_contract.py`, `src/argus/agent_runtime/run_field_contract.py` | Canonical interpreter temporal intent is resolved with deterministic date math; bounded date evidence is resolved with `dateparser` through the Argus natural-time wrapper. Runtime contracts consume canonical dates and no longer own month alias tables or month-year span parsers. | Natural time parsing | Partially resolved | Codex-owned | Feed only canonical intent or bounded spans; keep the boundary test that prevents date-language tables from returning to runtime contracts. |
| `src/argus/agent_runtime/recovery_messages.py`, `src/argus/api/routers/agent.py`, `web/lib/argus-api.ts`, `web/components/chat/ChatInterface.tsx` | Runtime recovery carries stable `code`, `retryable`, `language`, and `retry_last_turn` metadata, while localized fallback copy is generated from a central catalog. | Recovery copy | Locally resolved | Codex-owned | Keep recovery behavior structured and language-aware; do not make English or Spanish prose the durable failure contract. |
| `tests/agent_runtime/*` | Existing tests now include Spanish DCA, direct buy-and-hold/date repair, mixed-asset guardrail, approval, and latest-result follow-up transcripts that exercise the real structured interpreter conversion and runtime validation. | Coverage gap | Medium | Codex-owned | Add targeted messy-language semantic-continuity coverage for #119 while preserving bilingual quality coverage. |

### Artifact/result/status labels

| File / Area | Representative examples | Classification | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `web/components/chat/artifact-history.ts` | Confirmation lifecycle now uses stable confirmation status codes and legacy label fallback mapping. | Status check | Resolved | Codex-owned | Do not reintroduce English display-label state checks. |
| `web/lib/backtest-job-card-copy.ts` | `statusLabelFallback: "Queued"`, `"Running"`, `"Result ready"`, `"Could not run"`, `"Not completed"` | Fallback | Low | Jules-safe | Rely on localization JSON files. |

### Test fixtures/snapshots

| File / Area | Representative examples | Classification | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tests/test_slot_normalizer.py`, `tests/test_strategy_capabilities.py`, `tests/test_strategy_registry_i18n.py` | Capability registry guards reject natural-language strategy/cadence aliases and require machine identifiers for registry aliases. | Test data | Resolved | Codex-owned | Keep these guards so English, Spanish, Portuguese, or future languages do not re-enter the execution registry as phrase tables. |

### Internal logs/debug-only strings

| File / Area | Representative examples | Classification | Risk | Owner | Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `src/argus/llm/openrouter.py` | `logger.warning("OpenRouter unavailable; missing API key", llm_task=task)` | Log | Low | Jules-safe | No action needed. Logs can remain in English. |
| `src/argus/api/chat/recovery.py` | `logger.warning(...)` | Log | Low | Jules-safe | No action needed. |

### Already localized / no action needed

| File / Area | Finding | Reason |
| :--- | :--- | :--- |
| `web/components/ThemeProvider.tsx` | N/A | No user-visible strings. |
| `src/argus/domain/cadences.py` | Canonical keys such as `daily`, `weekly` | Backend machine keys, rendered through localized UI/prose when shown to users. |
