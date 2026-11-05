# Native readiness audit

**Status:** Read-only investigation report. It proposes work; it does not approve
contracts, select providers, or change the canonical architecture, API, or data
model documents.
**Date:** 2026-09-27
**Question:** How can Argus's existing backend and web capabilities support the
approved native iOS/Android clients and the
[minimum viable ecosystem experience (MVEE)](../specs/argus-minimum-viable-ecosystem-experience.md),
while the existing web/PWA and its behavior are retained?

## 1. Scope, inspected source, and limits

| Item | Value |
| --- | --- |
| Inspected base | `origin/codex/private-alpha-next` at `ab9143c18740c28f582646d405445c01c4c8aff4` ("docs(product): lock MVEE and replace conflicting product guidance (#704)", 2026-09-26) |
| Worktree / branch | Sibling managed worktree, branch `codex/native-readiness-audit` created from the fetched base |
| Reconciliation | Base later advanced to `2ea968156e0c664b9a9ba2fd540b51e20973ab3a` ([PR #706](https://github.com/lagarcess/argus/pull/706), private log content). It was merged in one way. It changes logging code this report does not cite and one `docs/API_CONTRACT.md` line in place, so no cited path or line number moved and findings stand as audited at `ab9143c` |
| Environment | Cloud container; source reading only. No services started, no provider calls, no Supabase or Render access, no package installation |
| Assignment direction | iOS: Swift + SwiftUI (UIKit where needed). Android: Kotlin + Jetpack Compose (Android Views where needed). Web/PWA retained. Shared backend, records, permissions, calculations, and conversational runtime |

**Evidence classes used in this report.**

- **Documented**: stated in a canon or contract document. It may describe intent.
- **Implemented**: present in source at the inspected SHA. Statements cite `path:line`.
- **Inferred**: follows from reading code paths but was not executed in this audit.
- **Deployed**: *not verified for anything in this report.* The Render MCP connection failed
  (`ERR_PROXY_TUNNEL`), production access is out of scope, and branch contents do not prove deployment.
  Hosted Supabase Auth settings (captcha provider, JWT lifetime, refresh-token rotation, redirect
  allow-list, email templates) live in the Supabase dashboard and were not inspected. The local
  `supabase/config.toml` disables captcha and uses `jwt_expiry = 3600`; hosted values may differ.

**Short file names.** After first mention, `auth.py`, `conversations.py`, and `agent.py` mean the
modules under `src/argus/api/routers/`; `schemas.py` and `dependencies.py` mean
`src/argus/api/schemas.py` and `src/argus/api/dependencies.py`; bare `web` TypeScript names are under
`web/lib/`.

**Native stack: approved, not yet published on the base branch.** The founder has approved the
native stacks named above. Their documentation exists on a separate local branch that has not
reached `codex/private-alpha-next` and was not inspected for this report. At the inspected SHA,
[PRODUCT.md §4](../PRODUCT.md#4-product-principles),
[MVEE §2](../specs/argus-minimum-viable-ecosystem-experience.md#2-product-character-and-platforms),
the [decision log](../specs/argus-decision-log.md) (2026-09-26 row), and
[ARCHITECTURE.md §5](../ARCHITECTURE.md#5-frontend-architecture) ("does not yet select native
frameworks") record native iOS/Android intent without naming frameworks, and
[DOCUMENTATION_AUTHORITY.md](../DOCUMENTATION_AUTHORITY.md#what-remains-technical-or-undecided)
still lists native app architecture as open. The framework choice is therefore not an open
question; publishing that documentation and reconciling these pointers is outstanding work (R0
below). This report uses the assignment direction as its scope and does not edit those documents.

## 2. Summary

- **The transport is largely client-neutral; end-to-end native compatibility is unverified.**
  Every product route resolves identity through one dependency that accepts
  `Authorization: Bearer <Supabase access token>` before any cookie
  (`src/argus/api/dependencies.py:419`), verifies the token with Supabase, and checks that the
  session row still exists (`dependencies.py:470`). That establishes reuse potential for
  conversations, messages, activity, chat streaming, jobs, runs, history, search, computations,
  decisions, discovery, profile, usage, and feedback. No native or bearer-only client was run
  against these routes in this audit; WP-A and WP-B define the evidence that would confirm it.
- **Authentication is the largest integration gap.** Guest start, sign-in, and sign-up each
  require a Cloudflare Turnstile token, and the only implemented way to obtain one is the web
  widget. Guest conversion carries its secret in HttpOnly cookies. Token refresh, sign-out
  revocation, password change, and password recovery run in the browser's Supabase client or a
  Next.js route, not in the Argus API. Each has a plausible native integration path; none is built.
- **Chat streaming is simple to consume** (data-only SSE, `[DONE]` terminator, keepalive comments,
  RFC 9457 errors), and the documented reconnect rule is "re-fetch messages". Mobile backgrounding
  makes the disconnect path common. What a phone user sees after an interrupted turn is inferred
  from code in this report and has not been measured.
- **Cards render from structured payloads, not prose**, but the wire types are not machine-published
  (message `metadata` and SSE frames are untyped in OpenAPI), and a meaningful share of display
  composition (result readout fallback, recovery copy, recovery actions, localized labels) lives in
  web TypeScript and the web i18n catalog. Porting that logic twice would create three copies of one fact.
- **No upload or file-ingestion capability was found.** Financial accounts, transactions, plans,
  households, sharing permissions, and device registration have no implemented contract at the
  inspected SHA. Notifications keep their documented status in PRODUCT.md; §5 records what this
  search did and did not find. These remain open and are not native prerequisites.

## 3. Capability table

Status key: **Reuse candidate** = no browser dependency found in the request path, so a native
client should be able to call it unchanged; not yet exercised by a native or bearer-only client.
**Adapt** = a bounded integration or contract adaptation is needed. **Missing** = no implemented
capability found at the inspected SHA.

| Capability | Current owner | Endpoint / payload | Browser dependency | Status | Source evidence |
| --- | --- | --- | --- | --- | --- |
| Identity resolution | `current_user` dependency | `Authorization: Bearer` or `sb-*auth-token` cookie; 401/403/503 Problem Details | Cookie fallback only | Reuse candidate | `src/argus/api/dependencies.py:393-533` |
| Session liveness | `auth_session_is_active` | Reads `auth.sessions` by JWT `session_id` | None | Reuse candidate | `src/argus/api/auth_sessions.py:27-76` |
| Guest start | `POST /auth/guest` | `{captcha_token, language}` → Supabase session JSON + cookies | Turnstile widget for token | **Adapt** | `src/argus/api/routers/auth.py:184-290`; `src/argus/api/schemas.py:1057-1059`; `web/lib/guest-captcha.ts:1-35` |
| Sign-in / sign-up | `POST /auth/login`, `POST /auth/signup` | `{email, password, captcha_token}` → `{user, session}` | Turnstile; response also sets cookies | **Adapt** | `auth.py:746-920`; `schemas.py:983-1003` |
| Guest conversion | `POST /auth/guest/handoffs`, `/auth/guest/signup`, `/auth/login`, `/claim` | Handoff id and secret in HttpOnly cookies, `path=/api/v1/auth` | Cookie jar | **Adapt** | `auth.py:298-392`, `auth.py:603-604`, `auth.py:861-862` |
| Token refresh | Browser Supabase client | Supabase Auth `refresh_token` grant, anon key | `@supabase/ssr` browser storage | **Adapt** | `web/lib/argus-api-transport.ts:33-53`; `web/lib/supabase-client.ts`; `web/lib/argus-api.ts:570-590` |
| Logout / revoke | Browser Supabase `signOut` + `POST /auth/logout` | Backend only deletes cookies | Browser client | **Adapt** | `auth.py:940-946`; `web/lib/argus-api.ts:711-719`; `web/lib/auth-security.ts:44-80` |
| Password change / recovery | Supabase `updateUser`; Next.js `POST /api/auth/recovery` | Recovery link targets web `/auth/recovery` | Next route, web origin | **Adapt** | `web/lib/auth-security.ts:97-150`; `web/app/api/auth/recovery/route.ts`; `supabase/config.toml:165-175` |
| Profile, usage, market session | `profile`, `market` routers | `GET/PATCH /me`, `GET /me/usage`, `GET /market/session`; returns `account_kind`, guest limits, `capabilities` | None | Reuse candidate | `src/argus/api/routers/profile.py:50-67`; `docs/API_CONTRACT.md` §8 |
| Conversations | `conversations` router | CRUD, `/guest/replace`, cursor pages | None | Reuse candidate | `src/argus/api/routers/conversations.py:169-530` |
| Messages / hydration | `GET /conversations/{id}/messages` | Cursor or `anchor_message_id`; `Message.metadata: dict[str, Any]` | None | Reuse candidate (untyped) | `conversations.py:666`; `schemas.py:324-330`; `docs/API_CONTRACT.md:3437` |
| Activity / attention | `conversation_activity` router | `latest_message_id`, `operation`, `attention`; `mark_read`/`mark_unread` | None | Reuse candidate | `src/argus/api/routers/conversation_activity.py:68-110`; `docs/API_CONTRACT.md:3259-3341` |
| Chat turn stream | `POST /chat/stream` | `data:` frames `stage_start`, `token`, `stage_outcome`, `final`, `error`, then `[DONE]`; `: keepalive` comments; `Idempotency-Key`, `X-Request-Id` | None | Reuse candidate | `src/argus/api/routers/agent.py:265`; `src/argus/api/chat/streaming.py:7-16`; `docs/API_CONTRACT.md:3467` |
| Structured actions | `ChatActionPayload` | `{type, label?, labelKey?, payload}` with typed ids (confirmation, run) | None | Reuse candidate | `schemas.py:751-763`; `docs/API_CONTRACT.md:3589` |
| Confirmation edits | Confirmation routes | `/confirmations/{id}/direct-edit`, `/peer-assets` | None | Reuse candidate | `conversations.py:851`, `conversations.py:1092` |
| Tool-result cards and recompute | `tool_result_cards` + recompute route | Backend-localized `presentation`, sources, `repair` | None | Reuse candidate | `src/argus/domain/tool_contracts.py:86`, `:173`; `src/argus/api/routers/tool_results.py:56`; `docs/API_CONTRACT.md:3496-3587` |
| Backtest / research jobs | Backtest router | `GET /backtest-jobs/{id}`, `/by-action/{confirmation_id}`, `GET /backtests/{run_id}`; research answer as `result_message` | None (polling) | Reuse candidate | `src/argus/api/routers/backtest.py:613-719`; `docs/API_CONTRACT.md:5029-5075` |
| Run dossiers | Conversations router | `GET /conversations/{id}/run-dossiers` | None | Reuse candidate | `conversations.py:531`; `docs/API_CONTRACT.md:3354` |
| History / Recents | `GET /history` | Cursor pages with activity projection. A `chat` row's `id` is its conversation id; `conversation_id` is set on the guest workspace's chat row and, when known, on `run` rows; registered users' chat rows leave it null | None | Reuse candidate | `src/argus/api/routers/history.py:63`, `:101-111`, `:165`, `:235`; `schemas.py:523-536`; `web/lib/command-palette-items.ts:83-90` |
| Omnisearch | `GET /search` | Discriminated rows: `conversation` rows carry `conversation_id`, optional `match.message_id` and dossier anchors; `asset_rollup` rows are aggregates with no transcript anchor; ledger groups | None | Reuse candidate | `src/argus/api/routers/search.py:53`; `schemas.py:621-631`, `schemas.py:671-719`; `docs/API_CONTRACT.md:5816` |
| Computations / decisions | `computations`, `decisions`, `evidence` routers | answers list, compare, continue, refresh, rerun, decision save/open | None | Reuse candidate | `src/argus/api/routers/computations.py:46-104`; `src/argus/api/routers/decisions.py:28-135`; `src/argus/api/routers/evidence.py:16` |
| Composer mentions | `discovery` router | `GET /discovery/assets`, `/discovery/indicators` | None | Reuse candidate | `src/argus/api/routers/discovery.py:46-83` |
| Client capability handshake | `X-Argus-Client-Capabilities` | Additive presentation opt-in (`dossier_decision_conversion_v1`) | None | Reuse candidate | `src/argus/api/client_capabilities.py:9-49`; `web/lib/argus-api-transport.ts:13-31` |
| Result readout text | Web `result-readout-*` | Uses backend `result_readout_content` when its language matches; otherwise composes from `result_fact_bank` + web i18n | Web i18n catalog | **Adapt** | `web/lib/artifact-response-transport.ts:8-22`; `web/lib/result-readout-display.ts:16-40`; `docs/API_CONTRACT.md:5042-5051` |
| Recovery copy and actions | Web `chat-recovery-display.ts` | Derives display text and action options from typed metadata codes | Web i18n catalog | **Adapt** | `web/lib/chat-recovery-display.ts:103-700` (1,116 lines) |
| Localized labels | Web i18n catalog (1,723 `en` keys) | Backend emits `locale_key` / `label_key` into that namespace | Bundled with web | **Adapt** | `web/public/locales/en/common.json`; `docs/API_CONTRACT.md:3513-3517` |
| Shared display policy | `argus_display_contract` package | JSON read by backend and web build | None | Reuse candidate | `web/argus_display_contract/result_display_policy.json`; `src/argus/domain/result_money.py:19`; `pyproject.toml:10` |
| Temporary chat (memory opt-out) | Web localStorage | `memory_opt_out` flag per request | `localStorage` | **Adapt** | `web/lib/browser-storage.ts:33-46`; `web/lib/argus-api.ts:1041`; `schemas.py:840-842` |
| Memory controls | `personalization_memory` router | role-gated settings, records, export JSON | None | Reuse candidate | `src/argus/api/routers/personalization_memory.py:108-379` |
| Feedback | `POST /feedback` | Text + bounded context; no attachments | None | Reuse candidate | `src/argus/api/routers/feedback.py:19`; `schemas.py:953-968` |
| Public receipts | `evidence_receipts`, `public_receipts` routers | Owner create/revoke; public view at web `/r/[receiptId]` | Web page for viewing | Reuse candidate | `src/argus/api/routers/evidence_receipts.py:145-357`; `web/app/r/` |
| File upload / ingestion | none | none | n/a | **Missing** | No `UploadFile`, multipart route, bucket, or file input found in `src/`, `web/`, or `supabase/migrations/` |
| Financial records, household, sharing | none | none | n/a | **Missing** | [DOCUMENTATION_AUTHORITY](../DOCUMENTATION_AUTHORITY.md#what-remains-technical-or-undecided) |
| Notifications / device registration | Documented as hidden/flagged for Alpha ([PRODUCT.md](../PRODUCT.md#current-production-availability-and-planned-changes)) | Not found by this search | n/a | **Not found at SHA** | Search scope and terms in §5; `src/argus/api/feedback_notification.py` only emails feedback to the team |
| Account deletion | Feedback type | `type: "account_deletion_request"` | None | **Adapt / decision** | `schemas.py:954` |

## 4. Answers to the eight questions

### 4.1 What native clients can consume unchanged

The `/api/v1` product routes marked **Reuse candidate** in the table. These are transport-level
findings from source reading; end-to-end compatibility still needs a bearer-only client run (WP-A
acceptance) and schema-validated payloads (WP-B). The shared properties behind the finding:

- Bearer auth is first-class (`dependencies.py:419-421`); cookies are a fallback.
- The auth-origin guard admits requests that carry no `Origin` header (`auth.py:923-937`), which is
  the normal native case. CORS is irrelevant to native HTTP clients.
- Errors are flat RFC 9457 bodies with `code` and `request_id` (`src/argus/api/app_setup.py:94-105`),
  plus `Retry-After` on 429.
- Navigation targets are ids, not web URLs, where a target exists. Search `conversation` rows,
  history chat rows, activity, and jobs return conversation, message, run, or job ids that native
  deep links can use. Two exceptions are covered in §4.6: search `asset_rollup` rows are aggregates
  with no transcript anchor, and registered users' history chat rows identify the conversation by
  `id` while leaving `conversation_id` null.
- Account class and capabilities come from the server (`profile.py:50-67`), so native gating can
  render them without re-deriving guest policy.
- The `X-Argus-Client-Capabilities` handshake already lets a client opt into additive presentation;
  native clients can declare the same tokens as they reach parity.

### 4.2 What depends on Next.js, cookies, storage, browser events, or frontend-only logic

| Dependency | Where | Native consequence |
| --- | --- | --- |
| Cloudflare Turnstile browser widget | `web/lib/guest-captcha.ts:1-35`; required by `schemas.py:986,1003,1058,1151` | No implemented native way to obtain the token yet; an integration gap, not an inherent barrier (§8.3 E1) |
| HttpOnly handoff cookies | `auth.py:343, 369-389, 417, 603-604, 861-862` | Guest conversion needs a cookie jar or another secret transport |
| Browser Supabase session storage and auto-refresh | `web/lib/supabase-client.ts`; `argus-api-transport.ts:40-48` | Native owns token storage and refresh |
| Next.js route for password recovery | `web/app/api/auth/recovery/route.ts`; `auth-security.ts:141` | Native recovery request has no Argus API endpoint |
| Web-origin email links | `supabase/config.toml:165-175`; no `web/public/.well-known/` | Confirmation and recovery links open the web, not the app |
| localStorage-only temporary chat | `browser-storage.ts:33-46`; `argus-api.ts:1041` | Opt-out does not follow the user across devices |
| Client-side readout, recovery, and action projection | `artifact-response-transport.ts:8-22`; `chat-recovery-display.ts` | Must be ported or moved server-side (§6 G6) |
| Web i18n catalog as key namespace | `web/public/locales/*/common.json` | Native needs the same keys or resolved strings |
| Markdown rendering policy | `web/components/chat/ChatMessage.tsx:272` (react-markdown, GFM) | Native renderers must match content and image policy ([#688](https://github.com/lagarcess/argus/issues/688)) |
| Tab/account-scope epochs | `web/lib/chat-request-session.ts:209-216` | Native needs equivalent account-scoped cache invalidation |

`web/proxy.ts` only hides a dev route in production and is not a native dependency.

### 4.3 Bounded adaptation for auth, refresh, logout, guest chat, and account switching

```text
Web today
 Browser ──Turnstile widget──▶ token
 Browser ──POST /auth/login {email,pw,captcha}──▶ Argus API ──▶ Supabase Auth
 Browser ◀── {user, session{access,refresh}} + Set-Cookie sb-* ──
 Browser ──supabase.auth.setSession()──▶ browser storage
 Browser ──Bearer access──▶ Argus API (every call)
 Browser ──supabase refresh (anon key)──▶ Supabase Auth          (no Argus API involvement)
 Browser ──supabase.auth.signOut()──▶ Supabase Auth (revokes)  + POST /auth/logout (clears cookies only)
```

- **Sign-in and sign-up**: the API returns the session in JSON (`argus-api.ts:570-590` reads it),
  so a native client can store tokens in Keychain/Keystore. The remaining gap for these routes is
  obtaining the captcha token (G1).
- **Refresh**: implemented only in the browser Supabase client. The smallest adaptation that matches
  today's web ownership is for native clients to refresh directly against Supabase Auth with the
  public URL and anon key, as the web does. The alternative is an Argus refresh endpoint. This is an
  engineering choice with a recommended default (§8.3 E2). Note that `supabase/config.toml:183-186` enables refresh-token
  rotation with a 10-second reuse window locally; concurrent refreshes from one app must be serialized.
- **Logout**: `POST /auth/logout` deletes cookies and does not revoke (`auth.py:940-946`). Revocation
  is a Supabase `signOut`. Because `current_user` checks `auth.sessions`, a revoked access token fails
  on the next call (`dependencies.py:470-490`). A native logout must revoke, not merely discard tokens.
- **Guest chat**: after guest start (G1), guest turns are ordinary bearer calls. Guest limits and
  capabilities arrive from `/me`. Guest allowances key on the trusted client IP
  (`src/argus/api/client_ip.py:1-15`, `src/argus/domain/visitor_usage.py:33-37`), the same for native and
  mobile web; this is existing behavior, not a native prerequisite.
- **Guest conversion**: the handoff secret is issued and read only as HttpOnly cookies. A native
  client with a persistent, per-account cookie jar could complete it without backend change, but
  the same jar would also capture `sb-auth-token` cookies that `current_user` accepts when no bearer
  is sent (`dependencies.py:422-445`). The smallest safe choices are (a) a jar limited to
  `/api/v1/auth` with `sb-*` cookies discarded, or (b) an additive body/header transport of the
  handoff secret for bearer clients. This is an engineering choice (§8.3 E3).
- **Account switching**: the server is stateless per request. The client must drop tokens, stop
  in-flight streams, and discard account-scoped caches before issuing a new identity. The web does
  this with an account epoch (`chat-request-session.ts:209-216`) and still has a stale-tab resend gap
  ([#688](https://github.com/lagarcess/argus/issues/688)).

### 4.4 Streaming, cancellation, reconnects, retries, errors, and hydration

```text
Native ──POST /chat/stream (Bearer, Idempotency-Key, X-Request-Id)──▶ API
  API: auth → validation → quota → durable user message + lifecycle row (accepted)
  API ──data: {"type":"stage_start"...}  data: {"type":"token"...}  ": keepalive"──▶ Native
  API ──data: {"type":"final","payload":{...message_id...}}  data: [DONE]──▶ Native
  On failure: data: {"type":"error", code, message, message_id, recovery, retry_last_turn?} then [DONE]

Disconnect ─▶ documented rule: GET /conversations/{id}/messages (no token replay)
           ─▶ GET /conversations/{id}/activity: compare latest_message_id, read operation status
           ─▶ run_backtest only: GET /backtest-jobs/by-action/{confirmation_id}
```

- **Implemented**: data-only frames and keepalives (`streaming.py:7-16`), a 120-second runtime event
  timeout (`agent.py:157`), durable lifecycle states and a 15-minute stale-turn reconciler that runs
  on the next POST or message read (`docs/API_CONTRACT.md:537-640`), and retry by
  `failed_assistant_id` (`docs/API_CONTRACT.md:3467-3494`).
- **Inferred from code, not executed or measured**: when the response generator closes, the threaded runtime worker is
  cancelled (`src/argus/api/chat/runtime_worker.py:111-125`). Only the result breakdown is explicitly
  shielded (`agent.py:1018`) and tested to survive disconnect (`tests/test_result_breakdown_jobs.py:60`).
  An ordinary turn cut off before its terminal message persists stays `running` until the reconciler
  marks it `abandoned` with a retry offer (`tests/test_chat_turn_route_matrix.py:1090`).
- **Phone impact (inferred, unmeasured)**: backgrounding the app during an answer is routine on iOS
  and Android. If the inference above holds, the user returns to a conversation shown as working for up to 15 minutes and
  then a retry prompt. A resend with a new `Idempotency-Key` spends another turn
  ([#700](https://github.com/lagarcess/argus/issues/700)). Mobile web shares this path.
- **User cancellation**: no stop-generation endpoint or web stop control was found; the web aborts
  requests on navigation or account change. Confirmation cancellation is a structured action
  (`src/argus/api/chat/cancellation.py`).
- **Async work**: backtests and thorough research are durable jobs; native polls
  `GET /backtest-jobs/{id}`, as the web does. Supabase Realtime is documented as the target but is
  not wired (`docs/API_CONTRACT.md:1879-1881`).

### 4.5 Rendering stages, cards, citations, assumptions, and actions from payloads

Yes for data, partially for presentation.

- **Authoritative and structured**: result cards and run facts, confirmation cards, tool-result
  cards (backend-localized `presentation`, per-fact `source`, typed `repair`), research sources,
  `next_experiments` rows with `label_key`, `send_text`, and typed reasons, recovery codes, and
  structured actions. No reviewed web path reconstructs strategy meaning from assistant prose.
- **Stages**: `stage_start` carries a stage name and, for tools, `{locale_key, interpolation_args}`;
  copy is chosen client-side from the web catalog.
- **Composed in the web client from typed facts**: the result Quick take and Breakdown fallback
  (`result-readout-display.ts:16-60`), recovery sentences and recovery action options
  (`chat-recovery-display.ts:103-700`), and assumption text. These are deterministic projections of
  typed data, not prose parsing, but they exist only in TypeScript.
- **Wire typing gap**: `Message.metadata` is `dict[str, Any]` (`schemas.py:330`), the SSE 200 body is
  `type: string` (`docs/api/openapi.yaml:461-463`), and the web hand-maintains its view types
  (`web/components/chat/types.ts`, 415 lines). Pydantic models already exist for several parts
  (`ToolResultCard`, `ToolProgress`, `ResearchSource`), but no published schema covers the envelopes.

### 4.6 How history, search, calculations, research, and backtests connect

Most results connect through ids that resolve to a conversation transcript. Aggregate results do not.

```text
/search conversation row ──conversation_id (always)
                          ──match.message_id (only when match.layer = "message")
                          ──dossier.run_id, dossier.result_message_id (optional)
                          ──answer_dossier.message_id (when a computed answer exists)──┐
/history chat row ──id (= conversation id), activity.latest_message_id──────────────────┤
job poll ──result_run_id (backtest) | result_message (research)──────────────────────┤
                                                                                      ▼
GET /conversations/{id}/messages[?anchor_message_id=…] → metadata.result_card / tool_result_cards / computation
GET /backtests/{run_id}, GET /conversations/{id}/run-dossiers, GET /decisions/{id}

/search asset_rollup row ──symbol, run_count, result_count, decision_counts, last_touched_at
                          (no conversation, message, or run id: not transcript-addressable)
```

- **Conversation search rows** always open a conversation. They open at a specific message only
  when the row carries a message anchor (`schemas.py:621-631`: `message_id` is present only for
  message-layer matches) or a dossier `result_message_id`. Otherwise a client opens the
  conversation at its default position.
- **Asset rollups** (`SearchAssetRollup`, `schemas.py:698-714`) summarize every result involving a
  symbol and carry no anchor. The web command palette renders the first rollup as a
  non-interactive summary and builds openable rows only from conversation items
  (`web/components/sidebar/ChatCommandPalette.tsx:522-584`,
  `web/components/sidebar/command-palette/AssetHistoryRollup.tsx`). No drill-down contract from a
  rollup to its runs exists; a native client should present it the same way unless one is defined.
- **History rows** do not use `conversation_id` uniformly. A `chat` row's `id` is the conversation
  id. Registered users' chat rows omit `conversation_id`, so it serializes as null
  (`history.py:165`, `history.py:235`); the guest workspace row sets it (`history.py:101-111`).
  `run` rows carry the run's `conversation_id`, which may be null (`history.py:159`, `:218`), and
  legacy `strategy`/`collection` rows have none. The web command palette opens only
  `chat` history rows and resolves them with `conversation_id ?? id`
  (`web/lib/command-palette-items.ts:83-90`). A native Recents client must use
  the same rule; reading only `conversation_id` would make ordinary chat rows unopenable. The API contract could instead require
  `conversation_id` on chat rows; that would be a contract change and is not proposed here.
- Computed answers carry `metadata.computation` and are listed by `GET /computations/answers`.

### 4.7 Uploads and files today versus planned ingestion

**Today:** none. No upload route, multipart handling, Storage bucket, migration touching
`storage.*`, or file input exists. Supabase Storage is enabled in local config with no buckets
(`supabase/config.toml:116-126`). Feedback accepts text and bounded JSON context only. The only
file-like output is `GET /memory/export` (JSON attachment) and public receipt pages.

**Planned (MVEE §4.4-4.5):** statements, CSV-type files, PDFs, images, camera scans. Provider,
format, retention, storage, extraction, review, and confirmation contracts are all undefined.
Native camera and document capture have nothing server-side to send to yet.

### 4.8 Existing contracts that support the pivot, and what remains undefined

**Supports:** bearer identity, owner-scoped conversations and messages, durable turn lifecycle,
structured actions with confirmation cards (a working capture → review → confirm pattern for
simulations), tool-result cards with sources and recompute, jobs, Omnisearch with typed rows and
dossiers, computed answers and decisions, the client-capability handshake, Problem Details, and the
shared display-policy package.

**No implemented contract found:** financial accounts, transactions, balances, currency handling for DOP/USD records,
plans (budget, goal, debt), households, membership, sharing and edit permissions with RLS,
chat-to-record proposal and confirmation actions, file and voice ingestion, notification inbox and
delivery (documented status per §5), device registration, and self-service account deletion. The
[authority map](../DOCUMENTATION_AUTHORITY.md#what-remains-technical-or-undecided) already names
these as open. The existing `AccountCapabilities` (`schemas.py:191`) is a guest/registered switch,
not a resource permission model, and should not be stretched into household permissions.

## 5. Documented intent versus implementation discrepancies

| Statement | Where documented | What the source shows |
| --- | --- | --- |
| Notifications: current production state "Hidden/flagged for Alpha"; approved to enable in the next product push | [PRODUCT.md](../PRODUCT.md#current-production-availability-and-planned-changes) | The documented status stands; this report does not revise it. A case-insensitive search at `ab9143c` for `notification`, `push_token`, `device_token`, `apns`, `fcm`, `web-push`, `pushManager`, and `serviceWorker` across `src/`, `web/lib/`, `web/components/`, `web/app/`, `supabase/`, `render.yaml`, `.env.example`, and `web/.env.local.example` found no user-facing inbox, delivery, device-registration, or notification flag code. Matches were limited to team feedback email (`src/argus/api/feedback_notification.py`), chart range events, and commented Supabase email-template examples. The search did not cover hosted configuration, dashboards, other branches, or other names for the feature, so it does not show the capability is absent from production. The PRODUCT.md owner can reconcile the wording if needed |
| Supabase Realtime is the job-status target transport | `docs/API_CONTRACT.md:1879` | Polling only |
| Auth transport "Supabase Auth session cookie or bearer token" | `docs/API_CONTRACT.md:67-75` | Accurate for requests; refresh, revoke, and recovery are outside the Argus API |

## 6. Contract gaps

Ordered by how directly they affect native integration while preserving existing behavior.

| # | Gap | User impact | Smallest plausible adaptation |
| --- | --- | --- | --- |
| G1 | No implemented native flow obtains the Turnstile token that guest start, sign-in, and sign-up require | Native entry is not integrated until a token path exists | Spike the recommended default (E1). No backend change if the token remains a Turnstile token |
| G2 | Session refresh, revoke, password change, and recovery live in the browser Supabase client and a Next.js route | Native sessions expire hourly (local config) with no documented refresh path; logout could leave refresh tokens live | Document the native session contract using the recommended default (E2) |
| G3 | Guest handoff secret travels only as HttpOnly cookies | Guest-to-account conversion loses the temporary conversation on native unless a jar is managed | Additive header/body transport read by the same server helper (E3), or a scoped cookie jar |
| G4 | Email confirmation and recovery links target the web origin; no app/universal link association | Users leave the app to finish signup or recovery | Founder choice X1; app/universal links need association files hosted by the web app |
| G5 | Ordinary turn continuity across disconnect is inferred from code and unmeasured on phones | If the inference holds, backgrounded answers show "working" for up to 15 minutes, then a retry that spends another turn | Measure first (WP-D). Founder choice X4 only after evidence |
| G6 | Deterministic presentation composed in web TypeScript from typed facts | Native must port well over 1,000 lines of TypeScript per platform, creating three owners of the same copy | Inventory projections, then apply the recommended default (E4) |
| G7 | Wire payloads untyped in OpenAPI | No generated Swift/Kotlin models; drift found only at runtime | Publish JSON Schema for SSE frames and metadata envelopes from existing Pydantic models, plus golden fixtures |
| G8 | Web i18n catalog is the de-facto key namespace for backend `locale_key`/`label_key` | Native strings drift from web or show raw keys | Package the catalog as a shared contract, like `argus_display_contract` |
| G9 | Temporary chat opt-out is device-local | Opt-out on one device is ignored on another | Founder choice X2 |
| G10 | Account deletion only by feedback request | App-store review risk; unclear user path | Founder choice X3 |
| G11 | No upload, financial-record, household, permission, or device-registration contract found (notification status per §5) | New MVEE record surfaces have no backend contract to build on, on any client | Contract definitions after the relevant MVEE §9 decisions (WP-E); not native prerequisites |

## 7. Proposed independent work packages

These are proposals for assignment, not created issues. Each preserves existing web behavior.

### WP-A Native session and guest-entry contract

- **Outcome:** a written, reviewed contract that lets a bearer-only client start a guest session,
  sign in, sign up, refresh, revoke, recover, convert a guest, and switch accounts.
- **Owns:** a new API_CONTRACT §7 subsection (by its owner), any additive handoff transport in
  `src/argus/api/routers/auth.py` and `schemas.py`, and tests.
- **Prerequisites:** R0; E1 spike result; E2 and E3 accepted by the architecture reviewer; founder choice X1.
- **No-touch:** interpreter prompts and schema descriptions, LangGraph runtime, web auth UI,
  cookie names in `browser_cookies.py` (unless the privacy disclosure is updated with them).
- **Acceptance evidence:** a scripted bearer-only client (no cookies, no `Origin`) completing guest
  start → turn → handoff → signup/login → claim → logout-with-revocation against a local stack;
  existing auth, guest, and cookie-disclosure tests unchanged and green.

### WP-B Wire-format schemas and golden fixtures

- **Outcome:** machine-readable schemas for SSE frames, `final` payload, and message metadata
  envelopes (result card, confirmation, tool-result card, recovery, research sources, next
  experiments, backtest job sidecar), plus recorded fixtures per card and failure type.
- **Owns:** a generated schema artifact and a test that validates existing test payloads against it.
- **Prerequisites:** none.
- **No-touch:** runtime behavior, `Field(description=...)` text in the eval-reachable tree
  (AGENTS.md Never-Violate 12 applies if touched), web types.
- **Acceptance evidence:** schema test green; OpenAPI structural gate unchanged; fixtures cover en
  and es-419 and at least one non-buy-and-hold strategy.

### WP-C Presentation ownership inventory

- **Outcome:** a list of every client-side projection from typed payloads to text or actions,
  with a per-item recommendation (backend-resolved or shared catalog plus template), and a packaged
  shared locale catalog.
- **Owns:** a docs report and catalog packaging similar to `web/argus_display_contract/`.
- **Prerequisites:** E4 accepted by the architecture reviewer.
- **No-touch:** visible web copy and layout, backend prose, model-facing text.
- **Acceptance evidence:** inventory cross-referenced to files; a test proving backend-emitted
  `locale_key`/`label_key` values exist in the packaged catalog for both languages.

### WP-D Mobile turn-continuity measurement

- **Outcome:** evidence of what a disconnect does to ordinary, research, breakdown, and
  `run_backtest` turns in hosted-parity mode, and what the user sees on return.
- **Owns:** a deterministic test or local-stack harness and a findings report.
- **Prerequisites:** none. Coordinate with [#700](https://github.com/lagarcess/argus/issues/700).
- **No-touch:** runtime code during measurement; paid provider calls and Render workflow dispatch.
- **Acceptance evidence:** mocked or synthetic-provider runs per turn type showing lifecycle
  state, persisted messages, activity projection, and allowance usage after disconnect.

### WP-E Ecosystem contract definitions (records, households, ingestion, updates)

- **Outcome:** separate, bounded contract proposals for financial records, household permissions,
  file ingestion, and notifications/device registration, each client-neutral.
- **Prerequisites:** MVEE §9 decisions for each area; WP-A for identity assumptions.
- **No-touch:** existing chat, simulation, and search contracts; legacy Strategy/Collection rows.
- **Acceptance evidence:** reviewed contract documents; no implementation.

## 8. Outstanding reconciliation, founder choices, and engineering recommendations

### 8.1 Documentation reconciliation (already decided)

| # | Work | Note |
| --- | --- | --- |
| R0 | Publish the founder-approved native stack documentation from its local branch and reconcile the pointers in the decision log, ARCHITECTURE.md §5, and DOCUMENTATION_AUTHORITY.md | Publication and reconciliation, not an open framework choice. Owned by whoever holds that branch |

### 8.2 Founder-facing experience choices

Each has a recommended default so work can proceed if the founder accepts it.

| # | Choice | Recommended default | Tradeoff |
| --- | --- | --- | --- |
| X1 | Where native users finish email confirmation and password recovery | Return to the app through app/universal links; until those exist, finish on the web with a clear step back to the app | App links need association files, a redirect allow-list change, and hosted email template review; web completion is available now but breaks the flow |
| X2 | Whether temporary chat (memory opt-out) follows the user across devices | Keep today's device-local behavior on each client and label it as applying to this device | Syncing needs a server-side flag and a privacy review; device-local can surprise someone who switches devices |
| X3 | How account deletion is offered in the native apps | An in-app entry point that starts the existing deletion request and explains what happens next; self-service deletion is a separate contract | The request path exists today; store policy fit should be checked by the release owner before submission |
| X4 | What a user sees when an answer is interrupted by leaving the app (after WP-D evidence) | Keep the current durable retry path unless measurement shows it is common and slow to recover | Finishing turns server-side after disconnect improves continuity but spends model cost on answers nobody may read |

### 8.3 Engineering recommendations (owner: architecture reviewer and release captain)

These are technical defaults with tradeoffs, not founder blockers. Escalate only if a spike fails
or a user-visible tradeoff emerges.

| # | Topic | Recommended default | Tradeoff / alternative |
| --- | --- | --- | --- |
| E1 | Native bot-protection token | Spike: host the existing Turnstile widget in a native web view and pass its token to the unchanged endpoints | Keeps one provider and no backend change; web-view friction and Cloudflare's behavior in embedded contexts must be verified. A platform-attestation path would need backend and Supabase Auth configuration changes |
| E2 | Session refresh, revoke, and password change | Native apps use the official Supabase client SDKs, mirroring the web's ownership; logout always revokes | No backend change; auth logic lives in three clients. Refresh must be serialized under token rotation. Alternative: thin Argus endpoints, one more owner to keep in sync with Supabase |
| E3 | Guest-handoff secret transport | Additive header or body field for bearer clients, read through the same server helper as the cookies | Small contract change with tests. Alternative: a cookie jar scoped to `/api/v1/auth` that discards `sb-*` cookies; no backend change, but each platform must enforce the scoping |
| E4 | Presentation ownership | Package the web locale catalog as a shared artifact first; move deterministic fallback composition server-side one projection at a time, only where web output stays identical | Shared catalog is cheap and removes key drift; porting templates to Swift and Kotlin creates three owners of the same copy |
| E5 | Wire schemas | Generate JSON Schema from existing Pydantic models (WP-B) | Some metadata has no model yet; adding models must not change `Field(description=...)` text in the eval-reachable tree |

Guest onboarding, offline synchronization, financial schemas, notification providers, and ingestion
providers are deliberately not selected here.

## 9. Related issues and pull requests

| Item | Relevance |
| --- | --- |
| [#700](https://github.com/lagarcess/argus/issues/700) Dedupe ordinary chat turns by Idempotency-Key | Native reconnect/resend currently spends another turn |
| [#688](https://github.com/lagarcess/argus/issues/688) Remote Markdown images; stale tab resend under new account | Same rendering and account-switch rules apply to native |
| [#686](https://github.com/lagarcess/argus/issues/686), [#671](https://github.com/lagarcess/argus/issues/671), [#676](https://github.com/lagarcess/argus/issues/676) | Client-IP trust and rate-limit keying affect native and mobile web equally |
| [#640](https://github.com/lagarcess/argus/issues/640) Keep an observing conversation fresh | Same activity/freshness contract native clients will poll |
| [#687](https://github.com/lagarcess/argus/issues/687), [PR #706](https://github.com/lagarcess/argus/pull/706) Private content in logs (PR merged after the audited SHA) | MVEE privacy rules for records and documents |
| [#701](https://github.com/lagarcess/argus/issues/701) Closed analytics event registry | Native analytics events should join the same registry |
| [PR #672](https://github.com/lagarcess/argus/pull/672) Docs accuracy and draft Wave 1 roadmap | Open docs PR touching roadmap context; avoid overlapping edits |
| [PR #705](https://github.com/lagarcess/argus/pull/705) Docs-only CI hardening | Affects how this report's PR is gated |

No open issue or pull request on native clients, mobile auth, uploads, or financial records was
found at the time of this audit.

## 10. Verification performed

- Every `path:line` reference above was read at `ab9143c`.
- Relative documentation links in this report were checked to resolve to existing files.
- Search navigation claims were re-verified against `SearchItem`, `SearchMatch`, and
  `SearchAssetRollup` in `schemas.py` and against the web command palette, after review feedback
  on this PR.
- The notification search terms and scope are recorded in §5.
- No native or bearer-only client was run; every "Reuse candidate" status is a source-reading result.
- The docs-reading pytest selection (`.github/docs-reading-tests.sh`, 42 files) could not run locally: project dependencies are not installed in this container and installation was out of scope. CI owns that gate.
- No runtime, test, or migration file was changed; no service was started; no provider was called.
