# Apple Shortcuts connector evidence (wave 1C)

**Date:** October 1, 2026. **Branch:** `claude/ingestion-shortcuts`.
**Lane spec:** [financial-ingestion-connectors](../../../specs/lanes/financial-ingestion-connectors.md).
**API:** [Apple Shortcuts connector routes](../../../API_CONTRACT.md#apple-shortcuts-connector-default-off).
**Experience:** MVEE [§4.6](../../../specs/argus-minimum-viable-ecosystem-experience.md#46-apple-pay--google-pay-and-device-assisted-capture).

The connector observes only. A shortcut on the person's iPhone posts one event
per run; the server turns it into `ImportCandidate` evidence for the hub's
`CandidateSink` and never creates accounts or activity. Code:
`src/argus/domain/ingestion/shortcuts/` (`tokens`, `store`, `amounts`,
`events`, `connector`), routes in `src/argus/api/routers/ingestion_shortcuts.py`,
wiring in `src/argus/api/shortcuts.py`, table in
`supabase/migrations/20261002120200_financial_shortcut_device_tokens.sql`.
No native iOS code changed; native adoption (an App Intent with a
Keychain-held token) is for the iPhone delivery owner.

Related documents: [capabilities](capabilities.md) (what iOS provides, with
sources and confidence), [setup guide](setup.md) (Spanish first, English
parity), [device test protocol](device-test-protocol.md).

## What works, and how far it is proven

| Claim | Level | Evidence |
| --- | --- | --- |
| Enrollment returns a 256-bit device token once; only its SHA-256 digest is stored; it is never listed or logged | Hermetic API + real Postgres | `test_enrollment_returns_token_once_and_stores_only_a_digest`, `test_tokens_never_reach_logs`, `test_clients_have_no_access_and_digests_follow_their_connection` |
| Intake accepts only the device token; missing, malformed, forged, user-session and disconnected tokens get the same 401 | Hermetic API | `test_unknown_tokens_are_refused_identically` (6 cases), `test_disconnect_revokes_the_device_token` |
| Flag off: enrollment and intake answer 404 even with a token | Hermetic API | `test_flag_off_answers_absent_even_with_a_device_token` |
| Disconnect deletes the digest (`provider_revocation: revoked`), removes unreviewed drafts, and the token is refused | Hermetic API + real Postgres | `test_disconnect_revokes_the_device_token`, `test_enroll_intake_and_disconnect_on_real_postgres` |
| No client role can read or write digests (RLS, no policies, grants revoked); digests cascade with their connection | Real Postgres | `test_clients_have_no_access_and_digests_follow_their_connection` |
| A tap becomes `transaction` evidence, `status=unknown`, `direction=unknown`, card name as account hint, no invented mask | Hermetic | `test_wallet_tap_is_unsettled_transaction_evidence`, `test_mask_only_when_the_shortcut_states_it` |
| Re-delivery returns the same receipt with `unchanged`; distinct event ids with identical content stay distinct | Hermetic API + real Postgres | `test_repeated_delivery_returns_the_same_receipt`, `test_identical_purchases_with_distinct_event_ids_stay_distinct`, `test_pending_batch_is_idempotent_per_event` |
| Formatted amounts read deterministically or left unresolved: `RD$1,250.00`, `US$ 12.50`, `1.250,00 €` parse; bare `$` keeps currency empty and uncertain unless an ISO code is sent; `1,250` stays unresolved | Hermetic | `test_shortcuts_amounts.py` (41 tests), `test_ambiguous_dollar_and_explicit_code` |
| Message captures are `unclassified` inert text with every money field unresolved | Hermetic | `test_message_capture_is_inert_text_with_money_unresolved`, `test_message_capture_is_accepted_as_inert_text` |
| No sink: 503 `shortcuts_intake_unavailable`, retryable, nothing saved, freshness unchanged | Hermetic API | `test_without_a_sink_nothing_is_saved_and_the_answer_is_retryable` |
| A sink failure mid-batch answers 503 without claiming nothing was saved; the retry records only what is missing | Hermetic API | `test_partial_batch_failure_is_retryable_and_never_claims_nothing_saved` |
| Body caps, strict schema (unknown fields refused), time window, batch limits | Hermetic API | `test_body_cap_extra_fields_and_bad_json`, `test_events_outside_the_time_window_are_refused`, `test_batch_limits_refuse_before_saving`, `test_stale_capture_in_a_batch_does_not_block_the_rest` |
| Per-device rate limit (20/min, 300/day), other devices unaffected | Hermetic API | `test_per_device_rate_limit` |
| Leaked-token bounds: 500 events/device/day across batches; 30 failed tokens per address per 10 min, checked before authentication; one limiter per window (all process-local) | Hermetic API | `test_daily_event_budget_bounds_batches`, `test_failed_tokens_are_limited_per_address_before_authentication`, `test_each_request_window_has_its_own_limiter` |
| A bad amount never fails a request: more than 18 digits stays unresolved; a contract refusal rejects only that event | Hermetic | `test_more_than_eighteen_digits_stays_unresolved`, `test_huge_amount_is_saved_unresolved_never_a_server_error`, `test_contract_refusal_rejects_only_that_event` |
| A capture the sink does not hold is never reported saved (`not_saved` or 503); a device disconnected mid-flight gets 401 | Hermetic API | `test_evidence_the_sink_ignores_is_never_reported_saved`, `test_connection_ended_mid_flight_answers_unauthorized` |
| Explicit currency settles only a bare `$` or no marker; a sign adds direction doubt; blank strings are missing | Hermetic | `test_explicit_code_never_settles_another_marker`, `test_a_sign_is_doubt_about_direction_not_a_direction`, `test_empty_optional_strings_are_missing` |
| Freshness moves only when an event was held | Hermetic API | `test_freshness_moves_only_when_an_event_was_accepted` |
| Five-device limit holds under concurrent enrollment (fails without the advisory lock) | Hermetic + real Postgres | `test_concurrent_enrollment_cannot_exceed_the_device_limit`, `test_concurrent_enrollment_holds_the_device_limit` |
| Wallet trigger fires and passes Amount/Merchant/Card; runs immediately; locked behavior; offline behavior; DR card formats; Message and iOS 27 notification triggers | **Not verified.** Secondary sources only | [capabilities.md](capabilities.md); [device-test-protocol.md](device-test-protocol.md) |

**No physical-device verification was performed.** The shortcut recipes in the
setup guide are written from secondary sources and have never been run.

## Commands and results

```bash
PY=/root/.cache/pypoetry/virtualenvs/argus-mew2D91N-py3.11/bin/python
# Hermetic
$PY -m pytest tests/ingestion/test_shortcuts_*.py -q --no-cov
# 96 passed (amounts 41, events 21, api 24, intake 10)

# Real Postgres (wave-0 and Shortcuts migrations)
ARGUS_DISPOSABLE_DATABASE_URL=postgresql://postgres@127.0.0.1:56811/argus_shortcuts \
  $PY -m pytest tests/test_ingestion_shortcuts_postgres.py \
  tests/test_ingestion_connections_postgres.py -q --no-cov
# 15 passed (shortcuts 3, connections 12)

# Lane gate
$PY -m pytest tests/ingestion tests/financial_accounts tests/household \
  tests/test_openapi_compatibility.py tests/test_phase6_api_structure.py \
  tests/test_environment_scripts.py tests/test_private_alpha_release_profile.py \
  tests/test_interpreter_prompt_freeze.py -q --no-cov
```

## Design decisions

- **Token:** `sct1.<device id>.<secret>`; the device id is the connection's
  `external_ref`, so lookup is one indexed read, followed by a constant-time
  digest comparison (also performed for unknown devices). Not sealed with the
  `SecretBox`: nothing ever needs the token back. No new environment variable.
- **Identity:** `external_id` is `wallet|message|notification` + `:e:` + hash
  of the shortcut's `event_id`. Without an `event_id` it is `:d:` + hash of the
  normalized content and the capture second: an exact replay is harmless, but
  two identical purchases captured in the same second would collapse and a
  retried run whose capture time moved would duplicate. The recipe always
  sends an `event_id`.
- **Dates:** Wallet gives no transaction time. `occurred_on` is the capture day
  in the phone's own zone; `occurred_at` stays empty; `observed_at` is the
  capture time.
- **Direction stays unknown:** the trigger reportedly also fires for declined
  taps and does not distinguish refunds. If device testing shows only settled
  purchases fire, `outflow` could be adopted by an explicit decision.
- **Offline:** Shortcuts has no retry. The optional fallback writes each event
  to `pending.txt` before sending and removes it after a receipt; a manual
  batch shortcut re-sends the file in batches of 25 lines (up to 8 per run),
  keeping the file whenever a receipt says `not_saved` (idempotent). Without
  it, any capture made without network, or while the server answers 503, is
  lost.
- **Receipts:** only `recorded`/`unchanged` mean held. The single-event route
  answers an error for anything else so a recipe checking `receipt_id` cannot
  mistake it for saved; a batch lists `out_of_window`, `rejected` or
  `not_saved` per event. When the sink holds nothing for an event (contract
  `SubmitResult.ignored`), a disconnected device gets 401 and a live one
  `not_saved`.
- **Limits** are process-local `SlidingWindowLimiter`s (one per window) and a
  small weighted counter for event budgets and failed-token addresses
  (`src/argus/api/shortcuts_limits.py`). With several API processes the
  effective limits multiply by the process count.
- **Device limit:** the count of live device digests and the new digest's
  insert run in one transaction under a per-person advisory lock; a loser's
  just-created connection is disconnected.
- **Freshness:** a successful intake sets the connection's `last_success_at`
  through the shared lease and compare-and-set, so the connections list shows
  the last capture.

## Unsupported or unknown

- Online and in-app Apple Pay, cards whose issuers never fire the trigger, and
  trigger timeouts: missed by design of iOS, not recoverable here.
- Reading amounts from SMS or notification text (needs an approved extraction
  path; no regex or keyword rules).
- Token rotation without re-enrollment (disconnect and enroll again instead).
- Native presentation of enrollment and review.

## Contract follow-up (adopted)

The amended wave-0 contract (`claude/ingestion-contract` @ `3bed4ac1`, now
merged at `bc0ce60c` with `SubmitResult.ignored`) added
`unclassified` to `EvidenceKind` at this connector's request. Message and
notification captures are emitted as `evidence="unclassified"`; `unresolved()`
always lists `kind` and every money field. The amended contract also counts a
card or account name alone as resolving `account`, so a tap with a card name
leaves only `direction` (and any uncertain amount or currency) for review.
Tap direction stays `unknown`; whether a Wallet tap may be taken as an
outflow is an open founder question.
