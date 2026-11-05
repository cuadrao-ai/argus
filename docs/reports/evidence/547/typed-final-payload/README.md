# Typed final-payload review follow-up

Codex's [review finding](https://github.com/lagarcess/argus/pull/547#discussion_r3939147748) was valid: the frontend's canonical `ChatFinalPayload` omitted `final_response_payload`, so the conversion detector read the nested code through an untyped cast. The frontend now imports a nested type generated from the backend `FinalResponsePayload`; a freshness check makes the Python model its owner. The detector reads the typed event directly. Old top-level codes remain supported.

The backend `code` fix and #543's durable refusal receipt remain intact. This PR does **not** close #542: it remains open until both #543 and #547 are in production. The separate daily/workspace availability mismatch remains #546.

## Browser acceptance after the review fix

Fresh optimized build and captures at `c29e56b18bba55c0429b100de72d1bba721bebb5`, including the one-way integration reconciliation. All four captures were visually inspected.

| Third Run | English | Spanish | Observed behavior |
| --- | --- | --- | --- |
| Same day after two completed runs | [Sign up](en-same-day.png) | [Registrarse](es-419-same-day.png) | Daily modal; no stream request; two jobs and runs |
| Daily reset and cleared history | [Sign up](en-next-day.png) | [Registrarse](es-419-next-day.png) | Workspace modal; final SSE retains the code; one failed receipt and no runs |

Each locale completed two real engine runs before either third-click check. Both counters reached 2/2 naturally and stayed there on rejection. The reset fixture moves only the visitor-day row to yesterday, then invokes real `replace_guest_conversation`; it never clears the workspace counter. Each browser `/me` response reports `public_account_access_enabled=true`. All four dialogs assert the localized signup heading, button, password field, correct limit copy, and absence of request-access/approval copy. Zero page errors. No signup form was submitted.

The earlier request-access screenshots were an acceptance configuration false alarm: the harness forced `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=false`, while the founder confirmed production uses true. Our acceptance environment did not match production. The existing flag branch is correct for both daily and workspace variants. This repeats #354's wrong-path proof pattern: its daily-modal browser success did not test the workspace rejection lost at graph validation. Both lessons are recorded in the PR description as well as the [earlier evidence](../../542/conversion-fix/public-signup/README.md).

The `*-state.json` files preserve database state, actual `/me` and usage responses, modal text and requests. The `.sse` files are actual browser responses, and the failure-boundary files record typed graph validation. No response interception or injected conversion code was used.

## Verification and scope

- [148 focused backend checks](reconciled-backend.txt) passed, including graph validation, checkpoint/SSE transport, legacy payloads, generated type freshness, prompt fingerprints, and the intervening integration's observability tests.
- [100 mocked eval checks](reconciled-mocked-evals.txt) passed. No paid providers were called.
- [1,519 frontend tests](frontend-full.txt) passed. This includes a compiler probe importing the real `ChatFinalPayload`, the guest recovery cases, and the updated existing ChatInterface wiring assertion. The first CI pass caught that assertion's obsolete cast-variable name; updating it required no product change.
- [Red compiler diagnostics](frontend-contract-red.txt) show the missing nested field before the correction. The focused consumer compile is enforced in the normal Bun suite. A repository-wide standalone `tsc` invocation still encounters existing Bun test declaration errors; it is not claimed green here.
- [Optimized Next build](build.txt), Ruff, changed-file ESLint, and [modularity on the reconciled tree](reconciled-modularity.txt) passed. Prompt-freeze tests remain green; this lane changes no model-facing prompt/schema text.

Original integration base: `77be94d68ae2217f43148883fc8c56348c4a40dc`. Refreshed integration: `dcbc7af5420d5d5dc41371bc1add9fef57c4582c`. Reconciliation merge and browser capture: `c29e56b18bba55c0429b100de72d1bba721bebb5`. The intervening #550 change adds interpreter repair observability and renames its preflight task. It does not change final graph payload serialization, allowance/admission, conversion state, frontend, migrations, or public signup configuration. No conversion acceptance was invalidated by semantic overlap; the four paths were nevertheless recaptured after the typed frontend correction and reconciliation.

All 1,269 inventoried source files in the tested archive matched the capture commit's Git objects; see [source-verification.json](source-verification.json). The following packaging commit changes only evidence and the existing source-wiring test assertion. Product sources and dependency manifests are explicitly revalidated against the final PR head. Final CI and external Codex review disposition will be recorded on [PR #547](https://github.com/lagarcess/argus/pull/547) after the review finishes; this acceptance report is not a terminal review audit.

## Local fixture provenance

See [manifest.json](manifest.json). The API uses fixture authentication with disposable real guest rows, unmodified graph/gateway/PostgreSQL admission, a memory checkpointer, and synthetic market data through the real backtest engine. Dispatch is disabled for local synchronous execution; workspace rejection occurs before dispatch. The optimized frontend was rebuilt from the capture commit. This proves local conversion behavior under the production flag value supplied by the founder; it is not a hosted canary or a fresh Render configuration read. Production was not accessed or changed.

Both guests were deleted; API/frontend services and disposable PostgreSQL/PostgREST containers were stopped and removed. Reproduction follows the [original migration setup](../../542/docn-conversion/harness/migrate.py). Put the [harness](harness/) under `temp/547-review-contract/` with the candidate archive at `temp/547-review-contract/candidate`. Explicitly supply `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=true` when starting `server.py <candidate> <trace> <en|es-419>`; then run `node temp/547-review-contract/browser.cjs <en|es-419>`. Ports remain loopback-only (55479–55482).
