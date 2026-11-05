# SPEC 0. Stage 0: safety fixes and clean analytics

> **September 26, 2026 reconciliation:** Read
> [documentation authority](../../DOCUMENTATION_AUTHORITY.md) and the approved
> [MVEE](../argus-minimum-viable-ecosystem-experience.md) before using this spec.
> These Wave 1 package bodies and existing stage/review gates remain preserved
> for assigned work. Conflicting experience requirements need explicit package
> reconciliation; they are not permanent limits on the pivot. This notice does
> not cancel work, unlock stages, change technical contracts, or authorize
> exposing unfinished features. The original product/source text below remains
> a dated specification, not the final definition of the whole ecosystem.

Shared rules: `00-shared-rules.md` (Iris's R1 to R7, engineering rules E1 to
E7, reuse map RM-1 to RM-19). Integration tip used for this spec:
`5fb0f079b92ed5391da770cb9a7b89c1c4807684` (the #691 squash).

---

## Product half (Iris, verbatim)

Source: Iris, "Wave 1 specs: product halves", Revision 2 (Sep 25 2026).

## SPEC 0: Safety fixes and analytics

**Who it's for.** Every pilot user, indirectly. Before we invite anyone, the app has to be safe, honest about limits, and measurable.

**Why.** The summer launch had about 46 real users. None came back after day 7, and we couldn't see why. Wave 1's one number is **the share of signed-in pilot users who return between day 8 and day 30** (baseline 0). If we can't measure it on day one, the whole wave is unmeasurable. Early signal: the share who save a card or create a goal in their first week.

### 0A. Kept by our team (not contractors)
- **#691**: Loguru stops printing local variable values in logs, and the ops token compare stops crashing on non-ASCII input. After merge, James and Lucas decide whether to rotate the ops token and SMTP credential. The PR doesn't claim they leaked, so this is a decision, not an automatic step.
- **#681**: the guest claim 503 is localized, with a Retry countdown.

### 0B. Contractors
- **#693** (starts after #681 merges): the signed-in claim 503 gets the same treatment as #681. The daily cap 429 stops saying "wait a moment" and gives the real reset time.
  - ES: "Llegaste al límite de preguntas de hoy. Se reinicia a las {hora}."
  - EN: "You've reached today's question limit. It resets at {time}."
  - The cap resets at midnight UTC. `{hora}` / `{time}` is that moment converted to the user's local time zone, in 12-hour format: "8:00 p. m." / "8:00 PM" for a user in the DR. No "try again later" and no vague wait.
- **#692**: a replayed request or a 404 conversation must not use up a daily question. The product rule is that a user loses a question only when they got an answer, or a real failed attempt they can see. The one-time deploy-day IPv6 over-allowance is accepted in writing. The other IP edge cases (`ip:port`, non-canonical IPv4) are fixed or explicitly accepted in writing, per the issue.
- #675 (attachment picker) is already done in #679 and is not part of this stage.

### 0C. Analytics cleanup (contractors; Priya checks because it touches user data)
**Goal.** A small, trustworthy event set that answers one question: "Do pilot users come back, and what did they do in week one?" Fewer events recorded correctly beat many recorded loosely. Renames are a clean break, since there's no real traffic to preserve.

**Required events:**
1. `first_answer_shown`: the first completed answer a person sees. It fires for **guests and signed-in users** (today it fires for guests only). Properties: guest or signed-in, audience row of the chip used if any (`everyday` / `practitioner` / `none`), language.
2. `signed_in`: account created or signed in. Properties: new or returning, and the trigger (`save`, `goal`, `checklist`, `other`).
3. `card_saved`: a result was saved. Property: calculator type only.
4. `goal_created`: defined now so the list is complete; it fires in stage 2. Property: goal type (savings only in wave 1).
5. `checklist_step_completed`: property is the step (1, 2 or 3). Fires in stage 2.
6. `reminders_opted_in` / `reminders_opted_out`: property is the channel (`email` / `push`). Fires in stage 3.
7. `session_started`: signed-in users only. Property: whole days since sign-up. This single event computes the one number (a session on day 8 through day 30). Don't build a separate "returned" event.
8. `installed_app_opened`: Argus opened in standalone (home-screen) mode. Fires at most once per session.

**Guest-to-account link.** Guests and accounts are not linked today. When a guest signs up, the account's first events carry a **hashed guest id** as a property, so we can measure guest-to-account conversion. No person profiles, no aliasing, and no personal data.

**Hard rules for events:**
- No amounts, no question or answer text, no names, no emails, and no free text of any kind in any property.
- Signed-in users are identified by an internal pseudonymous id, never by email. Guests get a random id that ends with the 7-day guest reset. The only link to an account is the hashed guest id above.
- Our team's test accounts are excluded or flagged so they never count toward the number.
- No ad tracking: no ad pixels, and click ids such as `fbclid` are dropped.

**Out of scope:** dashboards beyond one saved query or view for the one number and the week-one signal, A/B testing, marketing pixels, and third-party ad tracking.

**How we'll know stage 0 worked:**
- On staging, one scripted test user fires each event once, and the query shows exactly those events, with no amounts or text.
- The one number (signed-in pilot users with a `session_started` between day 8 and day 30, divided by all signed-in pilot users) comes from a saved query, even while it reads 0.

**Acceptance checks:**
- **A1.** #691, #681, #692 and #693 are merged under the review gate.
- **A2.** The daily cap message shows the real local reset time in es-419 and EN (8:00 PM for a DR time zone), with screenshots of both.
- **A3.** A replayed request and a 404 conversation leave the daily question count unchanged (tests).
- **A4.** The event list exists with exactly those properties. A test or lint fails if any event property holds a money-formatted number or free text.
- **A5.** `first_answer_shown` fires for both guests and signed-in users (test).
- **A6.** A guest who signs up produces account events carrying the hashed guest id, and no personal data (test).
- **A7.** Test accounts are excluded from the one-number query.
- **A8.** Priya has signed off on 0C.

### Iris's round 2 answers that apply to SPEC 0 (verbatim)

Source: "Answers to Yelena, round 2" in Iris's product halves. Where these
answers change an item above, the answer wins (for example the event count).

**2. `landing_viewed`: yes.** It's the 9th event, for guests and signed-in users, with language as its only property. It fires once per landing view (not on every re-render). The stage 1 leading indicator becomes `first_answer_shown` divided by `landing_viewed`, among first-session visitors.

**3. Invite-link cohort tag: in wave 1, stage 0.** The one number is about *pilot* users, and we can only count them if we can tell the roughly 20 hand-recruited DR users apart from anyone else who finds the site. Keep it minimal:
- The invite link carries a short cohort code (for example `piloto-1`). No names, emails or personal data are in the link.
- The code is stored on the account at sign-up (or carried from the guest session when the guest signs up).
- Add `cohort` as a property on `signed_in` and `session_started`. Guests who arrive through an invite link carry it on `first_answer_shown` and `landing_viewed` too.
- Other campaign fields (utm and similar) stay out of wave 1.
- New check A9: an account created through an invite link shows its cohort on `signed_in` and `session_started`, and the one-number query can filter to pilot users by cohort.

**4. Share analytics: add `receipt_shared` as the 10th event.** Sharing stays on and could become a way new users arrive, so I don't want to be blind to it. Its property is the calculator type only; no share id, no question text, no amounts. We don't track share-page views or a share funnel in wave 1. If shares turn out to matter, we add that later.

Updated event count: 10 (the 8 in 0C, plus `landing_viewed` and `receipt_shared`), with the `cohort` property added to four of them.

### Iris's round 3 answer that applies to SPEC 0 (verbatim)

Source: "Answers to Yelena, round 3" in Iris's product halves.

**Cohort codes.** Agreed that there's no allowlist in wave 1. Product rule: the real pilot codes are hard to guess, for example `piloto-7kq2` rather than `piloto-1`. That way a stranger typing a guessed `?ref=` doesn't get counted as a pilot user in the one number. Lucas or I pick the code when the invite links are drafted.

---

## Engineering half

### 0.1 Ownership and status at `5fb0f079`

- 0A stays with the internal team.
  - #691 is MERGED (squash `5fb0f079`, closes #682). The token and SMTP
    rotation decision (James and Lucas) is tracked outside this spec.
  - #681 is OPEN (head `fff96b69`). Contractors do not touch the files it
    changes until it merges. Package 0B-1 (#693) starts only after it merges.
- Every other package below is contractor-ready unless marked "internal".

### 0.2 What exists and is reused (see the reuse map)

| Need | Reuse | Map |
| --- | --- | --- |
| Log safety | `configure_logging()` in `src/argus/log_sink.py` (merged) | RM-16 |
| Guest claim 503 in the web | `Retry-After` parser, recovery-code mapping, Retry pill countdown, `ChatStreamError` carrying `Retry-After`, all from PR #681 | RM-4 |
| 429 and 503 in the API | `guest_compute_ceiling.py`, `registered_compute_ceiling.py`, `usage_limits.py`; the chat 429 already sends `Retry-After` = seconds to the next UTC midnight, and these two files are the only 429 sources on the chat route | RM-4 |
| Client IP keying | `src/argus/api/client_ip.py`, `visitor_key_for_request()` | RM-4 |
| Event sink | `envelope.py` (`capture_event()`, sanitizer, PostHog host config) | RM-1 |
| Once-per-subject events | milestone claim (`milestone_emission_allowed()` in `guest_observability.py`, migration `20260808120000_add_guest_funnel_milestones.sql`) | RM-1 |
| Pseudonymous ids | `actor_hash_for_user()` in `product_events.py` | RM-2 |
| Internal account role | `private_alpha_role_for_email()` and the role check in `personalization_memory.py` | RM-3 |
| Existing emit points to rename | `emit_first_guest_message_event()`, the three handoff-claim sites in `routers/auth.py`, `_emit_account_registration_completed_event()`, the two `decision_capture` sites | RM-1 |
| Client event endpoint pattern | `POST /api/v1/analytics/guest-events` (`routers/analytics.py`, rate limiter, background capture) | RM-1 |
| Session markers in the browser | `writeSessionStored()` and `STORAGE_REGISTRY` in `web/lib/browser-storage.ts` | RM-18 |

### 0.3 What is genuinely new

1. #692: the daily claim moves after idempotency and conversation lookup,
   and `ip:port` and non-canonical IPv4 get an explicit rule.
2. #693: signed-in claim 503 handling and the honest daily-cap copy, built on
   #681's helpers (no second parser).
3. One closed analytics registry for Iris's 10 events (below), with one
   Pydantic model per event, so a property that is not in Iris's list, or
   free text, cannot be represented. PostHog receives each event under its own
   name. Every other current event stops going to PostHog (clean break).
4. `internal_account` on every event, and the eval harness stops writing to
   the product stream.
5. `first_answer_shown` for guests and signed-in users.
6. `signed_in` for every sign-up and sign-in path, carrying `guest_id_hash`
   when the account came from a guest.
7. A small authenticated client endpoint for the two browser-detected events
   (`session_started`, `installed_app_opened`).
8. `fbclid` is removed from browser capture.
9. `landing_viewed` (guests and signed-in) and `receipt_shared`.
10. An invite cohort code: accepted at the API as one closed, pattern-checked
    field, stored on the profile, carried from a guest to the account, and
    sent as `cohort` on four events. No other campaign field reaches the API.

### 0.4 Data and schema changes

- No new table. The milestone claim table is reused for once-per-subject
  events (`first_answer_shown`).
- ONE MIGRATION (package 0C-9): `alter table public.profiles add column if
  not exists invite_cohort text` with a check constraint
  `invite_cohort ~ '^[a-z]{2,12}-[a-z0-9]{4,8}$'`, following the shape of
  `20260911120000_add_profile_home_country.sql`. No RLS change (profiles
  RLS already limits a row to its owner; the column is written only by the
  API with the service role and is not user-editable in Settings). Written
  and tested locally (`scripts/qa/write-local-env.sh`), applied by the
  internal team (E5). Because it is a migration on user data, 0C-9 carries
  the Priya plus Codex re-review gate.
- No migration for #692 if the claim is moved (preferred). If a refund RPC
  is chosen instead, it follows E5 and the E6 extra gate.
- `docs/API_CONTRACT.md`: new `POST /api/v1/analytics/client-events`
  (0C-5); `/auth/signup` and `/auth/guest` stop taking the `attribution`
  object and take one optional `invite_cohort` string instead (0C-9);
  `fbclid` is never sent (0C-7).
- `docs/DATA_MODEL.md`: `profiles.invite_cohort` (0C-9).
- `docs/DATA_MODEL.md` (observability section near line 1220): replace the
  event list with the 10 events, their exact properties, the technical
  properties, and the saved-query filter.
- Privacy page copy: the two new session markers (RM-18).

### 0.5 Iris's 10 events mapped to code

Technical properties allowed on every event, and nothing else besides the
event's own properties: `environment`, `internal_account`, `schema_version`,
`event_id`, `$process_person_profile` (always `false`). `distinct_id` is
`actor_hash_for_user(user id)`: the account id for signed-in users, the guest
user id for guests (a guest id ends with the 7-day guest workspace, see
Clashes resolved C4). The envelope's other outputs (`conversation_id_hash`,
`message_id_hash`, `status`, `latency_ms`, nested `attributes`) are not sent
for these events.

| # | Iris event | Properties (exact names and values) | Comes from today | Fires at (after SPEC 0) | Package |
| --- | --- | --- | --- | --- | --- |
| 1 | `first_answer_shown` | `account_kind`: `guest` or `signed_in`; `chip_audience`: `everyday`, `practitioner`, `none`; `language`: `en` or `es-419`; `cohort` for guests with a stored cohort only | `first_useful_assistant_response_completed` (guests only) | server, when the first completed assistant answer of a subject is persisted (text, calculation, research, or backtest result); once per subject via the milestone claim. `chip_audience` is `none` until SPEC 1 package 1B-2 sends it | 0C-3 |
| 2 | `signed_in` | `signup`: `new` or `returning`; `trigger`: `save`, `goal`, `checklist`, `other`; `guest_id_hash` only when the account came from a guest; `cohort` when the account has one | `account_creation_completed`, `existing_account_sign_in_completed`, `account_registration_completed`; a plain email login emits nothing today | `routers/auth.py`: signup, login, and the three guest-handoff claim sites; `distinct_id` is the ACCOUNT. `trigger` from the conversion reason (`save_decision` becomes `save`; others `other`; `goal` and `checklist` arrive in stage 2) | 0C-4 |
| 3 | `card_saved` | `calculator`: one of the registered calculation names or `backtest` | `decision_capture` (two sites) | `src/argus/api/chat/decisions.py` and `src/argus/api/chat/evidence.py` | 0C-4 |
| 4 | `goal_created` | `goal_type`: `savings` | none | registered only; fires in stage 2 | 0C-1 |
| 5 | `checklist_step_completed` | `step`: `1`, `2`, `3` (integer literal) | none | registered only; fires in stage 2 | 0C-1 |
| 6 | `reminders_opted_in` / `reminders_opted_out` | `channel`: `email` or `push` | none | registered only; fire in stage 3 | 0C-1 |
| 7 | `session_started` | `days_since_signup`: integer, 0 or more, computed on the server from the profile's `created_at`; `cohort` when the account has one | none | client posts once per browser session to `/analytics/client-events`; server rejects guests (signed-in only) | 0C-5 |
| 8 | `installed_app_opened` | none | none | client posts when `matchMedia("(display-mode: standalone)")` matches, at most once per session; guests and signed-in | 0C-5 |
| 9 | `landing_viewed` | `language`: `en` or `es-419`; `cohort` for guests with a stored cohort only | none | client posts once per landing view (each time the empty-chat landing surface is shown; guarded against re-renders and React strict-mode double mounts) to `/analytics/client-events`; guests and signed-in | 0C-5 |
| 10 | `receipt_shared` | `calculator`: a registered calculation name, `backtest`, `multiple` (more than one kind in the shared turns), or `none` (no calculation) | `receipt_created` (which also sends a receipt digest; Iris forbids a share id) | `src/argus/api/routers/evidence_receipts.py`, the two `if created:` sites (near lines 204 and 385); only a real insert counts, as today | 0C-8 |

`cohort` is the only string property that is not a fixed literal. It is
restricted at the boundary to `^[a-z]{2,12}-[a-z0-9]{4,8}$` (for example
`piloto-7kq2`; see 0C-9), stored with the same database check, and typed in the event
model as that constrained string, so it cannot carry free text. The A4 lint
allows exactly this one constrained-string field.

Current events and what happens to each (clean break, Iris 0C):

| Current event | Result |
| --- | --- |
| `first_useful_assistant_response_completed` | renamed to `first_answer_shown` |
| `account_creation_completed`, `existing_account_sign_in_completed`, `account_registration_completed` | replaced by `signed_in` |
| `decision_capture` | renamed to `card_saved` |
| `guest_session_started`, `starter_action_selected`, `confirmation_reached`, `first_simulation_admitted`, `first_result_completed`, `conversion_prompt_shown`, `temporary_workspace_claimed`, `guest_limit_reached`, `guest_feedback_submitted`, `guest_session_expired` | no longer sent to PostHog. Emit calls removed; milestone and cleanup logic that has other uses stays |
| `evidence_capture`, `recall_usage`, `continuity_mismatch`, `compare_started`, `next_experiments_offered`, `next_experiment_selected` | no longer sent to PostHog; logging with `loguru` is allowed if a caller needs it (no amounts, R4) |
| `eval_readiness` | no longer sent anywhere by the eval harness to PostHog |
| `receipt_created` | replaced by `receipt_shared` (calculator only; the digest and kind attributes are no longer sent) |
| `receipt_revoked`, `receipt_viewed`, `receipt_try_argus`, `receipt_followed_up`, `receipt_signed_up` | no longer sent to PostHog (Iris: no share-page views or share funnel in wave 1); sharing unchanged. `/public/receipt-funnel` becomes a no-op 204 so old pages do not error |
| research turn event (`research_events.py`) | no longer sent to PostHog |
| `POST /api/v1/analytics/guest-events` | removed with its two client events (web callers in `web/lib/guest-analytics.ts`, `useGuestConversion.ts`, `useGuestExperience.ts`) |

### 0.6 Work packages

Merge order: 0B-2, 0B-1 (after #681), 0C-1, 0C-2, 0C-9, 0C-3, 0C-4, 0C-5,
0C-8, 0C-7, then internal 0C-6. 0C-9 lands before the emitters because
0C-3, 0C-4, and 0C-5 read the stored cohort. 0C-7 and 0C-9 both edit
`web/lib/landing-intent.ts`; 0C-7 reconciles onto 0C-9. 0C-8 needs only
0C-1 and 0C-2 but merges after 0C-5 so the event PRs land one at a time.

Done when, for every package unless it lists more: the Outcome holds,
every named test passes in CI on the PR head (local runs attached where a
test is not in CI), the gate is met (E6, plus the extra gate where named),
the docs it names are updated in the same PR, and the PR is squash-merged
into `codex/private-alpha-next`.

#### 0A-1. #691 (internal): DONE

Merged as `5fb0f079`. No further stage 0 work. Counts toward A1.

#### 0A-2. #681 guest claim 503 (internal)

- Outcome: PR #681 merged. Tests as listed in the PR, including the local
  run of `web/e2e/guest-compute-claim-503.spec.ts` (not in CI).
- Done when: merged into `codex/private-alpha-next` with the gate below.
- Depends on: nothing. Gate: E6 plus Priya and Codex re-review (user-facing limit message).

#### 0B-1. Signed-in claim 503 and honest daily-cap copy (#693)

- Outcome: `registered_compute_claim_unavailable` gets the #681 treatment
  (localized notice, disabled Retry with countdown, clamp 1 to 120 s, 15 s
  fallback, one manual retry, transcript survives a repeated 503). The chat
  429 shows Iris's copy with the reset time.
- Copy (Iris, exact): ES "Llegaste al límite de preguntas de hoy. Se
  reinicia a las {hora}." EN "You've reached today's question limit. It
  resets at {time}." Keys: `chat.recovery.daily_cap_reached` in both files,
  with i18next interpolation `{{time}}` in both languages (the placeholder
  name in code is `time`; the visible text is Iris's).
- Reset time: the next midnight UTC after the moment the 429 was received,
  computed as `now + Retry-After seconds` and rounded to the minute, then
  formatted with `Intl.DateTimeFormat(language, { hour: "numeric",
  minute: "2-digit", hour12: true })` in the browser's time zone. For DR
  (`America/Santo_Domingo`, UTC-4) this reads "8:00 p. m." in es-419 and
  "8:00 PM" in EN. If `Retry-After` is missing or unparsable, compute the
  next midnight UTC from the client clock instead (the cap is defined as
  midnight UTC, so this is still exact). Never show a vague wait (Iris).
- Files: the #681 helpers (extend the code-to-copy map to the second 503
  code; do not copy the parser), `web/components/chat/ChatInterface.tsx`
  (the raw `err.message` fallback near line 1728),
  `web/lib/chat-recovery-display.ts`, both locale files.
- Tests:
  - `web/__tests__/chat-recovery-display.test.ts`: signed-in 503 maps to its
    key and never returns backend detail; chat 429 maps to
    `chat.recovery.daily_cap_reached`.
  - new `web/__tests__/daily-cap-reset-time.test.ts`: `America/Santo_Domingo`
    gives "8:00 p. m." (es-419) and "8:00 PM" (EN); a UTC+ zone rolls to the
    next local date correctly; missing header uses the client-clock midnight.
  - `web/__tests__/locales.test.ts`: exact Iris copy in both files, no
    U+2014, and no "wait a moment" left in the chat 429 path.
  - new `web/e2e/registered-compute-claim-503.spec.ts` and
    `web/e2e/daily-cap-429.spec.ts` (guest and signed-in), run with
    Playwright `timezoneId: "America/Santo_Domingo"`. Local runs attached.
  - Screenshots, es-419 and EN, before and after (A2).
- Depends on: 0A-2. Gate: E6 plus Priya and Codex re-review.

#### 0B-2. A question is used only by an answer or a visible failure (#692)

- Outcome: a replayed request (same idempotency key) and a turn for an
  unknown conversation (404) leave the daily count unchanged, for guests and
  signed-in users. `ip:port` in the trusted header has the port stripped;
  non-canonical IPv4 (leading zeros) is rejected to the peer address with a
  distinct log line (`client_ip_rejected_non_canonical`), or both are
  accepted in writing on the issue by Yelena. The deploy-day IPv6 /64
  over-allowance is accepted (Iris 0B); the PR records that in `## Risks`.
- Files: `src/argus/api/chat/agent.py` (move both claim calls from near line
  297 to after the idempotency check and conversation resolution near line
  420), `src/argus/api/chat/guest_compute_ceiling.py`,
  `src/argus/api/chat/registered_compute_ceiling.py`,
  `src/argus/api/client_ip.py`, `docs/API_CONTRACT.md` if the error order
  changes (a 404 now wins over a 429 for an unknown conversation).
- Tests (fail first on the old tree, AGENTS.md Standard 3):
  - `tests/test_registered_compute_ceiling.py::test_replayed_idempotency_key_does_not_consume_a_unit`
  - `tests/test_registered_compute_ceiling.py::test_unknown_conversation_404_does_not_consume_a_unit`
  - `tests/test_guest_compute_ceiling.py::test_replayed_idempotency_key_does_not_consume_a_guest_unit`
  - `tests/test_guest_compute_ceiling.py::test_unknown_conversation_404_does_not_consume_a_guest_unit`
  - `tests/test_guest_compute_ceiling_security.py::test_trusted_header_ip_with_port_strips_port`
  - `tests/test_guest_compute_ceiling_security.py::test_non_canonical_ipv4_falls_back_and_logs`
  - Postgres variants in `tests/test_guest_compute_claim_postgres.py` and
    `tests/test_registered_compute_claim_postgres.py` if the claim SQL
    changes.
- Depends on: nothing (0A-1 is merged). Gate: E6 plus Priya and Codex
  re-review (security).

#### 0C-1. Closed event registry, PostHog names, clean break

- Outcome: one registry owns the 10 events (0.5). PostHog receives each under
  its own name. Every other product and guest-funnel event stops reaching
  PostHog. A test fails if any event can hold a property outside Iris's
  list, free text, or a money-formatted value (A4).
- Files (new): `src/argus/observability/analytics_events.py`: one Pydantic
  model per event (`extra="forbid"`, fields typed only as `Literal[...]`,
  `bool`, or bounded `int`), a `capture_analytics_event(event, *, user_id,
  guest_user_id=None, internal_account)` that builds the envelope and calls
  `capture_event()`. (changed): `src/argus/observability/envelope.py`
  (`posthog_event_payload()` uses the analytics event name; analytics events
  send only the technical properties plus the model's fields),
  `src/argus/observability/product_events.py` and `guest_funnel.py` (remove
  PostHog output; keep `actor_hash_for_user()`, `milestone_subject()`,
  `is_milestone_event()` where still used), remove the unmapped emit calls
  listed in 0.5, remove `POST /analytics/guest-events` and its web callers,
  make `/public/receipt-funnel` a no-op 204, `tests/evals/chat_runtime_eval_harness.py`
  (no product event), `docs/DATA_MODEL.md`.
- Tests:
  - new `tests/test_analytics_events.py::test_registry_is_exactly_irises_events`
    (the set of names equals the 11 names of 0.5: 10 events, reminders
    counted as two names)
  - `tests/test_analytics_events.py::test_every_property_is_literal_bool_or_bounded_int`
    (introspects every model; any `str` field that is not a `Literal`
    fails, except the one `cohort` constrained string: this is the A4 lint)
  - `tests/test_analytics_events.py::test_money_formatted_value_is_rejected`
    (for example `"RD$5,000"` or `"5000.00"` into every field fails
    validation)
  - `tests/test_analytics_events.py::test_payload_has_only_technical_and_event_properties`
  - `tests/test_observability_envelope.py::test_posthog_event_name_is_the_analytics_event_name`
  - `tests/test_analytics_events.py::test_removed_events_do_not_reach_posthog`
    (drives each old emit path with a fake sink and asserts no capture)
  - update `tests/evals/test_chat_runtime_eval_manifest.py` so no product
    event is emitted; update `tests/test_public_excerpt_api.py` receipt
    funnel assertions to the no-op.
- Depends on: nothing. Gate: E6 plus Priya and Codex re-review (user data).

#### 0C-2. Test accounts flagged and excluded

- Outcome: every event carries `internal_account`. It is `true` when the
  signed-in email's allowlist role is `admin` or `developer`, when the
  process runs eval tooling, or under mock auth. Guests are `false`. If the
  role lookup fails, the event is still sent with `internal_account: true`
  (fail closed: an unknown account never counts toward the number).
- Files: one shared resolver in `src/argus/api/` used by both analytics and
  `personalization_memory.py` (extract the role set once; Split-Brain
  Rule), `analytics_events.py`, `docs/DATA_MODEL.md`,
  `docs/PRIVATE_LAUNCH_RUNBOOK.md` (the filter).
- Tests:
  - `tests/test_analytics_events.py::test_admin_and_developer_are_internal`
  - `tests/test_analytics_events.py::test_role_lookup_failure_marks_internal`
  - `tests/test_analytics_events.py::test_guest_is_not_internal`
  - `tests/test_analytics_events.py::test_mock_auth_is_internal`
- Depends on: 0C-1. Gate: E6 plus Priya and Codex re-review.

#### 0C-3. `first_answer_shown` for guests and signed-in users

- Outcome: the first completed assistant answer per subject fires
  `first_answer_shown` once, for both account kinds (A5).
- Files: `src/argus/api/guest_observability.py` (replace the
  "guest message count equals 1" check in `emit_first_guest_message_event()`
  with the milestone claim for both kinds, keyed by `milestone_subject()`
  for guests and the account actor for signed-in users; rename the function
  to `emit_first_answer_event()`), `src/argus/api/chat/measurement_events.py`
  (call it for signed-in turns too, and for backtest result turns),
  `src/argus/api/routers/backtest.py` if the backtest result is persisted
  there.
- Tests:
  - `tests/test_guest_observability.py::test_first_answer_shown_fires_once_for_guest`
  - `tests/test_guest_observability.py::test_first_answer_shown_fires_once_for_signed_in`
  - `tests/test_guest_observability.py::test_failed_turn_does_not_fire_first_answer`
  - `tests/test_guest_funnel_milestone_idempotency.py::test_first_answer_claim_is_idempotent`
- `cohort`: set for guests whose guest profile has `invite_cohort` (0C-9);
  omitted for signed-in users. Test:
  `tests/test_guest_observability.py::test_first_answer_carries_cohort_for_invited_guest_only`.
- Depends on: 0C-1, 0C-9. Gate: E6 plus Priya and Codex re-review.

#### 0C-4. `signed_in` with `guest_id_hash`, and `card_saved`

- Outcome: every sign-up and sign-in emits one `signed_in` on the account's
  `distinct_id`. When the account came from a guest (a non-replayed handoff
  claim), `guest_id_hash` = `actor_hash_for_user(<guest user id>)`, which is
  the same hash the guest's own events used as `distinct_id`, so conversion
  can be joined without person profiles or aliasing (A6). Saving a card emits
  `card_saved` with `calculator` only.
- Files: `src/argus/api/routers/auth.py` (signup, login, and the claim sites
  near lines 448, 739, 937), `src/argus/api/chat/decisions.py`,
  `src/argus/api/chat/evidence.py`.
- Tests:
  - `tests/test_guest_auth.py::test_guest_signup_emits_signed_in_with_guest_id_hash_and_no_personal_data`
    (asserts the payload has no email, name, or raw id)
  - `tests/test_guest_auth.py::test_replayed_claim_emits_no_second_signed_in`
  - `tests/test_auth_sessions.py::test_plain_login_emits_signed_in_returning_other`
  - `tests/test_auth_sessions.py::test_plain_signup_emits_signed_in_new_without_guest_hash`
  - a decisions test: `test_card_saved_carries_only_calculator`
  - `tests/test_guest_auth.py::test_signed_in_carries_account_cohort`
- `signed_in` sets `cohort` from the account's `invite_cohort` after the
  claim or signup has written it (0C-9).
- Depends on: 0C-1, 0C-2, 0C-9. Gate: E6 plus Priya and Codex re-review.

#### 0C-5. `session_started`, `installed_app_opened`, `landing_viewed`

- Outcome: the browser reports `session_started` and `installed_app_opened`
  once per browser session, and `landing_viewed` once per landing view; the
  server validates and emits them, adding `language` from the profile and
  `cohort` per 0.5. `landing_viewed` is sent from the current empty-chat
  surface (`EmptyChatSurface.tsx`) in stage 0, and SPEC 1's new landing keeps
  the same call.
- Files (new): `POST /api/v1/analytics/client-events` in
  `src/argus/api/routers/analytics.py` with body `{ "event":
  "session_started" | "installed_app_opened" | "landing_viewed" }` only (no other fields; the
  server computes `days_since_signup` from the profile's `created_at` and
  rejects `session_started` for guests with 204 and no capture), rate limit
  key `client-event:user:<id>`; `web/lib/client-analytics.ts` (called once
  from the app shell after auth resolves). (changed):
  `web/lib/browser-storage.ts` (`argus:session-events:v1` in
  `STORAGE_REGISTRY` as `temporary`, written with `writeSessionStored()`),
  privacy page copy, `docs/API_CONTRACT.md`.
- Tests:
  - `tests/test_analytics_client_events.py::test_session_started_computes_days_since_signup_on_server`
  - `...::test_session_started_ignored_for_guest`
  - `...::test_unknown_event_is_422`
  - `...::test_client_events_are_rate_limited`
  - `...::test_landing_viewed_for_guest_and_signed_in_with_language_only`
  - `...::test_session_started_and_landing_viewed_carry_cohort_per_rules`
  - new `web/__tests__/client-analytics.test.ts`: session events fire once
    per session; `installed_app_opened` only when standalone;
    `landing_viewed` fires once per landing view and not on re-render or a
    strict-mode double mount.
  - `web/e2e/browser-storage-disclosure.spec.ts` stays green (CI).
- Depends on: 0C-1, 0C-2, 0C-9. Gate: E6 plus Priya and Codex re-review.

#### 0C-8. `receipt_shared`

- Outcome: creating a share link (a real insert only) emits `receipt_shared`
  with `calculator` only. No share id, digest, question text, or amount.
- Files: `src/argus/api/routers/evidence_receipts.py` (both `if created:`
  sites), one small helper that maps the snapshot's turns to one
  `calculator` value (the single calculation kind, `backtest`, `multiple`,
  or `none`), reading the kinds already on the snapshot rather than
  re-deriving them.
- Tests: `tests/test_public_excerpt_api.py::test_receipt_shared_carries_only_calculator`,
  `::test_resharing_same_result_emits_nothing`,
  `::test_receipt_shared_values_for_backtest_multiple_and_none`.
- Depends on: 0C-1, 0C-2. Gate: E6 plus Priya and Codex re-review.

#### 0C-9. Invite cohort code (migration)

- Outcome: an invite link `https://<host>/?ref=<code>` (for example
  `ref=piloto-7kq2`) stores the code on the account at sign-up, or on the guest
  profile at guest start and then on the account when that guest signs up.
  No other campaign field reaches the API.
- Decision (Lucas, Sep 25 2026) and product rule (Iris, round 3):
  - No allowlist in wave 1. The server keeps no list of valid codes.
  - The server accepts only one short fixed format:
    `^[a-z]{2,12}-[a-z0-9]{4,8}$`. That is a lowercase word of 2 to 12
    letters, a hyphen, then 4 to 8 lowercase letters or digits. Accepted:
    `piloto-7kq2`. Rejected (422 at the API, ignored in the browser):
    `piloto-1` (suffix under 4), `Piloto-7kq2` (uppercase),
    `piloto_7kq2`, `piloto-7kq2-x`, `piloto 7kq2`, empty, and anything
    longer than 21 characters. The 4-character minimum rules out short
    sequence codes like `piloto-1`; the random suffix (next point) is what
    makes a real code hard to guess.
  - Real pilot codes are hard to guess (Iris): the suffix is at least 4
    characters chosen at random, not a sequence number. The server cannot
    check randomness; Lucas or Iris picks the code when the invite links
    are drafted. Staging uses its own code (`qa-t7k2`), never a pilot code.
  - The cohort is analytics only. It never grants or blocks access, and
    never changes caps, features, prices, copy, or model behavior. No code
    path other than the analytics emitters and the claim copy reads it
    (test below).
  - The pattern has three copies that must agree (Split-Brain Rule): the
    Pydantic type, the database check, and the browser guard. One shared
    fixture `tests/fixtures/invite_cohort_codes.json` (accepted and
    rejected lists above) is read by the pytest and vitest tests, and the
    migration test runs the same list against the check constraint.
- Browser: `web/lib/landing-intent.ts` keeps its first-touch attribution
  object unchanged for local use, but `attributionBody()` is replaced by
  `inviteCohortBody()`, which sends only `{ "invite_cohort": "<code>" }`
  or nothing. The code is captured into its own key
  `argus:invite-cohort:v1` (register in `STORAGE_REGISTRY` as `campaign`;
  privacy copy updated) on ANY visit that carries a valid `ref` while no
  cohort is stored yet, so an invite link still counts when the person had
  visited earlier without one (the first-touch rule in `landing-intent.ts`
  would otherwise drop it). Invalid codes are ignored in the browser.
- API boundary: in `src/argus/api/schemas.py` add
  `invite_cohort: InviteCohort | None = None` to `SignupRequest` and
  `GuestBootstrapRequest`, where `InviteCohort =
  Annotated[str, StringConstraints(pattern=r"^[a-z]{2,12}-[a-z0-9]{4,8}$")]`.
  A value that fails the pattern is a 422 (the browser only sends valid
  codes, so a 422 means a crafted request). The request models stop
  receiving `attribution`; set `model_config = ConfigDict(extra="ignore")`
  explicitly on both so an old cached client that still sends
  `attribution` does not break sign-up during rollout, and add a test that
  `attribution` content is never stored or emitted.
- Persistence: `supabase/migrations/<timestamp>_add_profile_invite_cohort.sql`
  (0.4). Written in `src/argus/api/routers/auth.py` at signup and guest
  bootstrap through the gateway (`src/argus/domain/supabase_gateway.py`
  and the in-memory store). Never overwritten once set. On a non-replayed
  guest handoff claim (`claim_guest_workspace_handoff()` in
  `src/argus/domain/supabase_guest_accounts.py`), copy the guest profile's
  cohort to the destination profile if the destination has none.
  `User` in `schemas.py` gets `invite_cohort` for server use only; it is not
  returned by `GET /me` and not editable (no profile PATCH field).
- Tests:
  - `tests/test_guest_auth.py::test_guest_bootstrap_stores_valid_invite_cohort`
  - `tests/test_auth_sessions.py::test_signup_stores_valid_invite_cohort`
  - `tests/test_auth_sessions.py::test_invalid_invite_cohort_is_422`
  - `tests/test_auth_sessions.py::test_attribution_payload_is_ignored_and_never_stored`
  - `tests/test_guest_auth.py::test_guest_claim_copies_cohort_to_account_without_one`
  - `tests/test_guest_auth.py::test_existing_account_cohort_is_never_overwritten`
  - new `tests/test_invite_cohort_migration.py` (pattern of
    `tests/test_avatar_theme_migration.py`): column exists, check
    constraint accepts and rejects exactly the shared fixture lists
  - new `tests/test_profile_invite_cohort.py`: `invite_cohort` absent from
    `GET /me` and rejected by the profile PATCH
  - `tests/test_auth_sessions.py::test_invite_cohort_format_matches_shared_fixture`
    (every accepted code stored, every rejected code 422)
  - `tests/test_invite_cohort_analytics_only.py::test_only_analytics_and_claim_read_invite_cohort`
    (a `git grep`-style scan of `src/` that fails if `invite_cohort` is read
    outside the analytics emitters, the auth write path, the gateway, and
    the claim copy)
  - `web/__tests__/landing-intent-requests.test.ts`: signup and guest bodies
    carry only `invite_cohort`; a later invite visit after an organic first
    visit still stores the cohort; the browser guard accepts and rejects
    exactly the shared fixture lists
  - `web/e2e/browser-storage-disclosure.spec.ts` green
- Docs: `docs/API_CONTRACT.md` first, `docs/DATA_MODEL.md`, privacy page.
- Done when: all tests above pass in CI, the migration test passes on
  local Supabase with the run attached to the PR, `docs/API_CONTRACT.md`
  and `docs/DATA_MODEL.md` describe the field and the format, and the
  internal team has applied the migration to staging.
- Depends on: 0C-1. Gate: E6 plus Priya and Codex re-review (database
  migration and user data).

#### 0C-7. `fbclid` dropped

- Outcome: the browser never stores or sends `fbclid`.
- Files: `web/lib/landing-intent.ts` (remove it from
  `CAMPAIGN_VALUE_FIELDS`; existing stored values lose the key on next read),
  `docs/API_CONTRACT.md`.
- Tests: `web/__tests__/landing-intent.test.ts::drops fbclid` and
  `web/__tests__/landing-intent-requests.test.ts` (no `fbclid` in signup or
  guest bodies).
- Depends on: nothing. Gate: E6 plus Priya and Codex re-review (consent).

#### 0C-6. Saved queries and staging run (internal)

- Outcome: in PostHog, one saved query for the one number (signed-in users
  with `session_started` where `days_since_signup` is 8 to 30, divided by all
  signed-in pilot users), and one for the week-one signal (`card_saved`, and
  `goal_created` once stage 2 ships, within 7 days of `signed_in` with
  `signup = new`). Both filter `environment = production` and
  `internal_account = false` (A7), and each has a `cohort` breakdown and a
  saved "pilot users" filter on the pilot cohort codes (A9). A third saved
  query is the stage 1 leading indicator: distinct visitors with
  `first_answer_shown` divided by distinct visitors with `landing_viewed`,
  both in the visitor's first session (first day seen). On staging, a
  scripted test user arriving through `?ref=qa-t7k2` fires each event
  that has a trigger in stage 0 (`landing_viewed`, `first_answer_shown`,
  `signed_in`, `card_saved`, `session_started`, `installed_app_opened`,
  `receipt_shared`) once, and an unfiltered query shows exactly those, with
  the cohort where 0.5 says, and no amounts or text. A visit with
  `?ref=piloto-1` (wrong format) shows no cohort.
- Done when: the three saved queries exist in PostHog, their links and a
  screenshot of the staging run are on the stage 0 closing issue, and
  Priya has signed off (A7, A8, A9).
- Contractors have no PostHog access (E5).
- Depends on: every other 0C package merged and deployed to staging.
  Gate: Priya's written verdict plus Yelena's confirmation (internal, no PR
  unless docs change; a docs change follows E6).

### 0.7 Acceptance checks mapped to packages

| Check | Evidence | Package |
| --- | --- | --- |
| A1 | #691 merged (`5fb0f079`); #681, #692, #693 merged with the E6 gate | 0A-1 (done), 0A-2, 0B-2, 0B-1 |
| A2 | `daily-cap-reset-time.test.ts` DR case plus es-419 and EN screenshots of the 429 notice | 0B-1 |
| A3 | the four replay and 404 tests in 0B-2 | 0B-2 |
| A4 | `test_registry_is_exactly_irises_events`, `test_every_property_is_literal_bool_or_bounded_int`, `test_money_formatted_value_is_rejected`, `test_payload_has_only_technical_and_event_properties` | 0C-1 |
| A5 | `test_first_answer_shown_fires_once_for_guest` and `..._for_signed_in` | 0C-3 |
| A6 | `test_guest_signup_emits_signed_in_with_guest_id_hash_and_no_personal_data` | 0C-4 |
| A7 | internal flag tests plus the saved query filter, shown with the staging test user absent from the one number | 0C-2, 0C-6 |
| A8 | Priya's written sign-off on the 0C PRs | 0C-1 to 0C-9 |
| A9 | `test_signup_stores_valid_invite_cohort`, `test_guest_claim_copies_cohort_to_account_without_one`, `test_signed_in_carries_account_cohort`, `test_session_started_and_landing_viewed_carry_cohort_per_rules`, plus the saved pilot filter on staging | 0C-9, 0C-4, 0C-5, 0C-6 |

### 0.8 Clashes resolved

| # | Iris's text | What the code does at `5fb0f079` | Resolution |
| --- | --- | --- | --- |
| C1 | Events are named, small, trustworthy | PostHog `event` is a generic type (`system`, `storage`); the name is a property; about 30 kinds are sent | Iris wins: 0C-1 |
| C2 | `first_answer_shown` fires for guests and signed-in users | Fires for guests only, and only when the guest message counter is 1 | Iris wins: 0C-3 |
| C3 | Accounts that started as guests carry a hashed guest id | No link; conversion events use the guest id, sign-up uses the account id | Iris wins: `signed_in` carries `guest_id_hash`. Only `signed_in` carries it (it is the account's first event); no stored mapping is added |
| C4 | Guests get a random id that ends with the 7-day reset | The guest `distinct_id` is the hash of the Supabase anonymous user id, which belongs to one guest workspace that expires after 7 days; renewal mints a new id | Consistent; no change |
| C5 | Exactly those properties | The envelope also sends hashed conversation and message ids, status, latency, and nested attributes | Iris wins, with a fixed technical set allowed (0.5). Iris to confirm the technical set on the 0C-1 PR |
| C6 | No click ids; no ad tracking | The web stores and sends `fbclid` plus `utm_*`, `ref`, `starter`, `landing_path` on signup and guest start; the API silently drops all of them | Iris wins: `fbclid` removed (0C-7). The API takes only `invite_cohort` (0C-9); the other fields stay in the browser for the composer prefill and never reach the API or PostHog |
| C7 | A user loses a question only for an answer or a visible failure | The claim is taken before model work and stands if the turn errors | Consistent: an errored turn shows a failure notice. Only replay and 404 were wrong; fixed in 0B-2 |
| C8 | Reset time is midnight UTC shown locally | The chat 429 already sends `Retry-After` = seconds to the next UTC midnight; the web says "wait a moment" | Iris wins: 0B-1 |
| C9 | On staging a test user fires "each event" once | Events 4 to 6 have no trigger until stages 2 and 3 | The staging run covers the seven events with triggers; events 4 to 6 are covered by the registry tests |
| C10 | The code is stored on the account "at sign-up" from the invite link | `landing-intent.ts` keeps only the first attributed visit, so an invite link after an earlier organic visit would be lost | Iris wins: the cohort gets its own capture rule and storage key (0C-9) |
| C11 | `receipt_shared` has no share id | `receipt_created` sends `receipt_digest` (first 16 characters of the payload digest) | Iris wins: digest dropped (0C-8) |

Decisions recorded (formerly open):

- The invite `ref` can be crafted by anyone. Lucas decided (Sep 25 2026):
  no allowlist; the server accepts only the fixed format in 0C-9; the
  cohort is analytics only. Iris's rule makes real codes hard to guess.

Not resolved: none.
