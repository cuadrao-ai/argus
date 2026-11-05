# Cuadrao auth and recovery operational audit, 2026-10-05

Read-only audit for #832, scoped to #671 and #676. Baseline is fetched `origin/codex/private-alpha-next` at `7018e0edebbc370b999005a857230bf3c3a1ad8b`. Shared checkout HEAD is `a9286b21886eb03df7a21f2f4b7d5e79af570679`; baseline sources were extracted with `git archive` to `/private/tmp/cuadrao-auth-rate-baseline-20261005` before reproduction. No repository writes, accounts, hosted changes, provider calls, root.env, PostgreSQL or Mac/device use.

Throughput checkpoint: n/a, read-only investigation. Poteto investigation/how/unslop guidance read. This bounded delegate performed direct explanation without recursive delegation.

## Outcome

#676 is a reachable defect in the selected consumer release. With the trusted header fixed, rotating the first XFF hop and email let all 6 of 6 synthetic requests reach the recovery sender; fixed XFF stopped request 6. Same-email throttling and the process-global cap still work. This is a bypass of the per-address layer, not unlimited email sends or a CAPTCHA bypass.

#671 remains a real process-local counter limitation. Two independent limiter instances accept twice the per-process allowance; reset admits a fresh attempt. Its issue records a September 25 deferral and says not to start until scheduled. Current Cuadrao master-plan B7 explicitly requires its disposition before public launch. #832 requires actual deployed worker counts and bounds, which this audit cannot establish from repository configuration. Do not claim #671 closed, accept a fleet-wide limit, or build a shared store without a bounded assignment.

## Reachability and current owners

- Native password login/signup use `ios/Packages/ArgusSession/Sources/ArgusSession/SessionController.swift:40,51`, paths `auth/login` and `auth/signup`, so API limits apply to iOS as well as web password entry.
- The connected iOS app opens web recovery: `ios/ArgusFoundation/Auth/NativeAuthConfiguration.swift:40`, `ios/ArgusFoundation/Connected/ConnectedCuadraoAuth.swift:380`. The proposal-only native recovery screen does not replace this path.
- `web/lib/auth-security.ts:141` sends to `/api/auth/recovery`. `web/app/api/auth/recovery/route.ts` owns module-level recovery limiters and the provider adapter. `web/lib/recovery-request.ts:178` owns the inconsistent client-address read.
- API auth delegates `auth._client_identity` to `guest_access.client_identity`, then `src/argus/api/client_ip.py:resolve_client_ip`. That owner reads `ARGUS_TRUSTED_CLIENT_IP_HEADER`, default `CF-Connecting-IP`, ignores XFF, canonicalizes addresses and falls back to socket peer. IPv6 is grouped by /64, IPv4-mapped IPv6 becomes IPv4. This is the existing API behavior, not proof of deployed edge sanitization.
- The analytics 20/10-minute endpoint cited in old #671 is absent at this baseline: `src/argus/api/routers/analytics.py` and its route wiring are gone. A stale browser-test interceptor is not a reachable production endpoint. Do not carry its old limit into the current auth count.

## Exact source limits

All windows below are 10 minutes, counters are local to their owning process.

| Owner/action | Per-process allowance | Key |
| --- | ---: | --- |
| API login | 8 | normalized email AND trusted client IP, independently |
| API signup, direct and guest conversion | 5 | normalized email AND trusted client IP, independently; both signup paths share action bucket |
| API access request | 5 | normalized email AND trusted client IP, independently |
| API guest session creation | 5 | trusted client IP |
| API guest handoff creation | 5 | destination email AND trusted client IP, independently |
| Web recovery | 5 | normalized email AND current spoofable address, independently |
| Web recovery global | 100 | one process-global key |

Source: `src/argus/api/routers/auth.py:56-68,112-165`, `web/app/api/auth/recovery/route.ts:8-20`. Guest session reuse returns before the creation limiter, by design. Successful calls to the limiter record attempts before the provider call, so failed authentication/provider outcomes also consume attempts. Recovery additionally bounds active tracked keys at 2,048, body at 8,192 bytes, email at 254 chars, CAPTCHA at 4,096 chars, and validates origin and address syntax. API compaction removes expired keys but is not a hard active-key limit.

For A simultaneously active API processes and W web recovery processes, the theoretical no-restart aggregate allowances are 8A for a login key, 5A for each 5-attempt API action key, 5W for a recovery key, and 100W recovery attempts globally per 10 minutes. Load distribution affects the actually attainable total. Restarts/deploys reset state; these formulas are not durable fleet-wide caps.

## Reproduction

Run from this workspace using the retained synthetic files:

```
bun /private/tmp/cuadrao-auth-rate-baseline-20261005/repro.ts
.venv/bin/python /private/tmp/cuadrao-auth-rate-baseline-20261005/repro.py
```

