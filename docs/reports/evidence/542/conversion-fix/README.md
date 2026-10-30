# Guest conversion transport fix: PR #547

**Public-signup acceptance correction:** the screenshots below used a harness that explicitly forced `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=false`. They proved transport and the gated-access modal, but did not prove the production signup branch. The [corrected public-signup captures and flag trace](public-signup/README.md) supersede them for that acceptance claim. Product code is unchanged.

The guest workspace refusal now opens the existing conversion modal. The product change is one optional field, `FinalResponsePayload.code`; admission, allowance policy, daily precheck, frontend copy, and #543's durable receipts are unchanged.

## Browser acceptance

Captured on 2026-09-05 UTC from code commit `5cecbe43d87f1e624f102789e5f98aa82774e81a`. Both languages completed two actual engine runs before the third-click checks. The candidate frontend was compiled with `next build --webpack` and served with `next start`.

| Third-click case | English | Spanish | Admission evidence |
| --- | --- | --- | --- |
| Same visitor day | [Daily modal](en-same-day.png) | [Daily modal](es-419-same-day.png) | Zero `/chat/stream` requests; two completed runs; workspace counter 2/2 |
| Visitor-day reset, then cleared history | [Workspace modal](en-next-day.png) | [Workspace modal](es-419-next-day.png) | Actual final SSE contains `final_response_payload.code=account_conversion_required`; one failed receipt, zero runs; counter remains 2/2 |

All four screenshots were visually inspected. Both browser journeys assert the corresponding existing localized copy and zero page errors. The daily modal describes today's limit and reset; the workspace modal describes the workspace limit and expiry. The journeys do not intercept or modify network responses.

The `*-state.json` files retain before/after database state, allowance responses, modal text, requests, and errors. `*-summary.json` records each completed run and refusal. The two `*-next-day.sse` files contain the browser's actual response. `*-failure-boundary.json` shows that the execute output's code now survives graph model validation.

## Contract and regression checks

- Red: both rejection and durable-receipt tests failed at the missing public `code` before the field was added. Three legacy payload cases already passed. See [red.txt](red.txt).
- Green: **138 focused tests passed**, covering execute, typed graph state, checkpoint serialization, public projection/SSE, legacy success/error/job payloads, workflow/recovery, and the prompt freeze. See [focused.txt](focused.txt).
- **100 mocked eval checks passed.** See [mocked-evals.txt](mocked-evals.txt). No paid interpreter calls were made for this deterministic transport correction.
- Prompt fingerprint: **zero changed, added, or removed surfaces**. See [prompt-comparison.json](prompt-comparison.json). `FinalResponsePayload` is graph output; the interpreter uses `LLMInterpretationResponse` and does not consume this output schema.
- Existing typed state consumers, checkpoint serde registration, result projection, API persistence, and frontend readers were audited. The added field is optional and nullable. Specific-field readers tolerate it, and old payloads still hydrate. No database migration or OpenAPI endpoint schema change is required.
- Ruff, whitespace checks, and modularity checks passed. The optimized frontend build passed. Logs are retained here.

The new regression test crosses the boundary the earlier test missed: execute → graph validation → checkpoint round trip → public projection → final SSE. It tests the historical rejection envelope and current durable-receipt envelope with a shared parametrized case.

## History and separate defect

The workspace-limit recovery path **never worked in #354**. It added the bridge and detector without adding this typed field. Its backend proof inspected the stage patch before graph validation. Its browser fixture exhausted the current visitor day, so it passed through the working daily precheck modal. We tested the wrong path and it looked green. The graph validation predates #354; no later removal caused this loss.

The [prior DOCN investigation](../docn-conversion/README.md) preserves source-exact production/integration failures and historical probes. #298's separate `/me/usage` change left browser availability observing only the visitor day while admission retained the workspace limit. That mismatch is filed as [#546](https://github.com/lagarcess/argus/issues/546) and remains outside this fix. Guest limit two is deliberate.

## Provenance and review

- Original integration base and refreshed remote integration: `77be94d68ae2217f43148883fc8c56348c4a40dc`.
- No intervening integration changes; no reconciliation merge or semantic overlap. The candidate is already based on the current integration tree. Modularity was checked on that would-be merged tree.
- Browser/source commit: `5cecbe43d87f1e624f102789e5f98aa82774e81a`. All **1,242** inventoried Python, JS/TS/TSX, JSON, and CSS files in the archived source were compared with Git objects after the build: zero differences. See [source-verification.json](source-verification.json).
- Later commits in this lane add evidence only; runtime, frontend, tests, and dependency manifests are revalidated unchanged from the capture commit. The final PR head and terminal CI state are recorded on [PR #547](https://github.com/lagarcess/argus/pull/547).
- Independent read-only review of `1ccfd233..5cecbe43` returned **no actionable findings** before this report was written. It checked backward compatibility, all payload consumers, checkpoint/SSE transport, receipt preservation, daily precheck isolation, and prompt-surface impact. No review remains in flight from this local review.

These are local browser acceptance results, not hosted deployment acceptance. The harness uses fixture authentication with real disposable guest owners, the unmodified API/graph/gateway and PostgreSQL admission, synthetic unit market data with the real engine, and a memory checkpointer. Workflow dispatch is disabled for local synchronous execution; refusal returns before dispatch. Synthetic price results do not establish market-data accuracy. No production requests or writes were made. See [manifest.json](manifest.json).

The harness moves the disposable visitor-day row to the prior UTC day and calls real `replace_guest_conversation`; it does not alter workspace usage or manufacture the first two run charges. Each locale uses a fresh guest. Both guest owners were deleted and the local API, frontend, and disposable database containers stopped after acceptance.

The [harness files](harness/) assume repository-root execution, candidate source under `temp/542-conversion-fix/candidate`, and output under `temp/542-conversion-fix/evidence`. Reuse the prior investigation's [migration harness](../docn-conversion/harness/migrate.py) for the disposable Supabase PostgreSQL/PostgREST pair. `server.py` accepts the candidate directory, trace path, and locale; `browser.cjs` accepts `en` or `es-419`. Ports are loopback-only: PostgreSQL 55482, PostgREST 55481, API 55479, frontend 55480.

**Disposition:** PR #547 targets `codex/private-alpha-next`. No merge or deploy is authorized by this report. #542 stays open until this fix lands.
