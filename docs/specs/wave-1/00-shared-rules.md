# Argus wave 1: shared rules for every stage

> **September 26, 2026 reconciliation:** Read
> [documentation authority](../../DOCUMENTATION_AUTHORITY.md) and the approved
> [MVEE](../argus-minimum-viable-ecosystem-experience.md) before using this spec.
> These Wave 1 package bodies and existing stage/review gates remain preserved
> for assigned work. Conflicting experience requirements need explicit package
> reconciliation; they are not permanent limits on the pivot. This notice does
> not cancel work, unlock stages, change technical contracts, or authorize
> exposing unfinished features. The original product/source text below remains
> a dated specification, not the final definition of the whole ecosystem.

Applies to: SPEC 0 (`01-stage-0-safety-and-analytics.md`) and SPEC 1
(`02-stage-1-layout-ai-landing-card-payoff.md`), and every later wave 1 spec.

Integration branch: `codex/private-alpha-next`. Reuse map verified against
integration tip `5fb0f079b92ed5391da770cb9a7b89c1c4807684`
("fix(api): disable Loguru diagnostic locals (#682) (#691)").
Where a fact comes from an unmerged branch or PR, the PR or SHA is named.

---

## Part 1. Product shared rules (Iris, verbatim)

Source: Iris, "Wave 1 specs: product halves", Revision 2 (Sep 25 2026).

## Shared rules (apply to every wave 1 spec)

- **R1. Language.** es-419 first, with English alongside. Every new user-facing string needs both, with no em dashes, following the key style already used in #681.
- **R2. Currency.** Money is shown in its own currency: pesos are `RD$`, dollars are `US$`. Wave 1 has no exchange-rate source, and the money code refuses to add two currencies, so **wave 1 never shows a combined peso-plus-dollar total**. Peso and dollar amounts are always shown side by side, separately. A combined total waits for a dated rate source. Which source to use is Lucas's call: his earlier direction was Perplexity, and Yelena suggests the central bank (BCRD). When it exists, every conversion shows the rate and its date.
- **R3. Taxes.** Every calculated result (receipt) says "Antes de impuestos" / "Before taxes". We don't calculate taxes (Lucas's locked rule).
- **R4. No amounts leave the app.** Not in emails, push, analytics events or logs. Shares follow the 09-14 lock (the owner picks what to share and sees an exact preview). Nothing in wave 1 changes shares.
- **R5. Keep all existing capability.** The 11 calculators on prod stay reachable by asking in chat, even when their menu entries are hidden.
- **R6. Hidden in wave 1** (behind a flag or removed from navigation, never deleted from the code): net worth, accounts, Discover, uploads, budgets, debt goals, Pro+/Rewards, WhatsApp. None of the money-placement-pilot UI comes back; only its engine and data may be reused.
- **R7. Extra review.** Money math (card payoff now, goal math in stage 2) needs Priya's eval check plus a Codex review, whoever writes it. So does anything that sends messages to users or touches their data or consent (analytics, notifications, email, push).

---

## Part 2. Engineering shared rules

### E1. Read first, do not restate

`AGENTS.md` at the repo root is the operating manual and wins over this file on
anything it covers: the source-of-truth docs and their order, the Split-Brain
Rule ("who else holds this fact, and what forces them to agree?"), the
worktree environment contract, feature-flag doctrine, model-facing text freeze
(Never-Violate Standard 12), API-contract-first (Standard 1), TDD first
(Standard 3), and commit discipline. Read it before the first commit. This file
only adds the wave 1 delivery rules below.

Two older rule files conflict with the delivery rules here. For wave 1 work,
this file wins:

- The old git-workflow rule file (since removed) said "Squash merge to main"
  and "Parallel PRs OK". Wave 1 PRs target `codex/private-alpha-next`, never
  `main`, and land one at a time (E4).
- The pull request template is `.github/pull_request_template.md`. The headings
  in E4 are that template.

### E2. Work from worktrees off the integration branch

1. `git fetch origin` and create a worktree from the current tip of
   `origin/codex/private-alpha-next`. One worktree per work package.
2. Run the Phase 0 environment steps from AGENTS.md "Worktree Environment
   Contract" (`bash .github/setup-worktree-env.sh "$PWD"` and the `--check`
   form). Never write into a linked `.env` or `web/.env.local`.
3. Before opening the PR and before asking for merge, reconcile the latest
   integration tip into the branch one way (merge or rebase before
   publication; do not rebase a published or evidenced branch, per AGENTS.md
   Standard 11) and re-run the tests named in the package.