The TS script imports the unmodified baseline recovery handler and injects a sender that only increments a local integer. All addresses are documentation addresses, all emails use example.test, and CAPTCHA is a synthetic string. Results:

| Scenario | Requests | 202 | 429 | Sender calls |
| --- | ---: | ---: | ---: | ---: |
| Fixed XFF, rotating email | 6 | 5 | 1 | 5 |
| Rotating XFF + email, fixed CF-Connecting-IP | 6 | 6 | 0 | 6 |
| Rotating XFF, fixed email | 6 | 5 | 1 | 5 |
| Rotating XFF + email, global guard | 101 | 100 | 1 | 100 |

The Python script imports the baseline limiter and client-IP owner directly, avoiding app startup and environment loaders. For limit 5, each of two instances admitted 5, total 10; for limit 8, each admitted 8, total 16. Reset admitted a fresh attempt. A generic limit-20 example admitted 40 across two instances, but this does NOT establish a currently reachable analytics route. Rotating XFF with fixed trusted header produced the same API identity twice. These are isolated runtime reproductions, not a deployed request test or a full application suite.

## Deployment and mitigation evidence limits

`render.yaml:12` starts Uvicorn without `--workers`. No `WEB_CONCURRENCY`, `numInstances`, autoscaling or explicit worker count is declared in the baseline blueprint. The web service starts `bun run start -- -p $PORT` at line 211. Neither proves actual deployed process counts, instance counts, overlap during deploy, or dashboard overrides. Baseline blueprint branch is `main`, so integration source is not evidence of the deployed SHA.

`ARGUS_TRUSTED_CLIENT_IP_HEADER=CF-Connecting-IP` is declared for the API at line 134, not for the web service. `renderSubdomainPolicy: disabled` is declared for the API. The live edge overwrite/path behavior and actual overrides were not inspected. No Render management connector was available in tool discovery, and this audit did not open credentials or root.env to invent one.

The #671 issue records Supabase Turnstile enabled and anonymous creation at 30/hour/IP in its historical audit. That is a known recorded mitigation, not a fresh readback. Source forwards CAPTCHA on API login/signup/guest creation and web recovery, preserves recovery generic responses, and enforces local limits. Actual current Supabase CAPTCHA/rate-limit settings require an authorized sanitized configuration readback. The provider's anonymous-IP limit must not be described as a fleet-wide application cap without knowing what IP the provider sees from the server-side call.

## Smallest proposed implementation slice

Assign #676 to one web writer. Allowed owners: `web/lib/recovery-request.ts`, focused recovery tests, and the web route/config declaration only if needed to pass the already-named trusted-header setting. Replace the first-XFF/x-real-ip choice with the trusted-header contract used by the API. The web boundary has no socket peer on a standard Request; preserve a stable unknown bucket when no trusted value is available, never fall back to XFF. Keep invalid-address rejection and existing request/provider behavior. Explicitly define the header setting/default in the bounded contract so the API and web deployment cannot choose different headers silently. Do not copy the Python parser wholesale or change IPv6 policy incidentally.

Acceptance: fixed trusted header plus rotated XFF AND varied emails yields 5 sender calls and sixth 429; rotated XFF with fixed email remains bounded; missing and invalid trusted-header behavior is explicit; custom configured header is tested if supported; existing origin, CAPTCHA, generic response, global cap and key-cap tests pass. Provider adapter remains mocked. A deterministic pass closes the code defect only. Deployed trusted-header sanitization remains a release/edge check under #694 and actual runtime verification under #832.

No-touch: Python shared auth/session, account deletion, native app, schemas/migrations, quota/daily usage owner, analytics/events, provider configuration, actual deployment, or shared storage for #671. No merge or promotion.

## Remaining gates

1. Capture sanitized actual API and web deploy identities, active instances and worker processes, including deployment overlap and restart behavior.
2. Read current allowed provider protections without exposing secrets, then accept the effective bounds or assign a shared-counter design under #671.
3. Verify trusted header overwrite on every allowed public ingress path in the approved promotion window; #686/#694 remain promotion obligations, not an invented prerequisite to local candidate testing.
4. After #676 lands and is deployed through authorized release work, verify web recovery at its named runtime boundary. This audit sent zero provider requests and establishes no physical-device or hosted acceptance.

Live issues read: https://github.com/lagarcess/argus/issues/671, https://github.com/lagarcess/argus/issues/676, https://github.com/lagarcess/argus/issues/832. Current authority: baseline Cuadrao master plan B7, rows 8 and B7 public-launch list; MVEE consumer/business launch boundary; DOCUMENTATION_AUTHORITY; API_CONTRACT recovery/session ownership. No issues were modified or closed.

Cleanup: no long-running process or shared resource created. Temporary baseline extracts and synthetic reproductions retained beside this sanitized report for the release captain to inspect. Repository remained clean at audit completion.
