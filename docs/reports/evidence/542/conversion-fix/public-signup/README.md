# Public-signup branch acceptance correction

The modal branch is correct. The earlier acceptance API harness explicitly set `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=false`; its browser assertions also selected the request-access translations. That was an acceptance configuration error. The transport proof stands, but those screenshots did not represent the public-signup configuration the founder confirmed for production.

No product code was changed for this correction. The same compiled frontend now renders the signup form when the local API flag is true. Both third-run paths pass in both languages.

| Third-run path | English | Spanish | Browser/API evidence |
| --- | --- | --- | --- |
| Two runs used today | [Create your account / Sign up](en-same-day.png) | [Crea tu cuenta / Registrarse](es-419-same-day.png) | `/me.public_account_access_enabled=true`; daily copy; zero chat stream requests |
| Daily reset, then cleared history | [Create your account / Sign up](en-next-day.png) | [Crea tu cuenta / Registrarse](es-419-next-day.png) | `/me.public_account_access_enabled=true`; workspace copy; actual final SSE retains the conversion code |

All four captures assert the localized create-account heading, signup button, password field, correct limit/reset copy, and absence of the request-access heading and approval-queue description. All were visually inspected. Zero browser page errors. No signup submission or email request was made; this verifies which conversion form is offered.

## What selects the branch

1. [`public_account_access_enabled()`](https://github.com/lagarcess/argus/blob/5cecbe43d87f1e624f102789e5f98aa82774e81a/src/argus/api/guest_access.py#L37) reads `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED` on the server.
2. [`_user_response`](https://github.com/lagarcess/argus/blob/5cecbe43d87f1e624f102789e5f98aa82774e81a/src/argus/api/routers/profile.py#L58) includes it in `/me` as `public_account_access_enabled`. Unlike the formerly missing final-response code, this field is declared in both Python `UserResponse` and the frontend type.
3. `getMe()` reads `/me`; `ChatInterface` stores that response as `account` and passes it into `useGuestExperience` and `useGuestConversion`.
4. [`useGuestConversion`](https://github.com/lagarcess/argus/blob/5cecbe43d87f1e624f102789e5f98aa82774e81a/web/components/guest/useGuestConversion.ts#L236) returns `account?.public_account_access_enabled ?? false`; `GuestExperienceSurfaces` passes that value to `GuestConversionModal`.
5. [`GuestConversionModal`](https://github.com/lagarcess/argus/blob/5cecbe43d87f1e624f102789e5f98aa82774e81a/web/components/guest/GuestConversionModal.tsx#L44) uses the prop for both the form mode and limit copy. With true, daily uses `simulation_limit_reset` and workspace uses `simulation_workspace_limit_reset`. With false, both use their `_request_access` counterparts and the request form. Both simulation triggers request the initial `signup` mode.

The modal does not read a separate browser build flag. It derives from the API response. The [earlier committed harness](https://github.com/lagarcess/argus/blob/b25228262a92f949d69845c5745a37810f569be0/docs/reports/evidence/542/conversion-fix/harness/server.py#L14) forced the server flag false. It was therefore expected to show the gated-access branch, regardless of production's actual flag.

## Configuration and evidence

- Source/browser code: `5cecbe43d87f1e624f102789e5f98aa82774e81a`; current pre-correction PR head `b25228262a92f949d69845c5745a37810f569be0` has identical product code, tests, and dependencies.
- Integration base remains `77be94d68ae2217f43148883fc8c56348c4a40dc`; no reconciliation or overlap.
- Reused the existing optimized Next build. The only product setting changed from the preceding acceptance run is `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=true` on the local API. No frontend rebuild, source patch, network interception, or injected response code was used.
- The revised [server harness](harness/server.py) requires the public-access flag to be explicitly supplied by the caller instead of forcing false. The [browser harness](harness/browser.cjs) fails unless both its initial `/me` read and every captured browser `/me` response report true. It also checks the actual rendered signup form and rejects approval-queue copy.
- Each language used a fresh disposable guest, completed two real engine runs with synthetic market data and real PostgreSQL admission, then clicked Run a third time. For the second path, the harness moved the visitor-day counter to the prior UTC day and called real `replace_guest_conversation`. Workspace usage stayed 2/2.
- The next-day refusal still leaves one failed job with `account_conversion_required`, zero completed runs after history clear, and no added allowance charge. #543's durable-receipt behavior and the `FinalResponsePayload.code` fix are preserved.
- Product/runtime source remains byte-identical to the captured code commit; see [source-verification.json](source-verification.json). Previous focused tests, mocked evals, prompt-freeze comparison, independent code review, and successful product CI remain applicable. Final evidence head and CI status are recorded on [PR #547](https://github.com/lagarcess/argus/pull/547).

The `*-state.json` files include actual browser `/me` responses, usage responses, modal text, counters, requests, and page errors. The two next-day `.sse` captures are actual browser responses; the boundary files show the code surviving typed graph validation. See [manifest.json](manifest.json) for fixture/runtime details.

This is local acceptance against the production public-signup setting supplied by the founder, not a hosted production signup test or an independent reread of Render configuration. Production was not accessed or changed. Both fixture guests, local servers, and disposable PostgreSQL/PostgREST containers were cleaned up.

Reproduction uses the same migration and compiled-candidate setup documented in the [original evidence](../README.md). Place the new harness under `temp/542-public-signup`, retain the candidate under `temp/542-conversion-fix/candidate`, and start each locale with `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=true .venv/bin/python temp/542-public-signup/server.py temp/542-conversion-fix/candidate temp/542-public-signup/evidence/<locale>-trace.jsonl <locale>`. Then run `node temp/542-public-signup/browser.cjs <locale>`. Supported locales are `en` and `es-419`.

**Disposition:** evidence correction only. PR #547 remains unmerged; #542 remains open. The separate allowance-availability defect remains #546.