4. Branch names: `<type>/<scope>-<short-name>`, for example
   `feat/web-bottom-nav` or `fix/api-claim-after-idempotency`.

### E3. Stage unlock rule

A stage unlocks only when every work package in the current stage is merged
into `codex/private-alpha-next` and has passed review under the gate in E6.
"Opened", "approved", or "green but unmerged" does not count. Work packages
inside a stage may be built in parallel in separate worktrees, but they merge
one at a time (E4). The Head of Engineering (Yelena) confirms the unlock in
writing before any work on the next stage starts.

### E4. Pull request rules

- Base branch: `codex/private-alpha-next`. Never `main`.
- Title: conventional commit form, `<type>(<scope>): <summary> (#<issue>)`.
- Body headings, in this order, all present (write "None" where empty):
  1. `## TL;DR`
  2. `## Motivation` (link the issue and the spec section, for example
     "SPEC 0, package 0C-2")
  3. `## Changes`
  4. `## Out of scope`
  5. `## Testing` (commands run and results; named tests; for any
     user-visible change, before and after screenshots in EN and es-419, at
     360 px wide (Iris's target phone) and at desktop width, attached on the
     pull request or uploaded with actions/upload-artifact)
  6. `## Risks/Rollback`
  7. `## Docs affected`
  8. `## Status` (head SHA, integration SHA it was reconciled onto, CI state,
     review-thread state)
- Labels: exactly one type label (`feature`, `bug`, `chore`, `docs`, `perf`,
  `refactor`, `test`) plus exactly one priority label (`low-priority`,
  `med-priority`, `high-priority`). Scope labels (`web`, `api`, `db`, `core`)
  are encouraged.
- One PR open for merge at a time per stage. Merge method: squash merge only.
- One logical change per PR. If an API shape changes, the
  `docs/API_CONTRACT.md` edit is in the same PR or lands first (AGENTS.md
  Standard 1).
- Every Codex review thread gets a written reply, then is resolved. Allowed
  replies:
  - `Fixed in <sha>`
  - `Won't fix: <reason>`
  - `Deferred to #<issue>` (open the issue first)
  No thread is resolved without a reply.

### E5. Access and deploy boundaries for contractors

- No production or Supabase secrets are shared with contractors. Work runs on
  mock auth (`NEXT_PUBLIC_MOCK_AUTH=true`, see AGENTS.md "Developer Identity:
  Mock Auth Mode"), the in-memory store, and local Supabase via
  `scripts/qa/write-local-env.sh` where a package needs Postgres.
- Tests that need a real provider (OpenRouter, Perplexity, PostHog, Resend)
  are run by the internal team. Contractor tests mock these at the module
  boundary, the way `tests/test_observability_product_events.py` mocks
  capture.
- No deploy to `main` or production, no Render or Vercel dashboard changes, no
  Supabase dashboard changes, no hosted migration runs. Migrations are written
  and tested locally; the internal team applies them.
- No PostHog project access is needed to build. Event payloads are asserted in
  tests.

### E6. Review gate

Everything, every PR:

1. CI green on the PR head (`.github/workflows/ci.yml` jobs: docs-change-gate,
   ownership-gate, docs-checks, backend-checks, frontend-checks,
   database-checks, plus any job the change triggers).
2. Codex review completed on the head.
3. Every review thread replied to and resolved (E4).

Additionally, for any PR that touches one of these, before merge (this is
the engineering form of Iris's R7):

- money math (anything in `src/argus/domain/finance/`,
  `src/argus/domain/calculations/`, presenters that print amounts, rounding,
  currency, exchange rates);
- security (auth, identity, rate limits, usage claims, logging of request
  data, CORS, headers);
- database migrations (`supabase/migrations/`);
- anything that sends a message to a user (email, push, in-app notice copy
  about limits or money);
- anything that touches user data or consent (analytics identity, attribution,
  profile fields, saved cards, sharing);
- model-facing text (AGENTS.md Standard 12; this includes a new calculation
  declaration, because its description is rendered into the calculation list
  the interpreter reads, see `src/argus/domain/calculations/answer_request.py`
  around line 197),

the PR also needs:

4. Priya's eval verdict, written on the PR.
5. A Codex re-review on the final head after all fixes.

### E7. Copy and language rules that code must follow

- Every user-visible string is an i18next key in both
  `web/public/locales/en/common.json` and
  `web/public/locales/es-419/common.json`. No hard-coded UI strings.
- Backend presenters never format prose. They return `LocalizedText`
  (`locale_key` plus `interpolation_args`) built with `text()` or `note()` in
  `src/argus/domain/calculations/_shared.py`; the web localizes.
- No em dash (U+2014) in any new copy or model-facing text. PR #681 adds a
  unit test for this on its strings; follow that pattern.
- Key style: nested snake_case under an existing top-level area (`chat`,
  `tools`, `receipt`, `guest`, `settings`, `sidebar`, `feedback`, `auth`,
  `landing`), for example `chat.recovery.guest_compute_claim_unavailable` and
  `tools.calc.time_value.*`. Add a new top-level area only for a new surface
  (SPEC 1 adds `navigation` and `landing_ai`).
- Parity and exact-copy assertions live in `web/__tests__/locales.test.ts`.

### E8. Follow-up questions must keep working (Lucas, Sep 25 2026)

Argus asks the user for a missing input when a question lacks one, and it keeps
the conversation going when the user asks a follow-up question in the same chat.
Wave 1 must not remove, weaken, or bypass either behavior.

- The landing chips carry every input so that a tap answers on the first turn.
  That is a property of the chip text only. It does not change how any
  calculator handles a question that is missing inputs.
- Every calculator still asks for missing inputs when a typed question lacks
  them. `card_payoff` asks one field at a time and also asks whether the rate is
  monthly or annual.
- A user can ask a follow-up question after any answer, including a chip answer,
  and the chat continues with the earlier context.
- Regression tests required in 1B-1 and 1C-2: (a) a typed question with a
  missing input gets a question back and then a receipt after the user answers;
  (b) a follow-up question after a chip answer continues the same chat and uses
  the earlier result. Existing missing-input and continuity tests must stay
  green. Any PR that fails them does not merge.

---

## Part 3. Shared reuse map for all of wave 1

Lucas's rule: find what exists and reuse it; say what is genuinely new. Each
spec points at the rows it uses by ID (for example "see RM-3"). "Exists" means
present at `5fb0f079` unless stated otherwise.

### RM-1. Product analytics pipeline (PostHog)

Exists:

- One server-side sink. `src/argus/observability/envelope.py`:
  `build_event_envelope()`, `capture_event()` (blocking `httpx.post` to
  PostHog `/capture`), `posthog_event_payload()`, attribute sanitizer
  `sanitize_observability_attributes()`, env `POSTHOG_HOST` or
  `POSTHOG_REGION` plus project token, suppression reasons
  `posthog_not_configured` and `posthog_region_not_configured`
  (`docs/DATA_MODEL.md` around line 1220).
- The browser never talks to PostHog. There is no `posthog-js`. The web posts
  two client events to the API at `POST /api/v1/analytics/guest-events`
  (`src/argus/api/routers/analytics.py`, schema `GuestFunnelClientEventRequest`
  in `src/argus/api/schemas.py`, client `web/lib/guest-analytics.ts`), and
  receipt funnel stages to `POST /api/v1/public/receipt-funnel`
  (`src/argus/api/routers/public_receipts.py`, client
  `web/lib/receipt-funnel.ts`).
- Two event registries:
  - `src/argus/observability/product_events.py`, `ProductEventKind` and
    `_PRODUCT_EVENT_MAP`, emitted through `capture_product_event()`.
  - `src/argus/observability/guest_funnel.py`, `GuestFunnelEventKind` and
    `GUEST_FUNNEL_EVENT_MAP`, emitted through
    `emit_guest_funnel_event()` / `emit_verified_guest_funnel_event()` in
    `src/argus/api/guest_observability.py`, with once-per-subject milestones
    (`MILESTONE_EVENT_KINDS`, claim table from migration
    `20260808120000_add_guest_funnel_milestones.sql`).
  - Plus `capture_research_turn_event()` in
    `src/argus/observability/research_events.py` (event_type `research`).
- IMPORTANT fact about naming: the PostHog `event` field is the generic
  `envelope.event_type` (for example `system`, `storage`, `tool_result`). The
  product name (for example `decision_capture`) is only in the property
  `product_event`. In the PostHog UI every funnel must filter on that
  property.
- Current product event names and where each fires:

| Event (`product_event`) | Registry | PostHog `event` | Fires in |
| --- | --- | --- | --- |
| `guest_session_started` | guest | `system` | `src/argus/api/routers/auth.py` guest bootstrap (around line 268) |
| `starter_action_selected` | guest (client) | `user_message` | web `captureGuestFunnelEvent` via `/analytics/guest-events`; only `buy_and_hold` and `dca_accumulation` accepted |
| `first_useful_assistant_response_completed` | guest, milestone | `ai_response` | `emit_first_guest_message_event()` in `guest_observability.py`, only when guest message count is 1 |
| `confirmation_reached` | guest | `tool_result` | `emit_guest_turn_funnel_events()` |
| `first_simulation_admitted` | guest, milestone | `tool_call` | `src/argus/api/routers/backtest.py` via `emit_first_guest_simulation_event()` |
| `first_result_completed` | guest, milestone | `tool_result` | same, on backtest completion |
| `conversion_prompt_shown` | guest (client) | `system` | web conversion modal via `/analytics/guest-events` |
| `account_creation_completed` | guest, milestone | `storage` | `auth.py` guest handoff claim (around lines 448, 739, 937), with the GUEST user id |
| `existing_account_sign_in_completed` | guest, milestone | `system` | same |
| `temporary_workspace_claimed` | guest, milestone | `storage` | same (around lines 463, 749, 951) |
| `guest_limit_reached` | guest | `system` | `src/argus/api/chat/backtest_admission_flow.py`, `routers/backtest.py`, `routers/feedback.py` |
| `guest_feedback_submitted` | guest | `storage` | `routers/feedback.py` |
| `guest_session_expired` | guest | `system` | `src/argus/domain/guest_cleanup.py` |
| `account_registration_completed` | product | `storage` | `auth.py` `_emit_account_registration_completed_event()` with the NEW registered id |
| `decision_capture` | product | `decision_saved` | `src/argus/api/chat/decisions.py` (message decision) and `src/argus/api/chat/evidence.py` (backtest artifact decision). This is "save a card" today |
| `evidence_capture` | product | `storage` | `src/argus/api/chat/evidence.py` (three sites) |
| `recall_usage` | product | `tool_result` | `src/argus/api/routers/search.py` (two sites) |
| `continuity_mismatch` | product | `recovery` | `src/argus/api/chat/measurement_events.py` |
| `compare_started` | product | `compare_started` | `measurement_events.py` |
| `next_experiments_offered` | product | `system` | `src/argus/api/chat/measurement_events.py` (registered by PR #669) |
| `next_experiment_selected` | product | `system` | `src/argus/agent_runtime/runtime.py` |
| `eval_readiness` | product | `eval_suite_run` | `tests/evals/chat_runtime_eval_harness.py` (around line 857). Eval tooling writes into the product stream |
| `receipt_created`, `receipt_revoked` | product | `storage` | `src/argus/api/routers/evidence_receipts.py` |
| `receipt_viewed`, `receipt_try_argus` | product | `system` | `/public/receipt-funnel` from `web/components/receipt/*` |
| `receipt_followed_up` | product | `system` | `src/argus/api/routers/receipt_forks.py` |
| `receipt_signed_up` | product | `system` | `src/argus/domain/supabase_guest_accounts.py` (around line 252) |
| research turn | research | `research` | `research_events.py` via `src/argus/api/chat/research_evidence.py` |

Target state after SPEC 0 (Iris's 0C, a clean break): PostHog receives only
Iris's 10 events under their own names (the 8 in 0C plus `landing_viewed`
and `receipt_shared`, from her round 2 answers); every row above is renamed into one of
them or stops being sent to PostHog. Mapping is in SPEC 0 section 0.5.
Genuinely new work is scoped in SPEC 0 package 0C. Do not add a third
registry, do not add `posthog-js`, and do not add a second sink.

### RM-2. Identity sent to PostHog; guest to account linking

Exists:

- `distinct_id` = `actor_hash_for_user(user_id)` in `product_events.py`:
  `argus_actor_` plus the first 32 hex chars of
  `sha256("argus:actor:<user id>")`. If there is no user id, the random
  `event_id` is used, so those events are unjoinable.
- Every event sets `$process_person_profile: False`, so PostHog creates no
  person profiles.
- A guest is a Supabase anonymous user with its own profile id. On sign-up or
  sign-in, `claim_guest_workspace_handoff()`
  (`src/argus/domain/supabase_guest_accounts.py` around line 176) moves the guest's data to the
  destination (registered) user id. The conversion events are emitted with the
  SOURCE (guest) user id; `account_registration_completed` is emitted with the
  DESTINATION id. Nothing links the two hashes. There is no `$identify`,
  `$create_alias`, or `$merge_dangerously` anywhere.
- Consequence: today a guest's pre-sign-up activity and the same person's
  signed-in activity are two unrelated PostHog ids.
- The milestone dedupe key is the visitor key (`milestone_subject()` in
  `guest_funnel.py`), derived from the client IP hash; it never leaves the
  server and must not be sent to PostHog.

### RM-3. Excluding eval, dev, and test accounts

Exists:

- Every event carries `environment` from `APP_ENV` / `ARGUS_ENV` /
  `ARGUS_APP_ENV` / `ENVIRONMENT`, default `local` (`_default_environment()`
  in `envelope.py`).
- Account roles live in `public.private_alpha_allowlist.role`
  (`admin`, `developer`, `user`, `requested`; migrations
  `20260530000001_private_alpha_allowlist.sql` and
  `20260731080154_add_requested_private_alpha_access.sql`), read by
  `SupabaseGateway.private_alpha_role_for_email()` in
  `src/argus/domain/supabase_gateway.py` (around line 349). The same lookup
  already gates memory exposure (`MEMORY_EXPOSURE_ROLES` in
  `src/argus/api/personalization_memory.py`).
- Mock auth (`NEXT_PUBLIC_MOCK_AUTH`) and the in-memory store are dev-only.

Missing: no event carries an internal/test flag; the eval harness emits
`eval_readiness` into the same stream. New work is SPEC 0 package 0C.

### RM-4. Usage caps, 429 and 503 claim errors

Exists (merged):

- Guest daily compute cap and atomic claim:
  `src/argus/api/chat/guest_compute_ceiling.py` (PR #674, migration
  `20260925120000_claim_guest_compute_usage.sql`). Errors: `429`
  `too_many_requests` with `Retry-After` = seconds to UTC day end; `503`
  `guest_compute_claim_unavailable` with `Retry-After: 15`
  (`COMPUTE_CLAIM_UNAVAILABLE_RETRY_AFTER_SECONDS` in
  `src/argus/domain/usage_limits.py`).
- Signed-in daily compute cap and claim:
  `src/argus/api/chat/registered_compute_ceiling.py` (PR #678, migration
  `20260925140000_claim_registered_compute_usage.sql`). Errors: `429`
  `too_many_requests`; `503` `registered_compute_claim_unavailable` with
  `Retry-After: 15`.
- CORS exposes `Retry-After` and `X-Request-Id`
  (`src/argus/api/app_setup.py` around line 142, PR #678).

- Log safety (PR #691, squash `5fb0f079`, closes #682): see RM-16. The ops
  token check in `src/argus/api/routers/ops.py` now compares latin-1 bytes
  (`_latin1_bytes()`), so a non-ASCII `Authorization` header is a plain 404.

Open, not merged:

- PR #681 (head `fff96b69`): web handling of the guest claim 503. Adds the
  `Retry-After` parser (delta seconds or HTTP-date, clamp 1 to 120 s, 15 s
  fallback), `chat.recovery.guest_compute_claim_unavailable` in EN and es-419,
  a disabled Retry pill with countdown, `Retry-After` on `ChatStreamError`,
  and `web/e2e/guest-compute-claim-503.spec.ts` (not run in CI).
- Issue #692: claim runs before idempotency and conversation lookup in
  `src/argus/api/chat/agent.py` (claim near line 297, lookup near line 420);
  IPv6 /64 re-bucketing on deploy day; non-canonical IPv4 and `ip:port` in the
  trusted header (`src/argus/api/client_ip.py`).
- Issue #693: web handling of signed-in claim 503 (the raw detail is shown at
  `web/components/chat/ChatInterface.tsx` near line 1728) and honest daily-cap
  429 copy ("resets at <local time>"). Starts after #681 merges and must reuse
  #681's helpers.

### RM-5. Translation files and style

Exists: `web/public/locales/en/common.json`,
`web/public/locales/es-419/common.json` (top-level areas: `conversation_preview`,
`common`, `legal`, `feedback`, `chat`, `settings`, `sidebar`,
`keyboard_shortcuts`, `recents_quick_peek`, `command_palette`, `auth`,
`account_security`, `landing`, `guest`, `receipt`, `tools`), loaded by
`web/lib/i18n.ts`; Spanish gated by `NEXT_PUBLIC_ENABLE_SPANISH`
(`web/lib/language-features.ts`); tests in `web/__tests__/locales.test.ts`.
PR #681 is the reference for adding a recovery string pair plus a no-em-dash
test. Rules are in E7.

### RM-6. Calculator registry

`get_calculation_declarations()` in
`src/argus/domain/calculations/__init__.py` is the only catalog. Do not
restate names, count, or modules here; that inventory belongs to the runtime
owner. Each calculation is a `ToolDeclaration`
(`src/argus/domain/tool_declaration.py`) with a handler, `free_policy(...)`,
`ToolProgressTemplate`, `ToolCardBinding` (card type plus presenter),
validation rules, and domain lines. Shared helpers in
`src/argus/domain/calculations/_shared.py` (`CalculationArguments` with a
single `currency: Currency`, `money_fact`, `money_input`, `percent_input`,
`note`, `text`, `no_solution`, `MAX_PERIODS = 1200`). Pure math in
`src/argus/domain/finance/` (`tvm.py`, `growth.py`, `bonds.py`, `dcf.py`,
`ratios.py`, `valuation.py`, `comparison.py`, `money.py` with a `Money` type
that refuses to add two currencies).

Around the registry: tests in `tests/domain/calculations/` (one file per
calculation plus `support.py`), the committed web fixture
`web/__tests__/fixtures/calculation-cards.json` regenerated by
`scripts/dump_calculation_fixtures.py` and checked by
`tests/domain/calculations/test_web_fixture.py`, driving-input test
`tests/domain/test_calculation_driving_inputs.py`, and kernels test
`tests/test_calculation_kernels.py` (parametrized over
`get_calculation_declarations()`). `docs/ARCHITECTURE.md` points at the same
runtime owner and must not grow a hand-maintained calculations table.

### RM-7. `time_value`

`src/argus/domain/calculations/time_value.py`: `TimeValueArguments`
(`direction` save or borrow, `present_value`, `payment`, `future_value`,
`annual_rate_pct`, `periods`, `periods_per_year` default 12, `payment_timing`,
`start_date`), rule `ExactlyOneUnknown`, closed-form math in
`src/argus/domain/finance/tvm.py` (float), balances path, card type
`time_value`. It is a single-currency, fixed-payment plan. It does not model a
minimum payment that is a percentage of balance, per-month rounding, or two
currencies.

### RM-8. Credit card and debt math

On integration: none. `debt_to_income` is a ratio only; `effective_rate` turns
a nominal rate plus fees into an effective rate (useful for card fees).
On the pilot branch (see RM-15): `calculate_payoff()` in
`money-view/server/platform/credit.py` at `026be6d3` (merged there by PR #664,
not on integration). Decimal math, monthly interest rounded ROUND_HALF_UP to
the currency's minor unit, fixed payment = minimum payment plus extra,
statuses `paid_off`, `non_amortizing`, `horizon_exceeded`, 1200-month horizon,
assumptions `fixed_apr`, `fixed_monthly_payment`, `no_fees`,
`no_new_borrowing`. This is the engine to port for SPEC 1.

### RM-9. Peso exchange rate path

There is no FX service, no exchange-rate provider, and no stored rate on
integration (`git grep -i exchange_rate` in `src/` finds nothing). What exists
is the generic grounded-figure path: research through Perplexity
(`src/argus/domain/research/perplexity_agent.py`,
`src/argus/domain/research/contracts.py`, whose unit field is "the ISO 4217
code of a money amount such as USD or DOP"), grounded answers in
`src/argus/agent_runtime/research_grounded.py` and
`src/argus/agent_runtime/answer_calculation.py`, and page-cited inputs via
`ToolFactSource(kind="page", title, url, date)` in
`src/argus/domain/tool_contracts.py`. Test reference:
`tests/research/test_calculation_retrieval.py` (a DOP question). A
peso-per-dollar rate reaches a calculation today only as a page-cited input
that the research path extracted. Home currency: profile `country` and
`currency_override` (`src/argus/api/schemas.py` around lines 168 and 248,
`src/argus/domain/home_country.py`). The pilot's `BCRDProvider` is a
placeholder that always raises `bcrd_schema_unverified`.
Wave 1 does not convert currencies at all (Iris's R2). The future rate
source (Perplexity or BCRD) is Lucas's decision and is not built in wave 1.

### RM-10. Result cards, receipts, and a "before taxes" line

Exists: calculation cards are rendered generically by
`web/components/chat/ToolResultCard.tsx` and
`web/components/chat/ToolCardPresentation.tsx` from the backend presenter's
`ToolCardPresentation`; the parser is `web/lib/tool-result-card.ts`. Notes
render as a list under the card (`presentation.notes`), go into copy text
(`web/lib/tool-result-card.ts` around line 150), and become the "assumptions"
list on a shared receipt (`web/lib/receipt-presentation.ts` around line 113).
Note keys live under `tools.calc.notes.*` and are built with `note(code)` in
`_shared.py`. Backtest cards: `web/components/chat/StrategyResultCard.tsx`;
receipt fine print: `receipt.fine_print` keys, `web/components/receipt/`.
So a "before taxes" line added as one presenter note flows to the chat card,
copy text, and the receipt from one owner. R3 ("Antes de impuestos" /
"Before taxes" on every receipt) is built in SPEC 1 package 1F-1.

### RM-11. Saved cards (`supabase_decisions`)

Exists: table `public.decision_notes`
(`supabase/migrations/20260619000001_p1_evidence_decision_spine.sql`),
gateway `src/argus/domain/supabase_decisions.py`
(`upsert_message_decision_note`, `get_decision_note`,
`current_decisions_for_attachments`), routes in
`src/argus/api/routers/decisions.py`
(`POST /api/v1/conversations/{conversation_id}/messages/{message_id}/decision`,
`GET /api/v1/decisions/{decision_id}`, `POST .../rerun`), capability gate
`can_save_decision` (guests are asked to sign in, conversion reason
`save_decision`), web `web/components/chat/DecisionAffordance.tsx`,
`web/components/sidebar/command-palette/DecisionHistoryView.tsx`. A saved card
is always attached to a conversation message.

### RM-12. Navigation, layout, and feature flags

Exists: no bottom navigation. Shell is the sidebar:
`web/components/sidebar/ChatSidebar.tsx`, `SidebarShell.tsx`,
`SidebarDrawer.tsx` (mobile drawer), `SidebarNavButton.tsx`,
`ProfileMenu.tsx`, `ProfileSettingsPanels.tsx`, `ChatCommandPalette.tsx`
(omnisearch). Mobile shell: `web/components/chat/useMobileShell.ts`.
Breakpoints: `web/lib/responsive-layout.ts` (`TABLET_MIN_WIDTH_PX = 720`,
`DESKTOP_MIN_WIDTH_PX = 1024`) with `docs/BREAKPOINTS.md` and breakpoint
Playwright baselines (`web/e2e/breakpoint-baselines.spec.ts`). Routes under
`web/app/`: `/` (landing and auth, `web/app/page.tsx`, redirects a signed-in
user to chat), `/chat` (`web/app/chat/page.tsx`, the whole app lives in
`web/components/chat/ChatInterface.tsx`, 2596 lines), `/login`, `/signup`,
`/account/security`, `/r/[receiptId]`, `/privacy`, `/terms`, `/dev/*`.
Empty chat: `EmptyChatSurface.tsx`, `EmptyChatGreeting.tsx`,
`EmptyChatHeading.tsx`, `StarterActions.tsx`; starter prompts API
`GET /chat/starter-prompts`. Sidebar entries today (`ChatSidebar.tsx`): New chat, Search (opens the
omnisearch palette, conversation search), Recents, Settings. None of Iris's R6
items (net worth, accounts, Discover, uploads, budgets, debt goals,
Pro+/Rewards, WhatsApp) exists in this web app's navigation or routes; they
exist only in the unmerged `money-view/` pilot app. There is no
`web/app/not-found.tsx`, so an unknown path shows the Next.js default 404.
`StarterActions.tsx` SENDS on tap (`EmptyChatSurface.tsx` passes
`onSelect={onSend}`); the prefill-without-send mechanism is the landing
starter (`web/components/chat/useLandingStarterPrefill.ts`,
`noteLandingStarterComposerMatch()` in `web/lib/landing-intent.ts`).
Web flags: `web/lib/private-alpha-flags.ts`
(`NEXT_PUBLIC_OMNISEARCH_ENABLED`, `NEXT_PUBLIC_RESEARCH_RAIL_ENABLED`,
`NEXT_PUBLIC_GUEST_ACCESS_ENABLED`,
`NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED`) and
`web/lib/language-features.ts`. Flag doctrine: AGENTS.md "Feature Flags".

### RM-13. (Retired)

The feedback attachment picker was removed by PR #679 (`983e6d8e`) and is
not part of wave 1. Do not reintroduce it;
`web/e2e/feedback-dialog-no-attachments.spec.ts` guards it.

### RM-14. `web/public/manifest.json`

Exists: `name` and `short_name` "Argus", `description` "Test investing ideas
in plain language.", `lang` "en", `start_url` "/", `scope` "/", `display`
"standalone", theme and background `#191c1f`, icons 192, 512, maskable 512,
two screenshots. No `shortcuts`. It is served as-is; there is no service
worker in the repo.

### RM-15. Money-placement-pilot engine (reuse engine only, no UI)

Exists on remote branches only, never merged to integration:
`codex/money-placement-pilot` (tip `026be6d3`) and
`codex/money-placement-pilot-impl` (tip `429f5dd1`), in a separate app under
`money-view/`. Reusable engine parts:

- `money-view/server/platform/credit.py` `calculate_payoff()` (RM-8).
- `money-view/server/calculator.py`: Decimal placement comparison,
  `currency_minor_digits()`, `CalculationError(code)`, rounding once at the
  presentation edge (`present_result()`).
- `money-view/server/providers.py`: `SBProvider` (Superintendencia de Bancos
  deposit rates, parser `parse_sb_records()`), `BCRDProvider` placeholder.
- `money-view/server/argus_core/` is a synced COPY of Argus
  `src/argus/domain/calculations` and `finance` made by
  `money-view/scripts/sync_argus_core.py`. Never reuse from the copy; the
  owner is `src/argus/domain/`.

Rule: port the pure functions into `src/argus/domain/finance/` with their
tests; do not import from `money-view/`, and do not bring over any
`money-view/web` UI, its SQLite store, or its session model.

### RM-16. Logging and secrets hygiene

Exists (PR #691, `5fb0f079`): `configure_logging()` in
`src/argus/log_sink.py` removes the default Loguru handler and adds one with
`diagnose=False, backtrace=False`. It runs on `import argus`
(`src/argus/__init__.py`), at API startup (`src/argus/api/app_setup.py`), in
`workflows/main.py`, `workflows/backtest_job.py`, and the three ops scripts
under `scripts/ops/`. `src/argus/observability/log_sink.py` re-exports it. Tests:
`tests/test_log_sink.py`. New code must not add another Loguru sink or call
`logger.remove()`; use `configure_logging()` if a new entrypoint is added,
and add that entrypoint to `tests/test_log_sink.py`. R4 still applies: no
amounts in log fields.

### RM-17. Docs that each spec's PRs keep true

`docs/API_CONTRACT.md` (any endpoint or payload change), `docs/DATA_MODEL.md`
(any table, event property, or retention change), `docs/ARCHITECTURE.md`
(analytics and the pointer to the runtime calculation catalog
`get_calculation_declarations()` in `src/argus/domain/calculations/__init__.py`;
do not recreate a hand-maintained calculations table), `docs/PRODUCT.md`,
`.agent/designs/argus/DESIGN.md` (navigation), `docs/BREAKPOINTS.md`
(layout). Decision log: `docs/specs/argus-decision-log.md`. Wave 1 package
authority: `docs/specs/wave-1/README.md` and this directory's stage specs.
The earlier draft Wave 1 roadmap file proposed on PR #672 was dropped; do
not revive it.

### RM-18. Browser storage registry

Exists: every browser storage key must be registered in `STORAGE_REGISTRY`
in `web/lib/browser-storage.ts` (an ESLint rule bans direct
`localStorage`, `sessionStorage`, and `document.cookie`), and CI runs
`web/e2e/browser-storage-disclosure.spec.ts` to check the keys against the
privacy disclosure. Any new once-per-session marker (SPEC 0 events
`session_started`, `installed_app_opened`) goes through `writeSessionStored()`
and the registry, and the privacy page copy is updated in the same PR. The
invite cohort key `argus:invite-cohort:v1` (SPEC 0 0C-9) is registered the
same way, as `campaign`.

### RM-19. Render and release flags

Exists: `render.yaml` declares the web service `argus-app` env keys
(`[removed obsolete setting]`, `NEXT_PUBLIC_OMNISEARCH_ENABLED`, and others; it
also declares `NEXT_PUBLIC_POSTHOG_KEY`, which no web code reads).
`.github/private-alpha-release-profile.json` and
`tests/test_private_alpha_release_profile.py` check that flags are declared
consistently. A new `NEXT_PUBLIC_*` flag is added to `web/.env.example`,
`render.yaml`, and the release profile in the same PR; the internal team
sets hosted values.
