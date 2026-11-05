# Gmail connector evidence (wave 1B)

**Date:** October 1, 2026. **Branch:** `claude/ingestion-gmail`.
**Lane spec:** [financial-ingestion-connectors](../../../specs/lanes/financial-ingestion-connectors.md).
**API:** [Gmail connector routes](../../../API_CONTRACT.md#gmail-connector-default-off).
**Data:** [Gmail sender allowlist](../../../DATA_MODEL.md#gmail-sender-allowlist).

## Read this first (founder decision)

**(a) Verified against a mocked Google only.** OAuth (consent URL, code
exchange, scopes, refresh, revocation) and Gmail API behavior (profile, search,
messages, attachments, history) were proven only against an in-process fake
(`tests/ingestion/gmail_fakes.py`) with synthetic, clearly labeled mailboxes
(`tests/ingestion/gmail_mailbox.py`: fictional banks on `.test` domains, no real
people or email content). No Google Cloud OAuth client or test inbox exists
yet, so no request in this lane reached Google. Real Google behavior, quotas
and consent screens are unverified.

**(b) Gmail is NOT end-to-end automatic import.** Financial extraction (amount,
currency, date, account) is missing in this wave. Every relevant email becomes
an `unclassified` draft that the person must classify and fill in during
review. Reading those fields from email content needs a separately authorized,
measured step (a paid model and a committed scorecard, AGENTS.md
Never-Violate 12).

**(c) Nothing reaches review from this branch alone.** Candidates go to the
hub's `CandidateSink`, which reconciliation (#772) provides. On this branch the
sink is absent, so sync answers `no_sink` and fetches nothing; drafts appear
only once reconciliation is wired.

The connector observes only. It turns allowlisted, sender-authenticated Gmail
messages into `ImportCandidate` drafts handed to the hub's `CandidateSink`; it
never creates accounts or activity. Code: `src/argus/domain/ingestion/gmail/`
(config, client, state, oauth, senders, senders_postgres, mime, html_text,
attachments, authenticity, extract, messages, failures, sync, suggestions,
adapter, connector), routes in
`src/argus/api/routers/financial_connections_gmail.py`, wiring in
`src/argus/api/gmail.py`, table in
`supabase/migrations/20261002120100_financial_source_gmail_senders.sql`.
Forwarding mail to Cuadrao is not offered as a substitute for this connection.

## Scope and why

Exactly one scope: `https://www.googleapis.com/auth/gmail.readonly`.

- It is the narrowest Gmail scope that can read message bodies and
  attachments, which bank alerts and statement notices need. Google classifies
  it as **restricted** ([Gmail API scopes][gmail-scopes], [restricted
  scopes][restricted]).
- `gmail.metadata` cannot read bodies or attachments and is restricted too
  ([Gmail API scopes][gmail-scopes]), so it would not reduce the verification
  burden. (Its inability to use the `q` search parameter is from memory of the
  Gmail reference and was not re-verified here.)
- No `openid` or `email`: `users.getProfile` returns the mailbox address under
  `gmail.readonly`, so no identity scope is requested.
- `access_type=offline` and `prompt=consent` obtain a refresh token on every
  authorization; `include_granted_scopes=true` makes an earlier
  `gmail.readonly` grant visible in the token response, so a token response
  without it means the person unticked it under granular consent, which Google
  expects apps to check ([granular permissions][granular]).

## What the founder must create

1. A Google Cloud project for Cuadrao (separate from any personal project).
2. Enable the Gmail API in that project.
3. Google Auth Platform / OAuth consent screen: user type **External**, app
   name "Cuadrao", support email, app logo optional, app domain and links to
   the privacy policy and terms (see Privacy below), authorized domain of the
   web app, developer contact. Add the scope `.../auth/gmail.readonly` under
   Data Access. Keep publishing status **Testing** and add each test user's
   Google account under Audience.
4. Credentials: an OAuth client of type **Web application**. Authorized
   redirect URI = the web app page that receives `code` and `state` (for
   example `https://<app-domain>/settings/connections/gmail`; an
   `http://localhost` URI is allowed for local development). That page posts
   both to `POST /api/v1/financial-connections/gmail/callback` with the
   person's session. The web page itself is not part of this lane.
5. A dedicated test inbox (a Gmail account created for testing, receiving
   only mail the founder authorizes for this purpose), added as a test user.
6. Store `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and
   `GOOGLE_OAUTH_REDIRECT_URI` as server-side environment variables of the API
   service only (Render dashboard; `render.yaml` declares them `sync: false`,
   nothing is committed), with `ARGUS_INGESTION_SECRET_KEY` already set. Never
   put the client secret in the web app, a `NEXT_PUBLIC_*` variable, a
   transcript or a ticket. Enabling also needs `ARGUS_INGESTION_ENABLED=true`
   and `ARGUS_FINANCIAL_ACCOUNTS_ENABLED=true`, both still default-off.
7. Before any external user: Google verification of the restricted scope and
   the security assessment (below), and the privacy statements.

## Testing-mode limits (sourced)

| Limit | Source | How it was checked |
| --- | --- | --- |
| A project in **Testing** status is limited to 100 test users listed on the consent screen | [Manage App Audience][audience]; [Unverified apps][unverified] | WebSearch result summaries of Google Cloud Help; direct fetch of `support.google.com` was blocked by this environment's egress proxy |
| Refresh tokens issued to an External app in **Testing** expire after 7 days unless only name/email/profile scopes are requested | [Using OAuth 2.0 to Access Google APIs][oauth2] | WebSearch summary; `developers.google.com` fetch blocked here |
| Unverified apps requesting restricted scopes show the unverified-app screen and are capped at 100 new users over the project's lifetime | [Unverified apps][unverified] | WebSearch summary |

Consequence for testing: a test connection will hit `invalid_grant` about a
week after each authorization. The connector records `needs_reauth` with
`gmail_token_revoked`, keeps `last_success_at` and the cursor, and the person
re-runs authorize; the callback replaces the credential on the same connection.

## Restricted-scope verification and security assessment (sourced)

- Apps that request restricted scopes must pass a security assessment that
  verifies they handle data securely and delete user data on request; Google
  uses the App Defense Alliance **CASA** framework, and the assessor issues a
  Letter of Validation ([Security Assessment][casa]).
- The assessment is repeated every 12 months from the previous Letter of
  Validation date ([Annual Recertification][recert]).
- Google's API Services User Data Policy, including its **Limited Use**
  requirements, applies to data from these scopes ([User Data Policy][policy]).
- Not verified here: assessor cost and timeline (only third-party blog
  figures were found, not Google sources), and the exact CASA tier Google will
  assign; Google assigns it during review.

Until verification passes, Gmail stays limited to manually added test users.

## Privacy statements needed before external users

- A privacy policy section stating which Gmail data is accessed (messages from
  senders the person chooses, their headers, visible text and allowed
  attachments), why (proposing reviewed financial drafts), what is kept
  (below), that nothing is shared with a household or third party by
  connecting, and how to disconnect and delete.
- The Limited Use affirmative disclosure Google requires, for example: "Use
  of information received from Google APIs will adhere to the Google API
  Services User Data Policy, including the Limited Use requirements."
- In-app disclosure before consent: only chosen senders are read; drafts need
  review; sender suggestions read headers of recent mail on request.

## Data retention for email content

| Data | Kept? |
| --- | --- |
| Refresh token | Sealed (AES-256-GCM, bound to `gmail:<connection id>`) in `financial_source_connections`; deleted on disconnect |
| Access token | Memory only, minted per sync or suggestion request, never stored or logged |
| Mailbox address | Not stored: a keyed, purpose-separated digest (`SecretBox.digest`, `external_ref`) and a masked label only |
| Sender allowlist | `financial_source_gmail_senders`; deleted on disconnect |
| Message body, HTML, headers | Not stored; parsed in memory during a sync |
| Excerpt | Subject and visible text, inert and capped at 280 characters, inside the candidate (reconciliation decides its retention) |
| Attachments | Bytes fetched only for allowed types under 10 MiB, hashed and dropped; the candidate keeps `<message id>:<part id>`, media type, size, SHA-256 and inert file name |
| Sender suggestions | Computed per request from headers, never stored or logged |

Reading statement files (PDF/CSV) belongs to a document-import path that does
not exist yet; this wave hands off only the attachment reference.

## Content extraction is a separate, authorized step

No model and no keyword or regex rule reads what an email says. The shipped
`UnreviewedEmailExtractor` asserts only the sender domain; amount, currency,
dates, direction and account stay unresolved for review. A content extractor
plugs in through the `EmailExtractor` protocol (`extract.py`) and needs founder
authorization: a paid model and a committed scorecard (AGENTS.md
Never-Violate 12).

## Verification levels

| Claim | Level | Evidence |
| --- | --- | --- |
| Consent URL: `gmail.readonly` only, offline, `prompt=consent`, incremental, PKCE S256 | Mocked provider | `test_authorize_url_asks_only_for_gmail_readonly_with_pkce_and_offline_access` |
| State bound to the person, single-use, expiring, tamper-proof; PKCE verifier checked by the token endpoint | Mocked provider | `test_state_is_*`, `test_forged_or_altered_state_is_refused` (4), `test_a_code_issued_for_another_pkce_challenge_is_refused_by_google`, RFC 7636 vector |
| Partial consent refused and released; missing refresh token stores nothing | Mocked provider | `test_partial_consent_*`, `test_missing_refresh_token_*`, API 422 |
| Connection: digest ref, masked label, sealed refresh token; time-limited grant flagged for attention | Mocked provider | `test_callback_creates_a_connection_*`, `test_time_limited_grant_is_flagged_*` |
| Reconnect updates the same connection; insert race resolves; other person's mailbox refused | Mocked provider; Postgres | `test_reconnect_*`, `test_concurrent_callback_race_*`, `test_mailbox_connected_by_someone_else_*`, `tests/test_ingestion_gmail_postgres.py` |
| Allowlist only; query built from it; strict local match (lookalike domain rejected) | Mocked provider | `test_initial_sync_imports_allowlisted_authenticated_messages_only`, `test_matching_*`, `test_senders_that_could_inject_query_operators_are_refused` (12) |
| Forged `From` skipped using Gmail's topmost `Authentication-Results` | Mocked provider (synthetic headers) | `test_gmail_authentication_results_decide_sender_authenticity`, spoofed fixture |
| MIME limits, charset handling, HTML to inert text, nothing fetched | Mocked provider | `test_hostile_html_*`, `test_hidden_markup_is_dropped` (9), `test_part_tree_is_bounded`, `fake.unexpected == []` |
| Attachment media types, size cap (30 MiB part never downloaded), signatures | Mocked provider | `test_attachment_policy_*`, `test_candidates_claim_only_machine_certain_facts` |
| Pagination (search and history), bounded with resume | Mocked provider | `test_scan_paginates_and_reports_truncation`, `test_history_pagination_is_bounded_and_resumes` |
| Incremental history, spam rescue, duplicates are one observation | Mocked provider | `test_incremental_*`, `test_message_rescued_from_spam_*`, `test_same_message_from_scan_and_history_*`, `test_a_retried_sync_*` |
| Concurrent syncs advance the cursor once; stale lease cannot advance | Mocked provider; Postgres | `test_concurrent_syncs_*` (memory and Postgres), `test_a_sync_that_outlives_its_lease_*` |
| History 404 recovery, window bounded | Mocked provider | `test_history_too_old_*`, `test_recovery_window_never_exceeds_the_lookback` |
| Revoked grant, 401, 403 scope, 403 other: `needs_reauth`, freshness kept | Mocked provider; Postgres | `test_revoked_refresh_token_*`, `test_refused_access_needs_reauth` (3) |
| 429/5xx bounded backoff then `gmail_unavailable`, cursor kept | Mocked provider | `test_outages_*` (3), `test_a_transient_outage_*` |
| A message or attachment Gmail refuses on its own (oversized, malformed, per-item 4xx) is a counted skip and the cursor moves past it; auth, 429 and 5xx still fail the sync | Mocked provider | `test_one_bad_message_is_skipped_*` (3), `test_malformed_metadata_*`, `test_a_refused_attachment_*`, `test_auth_refusals_on_a_message_*` |
| OAuth state ledger is capped per person and never locks out others | Hermetic unit; mocked provider for the 429 | `test_state_ledger_*` (2), `test_a_person_over_the_state_limit_gets_429` |
| A failure after the code exchange (profile 403/5xx, database) revokes the new grant; owned-elsewhere never revokes | Mocked provider | `test_profile_failure_after_the_exchange_*` (2), `test_database_failure_*` |
| Two people completing the callback concurrently cannot both hold the mailbox | Mocked provider; Postgres (global live-reference index) | `test_two_people_completing_the_callback_concurrently_*`, `test_two_people_cannot_both_hold_a_live_mailbox` |
| `From` with parse defects or parser disagreement has no sender; hidden HTML regions end only at their own tag | Hermetic unit | `test_from_header_parsing_*`, `test_hidden_markup_is_dropped` (9), `test_an_unclosed_hidden_element_*` |
| Disconnect revokes; failure still deletes credential; `forget` deletes the allowlist; a cleanup-only adapter does both while the OAuth client is unconfigured, and still forgets the allowlist without the sealing key | Mocked provider | `test_connect_choose_senders_sync_and_disconnect`, `test_failed_revocation_still_deletes_credential`, `test_forget_runs_even_when_google_revocation_fails`, `test_unconfigured_oauth_still_registers_a_revoke_only_adapter`, `test_without_a_sealing_key_disconnect_still_forgets_senders` | Mocked provider; Postgres | `test_connect_choose_senders_sync_and_disconnect`, `test_failed_revocation_still_deletes_credential` |
| Flag/config off is 404; other person's connection is 404; no token in responses or logs | Mocked provider | `test_flag_off_*`, `test_missing_configuration_*` (4), `test_another_persons_connection_looks_absent`, loguru capture in the round-trip test |
| Allowlist table RLS, owner-only writes through a live connection | Real Postgres 16 (Supabase shim) | `test_clients_read_their_own_senders_and_never_write`, `test_senders_attach_only_*` |
| Real Google OAuth, consent screen, Gmail API behavior and quotas | **Not verified** | Needs the founder's OAuth client and test inbox |

## Commands and results

```bash
# Hermetic (no network)
python -m pytest tests/ingestion/test_gmail_*.py -q --no-cov
# 117 passed (oauth 17, parsing 38, sync 12, sync failures 13, api 20,
#             hardening 17)

# Real Postgres (wave-0 and Gmail senders migrations)
ARGUS_DISPOSABLE_DATABASE_URL=postgresql://postgres@127.0.0.1:56811/argus_gmail \
  python -m pytest tests/test_ingestion_gmail_postgres.py \
  tests/test_ingestion_connections_postgres.py -q --no-cov
# 17 passed (gmail 5, connections 12)
```

## Unsupported or unknown

- Forged `Authentication-Results` on messages Gmail did not deliver: mail
  placed in the mailbox by IMAP `APPEND`, Gmail import or migration tools
  carries whatever headers its author wrote, including a topmost
  `mx.google.com` "pass". Sender authentication cannot tell those apart from
  delivered mail, so such a message from an allowlisted sender becomes a draft.
- Gmail push (`users.watch` with Pub/Sub) needs a hosted Pub/Sub topic;
  syncs are manual (`POST .../gmail/{id}/sync`) or a future scheduler.
- Messages whose sender domain Gmail did not authenticate (no DMARC pass and
  no aligned DKIM pass) are skipped and counted as `unverified_sender`. A bank
  without DKIM would be invisible; whether Dominican banks sign their alerts
  is unknown until real mail is seen.
- Attachments declared as `application/octet-stream` (even real PDFs) are not
  fetched; only declared PDF, CSV, PNG, JPEG, GIF and WebP are.
- A search reads at most 500 matching messages (5 pages of 100, newest first)
  and reports `scan_truncated`; older matches in that window are not read. A
  history sync reads at most 500 history records and resumes next time.
- Deleting or archiving an email does not withdraw its evidence (the fact did
  not change).
- The OAuth state replay ledger is per process; behind several API instances
  replay protection rests on Google's single-use code and PKCE (see
  `state.py`). It holds at most 20 unexpired redeemed states per person and
  answers 429 to that person only.
- A reconnect that fails after Google issued the new grant revokes it, and
  Google revokes the whole grant, so that mailbox's existing connection then
  needs authorization again. A grant without a refresh token is not revoked
  (it may back the person's live connection).
- Google Workspace accounts whose admin blocks third-party Gmail access fail
  with `gmail_access_denied`; not exercised against Google.
- In memory persistence mode the sender allowlist is in memory too.

## Wave-0 changes adopted

The amended contract (`claude/ingestion-contract` at `3bed4ac1`) took the
three changes this lane proposed, and Gmail now uses them:

1. `evidence="unclassified"`: every Gmail candidate says "a person must say
   what this is"; `unresolved()` then demands `kind` and every money field.
   The earlier `transaction` plus uncertain-`kind` workaround is gone.
2. `SecretBox.digest(address, purpose="gmail_mailbox")` makes the mailbox
   `external_ref`; Gmail no longer reads `ARGUS_INGESTION_SECRET_KEY` itself.
3. The adapter's `forget(connection)` hook deletes the sender allowlist after
   the local disconnect; `revoke` only talks to Google.

It also uses `flag_attention`: a grant Google marks time-limited
(`refresh_token_expires_in`) sets `attention_code=gmail_access_time_limited`
without blocking syncs; re-authorizing clears it. Google documents that field
for time-based access grants; whether Testing-mode grants (7-day refresh
tokens) report it was not verified, so the 7-day expiry may still surface only
as `needs_reauth` with `gmail_token_revoked`.

[gmail-scopes]: https://developers.google.com/workspace/gmail/api/auth/scopes
[restricted]: https://support.google.com/cloud/answer/13464325?hl=en
[granular]: https://developers.google.com/identity/protocols/oauth2/resources/granular-permissions
[audience]: https://support.google.com/cloud/answer/15549945?hl=en
[unverified]: https://support.google.com/cloud/answer/7454865?hl=en
[oauth2]: https://developers.google.com/identity/protocols/oauth2
[casa]: https://support.google.com/cloud/answer/13465431?hl=en
[recert]: https://support.google.com/cloud/answer/13463816?hl=en
[policy]: https://developers.google.com/terms/api-services-user-data-policy
