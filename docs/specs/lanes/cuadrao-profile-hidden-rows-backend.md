# Cuadrao Profile hidden rows: backend each one needs

**Status:** Planning list, not an assignment. It dispatches no worker and decides no product question.
**Read at:** integration `a8c37d3a182fbdb3228f6003272418e65286bc1a`.
**Product owner:** [MVEE Profile](../argus-minimum-viable-ecosystem-experience.md#profile-control-argus). The [execution board](../argus-execution-board.md#cuadrao-release-ui-landing-order) owns status and order.

At the integration baseline above, `CuadraoFirstRelease.hiddenProfileRoutes` in `ios/ArgusFoundation/Cuadrao/CuadraoProfileCanvas.swift` hides seven Profile rows: `.personalization`, `.security`, `.shared`, `.removed`, `.memory`, `.usage` and `.advanced`. Their screens are in `ios/ArgusFoundation/Cuadrao/CuadraoProfilePage.swift` and are preview-only: no row calls the API. The MVEE calls them designed rows whose backend is still owed, ordered after chat.

The verified #790 candidate renames that inventory to `unfinishedProfileRoutes` and shows the complete editor in development builds. Release still gates unfinished rows and avatar editing until selections persist. This candidate behavior has not landed on integration; the [current mobile roadmap](../argus-execution-board.md#current-mobile-roadmap-october-4-founder-lock) owns its status.

This file lists, for each row, the backend it needs, what integration already has, and what is missing. The original dependency was the connected native conversation client (board work ID D09). The current mobile roadmap also requires a bounded Cuadrao runtime assignment. Existing Argus APIs below are reusable inventory, not approval to copy its runtime or allowance model into Cuadrao. These Profile backends remain ordered after chat.

## Proposed order after chat

1. **Usage.** The backend exists; only the native client is missing.
2. **More options.** Feedback exists; one preference needs a product definition first.
3. **Security.** Supabase Auth owns the operations; Argus has no session list.
4. **Memory.** The API exists behind a role gate; the native client and the rollout decision are missing.
5. **Shared conversations.** The API exists behind a default-off flag that needs a founder decision.
6. **Personalization.** No storage exists, and the change reaches model-facing text.
7. **Removed activity.** No removal or restore operation exists, and its recovery rules are open.

The order puts the smallest backend gap first. Rows 4 to 6 also depend on chat for their content. Row 7 does not depend on chat, but it waits on open product decisions.

## Usage (`.usage`)

- **Needs.** The account's allowances and reset times. The screen says: "Your allowance and reset time will appear when your account is connected."
- **Exists.** `GET /api/v1/me/usage` ([API contract](../../API_CONTRACT.md#get-meusage)) returns `compute`, `grounding` and `execution` windows from `usage_counters`. It is owner-only and creates no counter on read.
- **Missing.** A native client for `GET /me/usage` and copy for each operation class. `compute` is never metered, so the screen must not show a limit for conversation.

## More options (`.advanced`)

- **Needs.** The screen has two actions, "Suggestions" and "Shake to report a problem".
- **Exists.** `POST /api/v1/feedback` (`src/argus/api/routers/feedback.py`) stores a report in `feedback`.
- **Missing.** Shake to report needs only a native client that posts to `/feedback`. "Suggestions" has no definition in the MVEE or in Cuadrao's design guide, so it needs a product definition before any backend. If it is an account preference, it needs a field on `PATCH /me`, which today accepts no such field.

## Security (`.security`)

- **Needs.** Change password, show this device, sign out other sessions, and sign out all sessions.
- **Exists.** Supabase Auth (GoTrue) owns passwords and sessions. `POST /api/v1/auth/logout` clears Argus's mirrored cookies only, and the [contract](../../API_CONTRACT.md#post-authlogout) says it does not choose a revocation scope. Argus reads `auth.sessions` only to check that the caller's own session is live (`src/argus/api/auth_sessions.py`); it never lists sessions.
- **Missing.** A session list that names devices: Argus has no route for it. The native client must call Supabase Auth for a password change and for sign-out with the `others` or `global` scope. A person who signed in only with Apple or Google has no password, so the row needs that state.

## Memory (`.memory`)

- **Needs.** A list of remembered context, with edit, pause and reset. The Personalization screen also links here.
- **Exists.** The memory API ([API contract 17.2](../../API_CONTRACT.md#172-memory-registered-role-gated)) in `src/argus/api/routers/personalization_memory.py`: `GET /memory/availability`, `/memory/settings`, `/memory/records` and `/memory/export`; `PATCH` and `DELETE /memory/records/{record_id}`; and `POST /memory/enable`, `/memory/disable`, `/memory/reset`, `/memory/candidates` and `/memory/retrieval`. Tables: `memory_settings`, `memory_consent_actions` and `memory_records` (`20260729225600_add_personalization_memory_persistence.sql`). `ARGUS_ENABLE_PERSONALIZATION_MEMORY` is `"true"` in `render.yaml`, but every endpoint except `GET /memory/availability` also needs an `admin` or `developer` role in `private_alpha_allowlist`, so ordinary accounts get `404 personalization_memory_unavailable`. `GET /memory/availability` answers them `available: false`.
- **Missing.** A native client. Memory candidates come from conversations, so chat comes first. Opening memory to ordinary accounts is a rollout decision that [PRODUCT.md](../../PRODUCT.md#current-production-availability-and-planned-changes) owns. The temporary-chat copy that mentions memory (`ios/ArgusFoundation/Cuadrao/CuadraoTemporaryChatSettings.swift`) has to follow the same gate.

## Shared conversations (`.shared`)

- **Needs.** The person's share links, each with a revoke action. The screen says: "Links you share will appear here."
- **Exists.** The owner routes in the [API contract](../../API_CONTRACT.md#public-evidence-receipts), in `src/argus/api/routers/evidence_receipts.py`: `GET /public-excerpts` (the owner's list) and `DELETE /public-excerpts/{snapshot_id}` (revoke), plus candidate, preview and create under `/conversations/{conversation_id}/public-excerpt*`. Table: `public_excerpt_snapshots`. All of it sits behind `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED`, which is `"false"` on integration and `"true"` on `main`.
- **Missing.** A native client, and a native way to create a share from chat. The founder decides whether sharing is on before the next promotion to `main`. The [sharing spec](../conversation-sharing.md) owns the behavior.

## Personalization (`.personalization`)

- **Needs.** Response length (automatic, brief, detailed), tone (natural, direct, educational) and free-text instructions the person writes. The screen says these are preferences the person chooses, not memories.
- **Exists.** Nothing stores them. `PATCH /me` accepts names, language, locale, avatar theme, country and currency only. `src/argus/agent_runtime/response_style.py` holds one fixed style for every account.
- **Missing.** Storage on the profile and a `PATCH /me` contract for the three fields, then a way for chat to use them. Using them changes model-facing text, so it needs the committed scorecard that AGENTS.md Never-Violate Standard 12 requires. The free-text field also needs a sensitivity rule, as memory has.

## Removed activity (`.removed`)

- **Needs.** A list of removed financial entries that can be restored. The MVEE's [account activity section](../argus-minimum-viable-ecosystem-experience.md#account-activity-and-balance-checks) asks for the original space and account, a preview of balance effects, and restoring the original record instead of a copy, with transfers and payments returning together.
- **Exists.** Nothing that removes activity. The API contract says: "No operation removes actual activity or changes its immutable kind." `/financial-activities` creates, previews and corrects activity, and a correction retires legs as inactive zero revisions.
- **Missing.** A remove operation, a restore operation, a stored removal state, and the product rules the MVEE leaves open: production retention, authorization and recovery periods. This row waits on those decisions, not on chat.
