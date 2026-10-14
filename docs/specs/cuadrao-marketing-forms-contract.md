# Cuadrao marketing forms contract

Owns the two public form endpoints of the independent `marketing/` package: Business inquiries ([#881](https://github.com/lagarcess/argus/issues/881)) and Personal early-access signups ([#882](https://github.com/lagarcess/argus/issues/882)). Part of the launch tracked in [#880](https://github.com/lagarcess/argus/issues/880). It does not touch the Argus API, the native app or any financial contract.

## Ownership

| Fact | One owner | Everything else |
| --- | --- | --- |
| Inquiry acceptance and retry | Resend, under an `Idempotency-Key` the page generates per message | The route reports Resend's answer and stores nothing |
| Signup durability | `public.cuadrao_early_access_signups` in the existing Supabase project | The route inserts; the operator tool reads, removes and notifies |
| Inquiry destination | `CUADRAO_INQUIRY_TO` on the service, chosen by the founder, no default | The route reads it; nothing else assumes where inquiries land |
| Public contact address shown to visitors, reply-to of availability notices and removal requests | `businessContactEmail` in `marketing/components/site-copy.ts` | Both pages, the privacy text and the operator tool read it. It may differ from the inquiry destination |
| Address spelling | `normalizeEmail` in `marketing/lib/forms/validation.ts` | The digest, the stored address and the operator tool derive from it |
| Consent version | `SIGNUP_CONSENT_VERSION` in `marketing/lib/forms/config.ts` | Stored on each row |

## Shared rules

- Both endpoints accept `POST` with `Content-Type: application/json`, a body of at most 8 KiB, and return JSON with `Cache-Control: no-store`.
- Validation is on the server. Errors name fields, never echo values.
- A request whose `Origin` header names another host is refused with 403. No CORS headers are sent.
- A hidden `website` field is a honeypot. When filled, the route answers as if it succeeded and sends or stores nothing.
- Limits are in-memory counters in the single service instance. A restart forgets them, and a timer sweeps every counter once per window, so a key is forgotten within two windows even if nobody submits again, and a visitor's address and an inquirer's email are held for at most two hours and never stored in a database. The privacy text says so. They slow scripts down and are not a security boundary. Per client: inquiries 5 per 10 minutes, signups 8 per 10 minutes. The client is the rightmost `X-Forwarded-For` entry, which Render appends and a caller cannot choose; behind a proxy such as Cloudflare, `CUADRAO_TRUSTED_CLIENT_IP_HEADER` names the header it sets (for example `CF-Connecting-IP`). Per address: inquiries 3 per hour. Overall: inquiries 60 per hour, signups 300 per hour. Only requests that passed validation (and are not honeypot hits) spend an overall allowance. Over a limit the answer is 429 with `Retry-After`.
- Provider calls time out after 10 seconds. A timeout, a provider error or missing configuration is 503 `unavailable`. Nothing reports success it did not receive.
- Logs carry an event name and an outcome only. They never carry a name, address, message or digest.

## `POST /api/inquiries`

```json
{ "name": "1 to 120 characters, one line",
  "email": "valid address, at most 254",
  "description": "optional, at most 1000",
  "locale": "es | en",
  "submissionId": "UUID the page generates for this message",
  "website": "" }
```

The route accepts these fields only. The page composes `description` from the visitor's
optional answers and note, so the contract is unchanged: a Spanish block first (role,
preferred channel and a validated WhatsApp number, how they found Cuadrao, pilot interest),
then the visitor's own text of at most 700 characters. The block never exceeds 300
characters, so the total stays within the 1000 limit; `marketing/__tests__/inquiry-summary.test.ts`
checks the worst case. Nothing is stored beyond the email in the inquiry mailbox. The page
asks for no new required field, and the privacy notice and the line under the form say a
WhatsApp number may be shared.

| Status | Body | Meaning |
| --- | --- | --- |
| 202 | `{"status":"accepted"}` | Resend accepted the message for delivery to the configured inquiry mailbox, with the visitor as `Reply-To`. "Accepted" is not "delivered to a mailbox". |
| 400 | `{"error":"invalid","fields":["email"]}` | Validation failed. |
| 403 / 413 / 415 | `{"error":"forbidden"\|"invalid"}` | Wrong origin, body too large, not JSON. |
| 429 | `{"error":"rate_limited"}` | Over a limit. |
| 503 | `{"error":"unavailable"}` | Not configured (including no valid `CUADRAO_INQUIRY_TO`), provider rejected, or timed out. |

**No duplicates.** The page reuses `submissionId` when the visitor retries the same text and makes a new one after any edit. Resend returns the original result for a repeated key for 24 hours, so a double click, or a retry after a lost response, sends one message. A second submit is ignored while a request is in flight; the button stays focusable and is marked `aria-disabled`.

**No storage.** The inquiry is an email in Cuadrao's mailbox. There is no inquiry table to retain, secure or erase beyond the mailbox itself.

**Failure keeps the text.** On any non-202 the form shows the visitor's text unchanged, a retry control and the direct email address.

## `POST /api/signups`

```json
{ "email": "valid address, at most 254", "locale": "es | en", "website": "" }
```

| Status | Body | Meaning |
| --- | --- | --- |
| 200 | `{"status":"registered"}` | The database accepted the request. A new, a repeated and a removed address all get exactly this answer. |
| 400 / 403 / 413 / 415 / 429 | as above | |
| 503 | `{"error":"unavailable"}` | Not configured or the database did not accept it. |

The route sends `INSERT ... ON CONFLICT (email_digest) DO NOTHING` through PostgREST (`Prefer: resolution=ignore-duplicates,return=minimal`) with the service-role key. It never reads the table, so it cannot tell, and cannot reveal, whether an address already existed or was removed.

## Table `public.cuadrao_early_access_signups`

Migration `supabase/migrations/20260920000000_cuadrao_early_access_signups.sql`.

| Column | Meaning |
| --- | --- |
| `email_digest` (pk) | SHA-256 hex of the normalized address. Deduplication and suppression key. |
| `email` | The normalized address while the signup is active. `null` once removed. |
| `language` | `es` or `en`, from the page. |
| `consent_version` | The consent text version the visitor saw. |
| `source` | `personal-page`, `operator-removal`. |
| `created_at`, `notified_at`, `removed_at` | Registration, one availability notice sent, removal. |

Checks make the table refuse inconsistent rows: an address exists exactly while `removed_at` is null, and the digest must equal the SHA-256 of the stored address. RLS is on with no policy, `anon` and `authenticated` hold no privilege, and `service_role` holds select, insert and update but not delete. The migration revokes from `service_role` explicitly because hosted Supabase grants it every privilege on new tables by default. Visitors have no Argus account, so nothing references `auth.users`.

## Removal and suppression

Removal erases the address and keeps the digest with `removed_at`. That row is the suppression record: the page's insert conflicts with it and is ignored, so a removed address is not registered or notified again, and the visitor sees a normal success. A request for an address that never registered still creates a suppression row. Visitors ask for removal at `hola@cuadrao.ai`; the operator runs `bun run scripts/signups.ts remove <email>`.

## Availability notice

The page promises one message when access is available. The operator sends it with `scripts/signups.ts notice`:

- It reads only rows with `removed_at is null and notified_at is null`.
- A template must carry a Spanish and an English subject and text, and every text must name `hola@cuadrao.ai` so the reader can opt out.
- The default is a dry run that prints counts. A full send needs `--send` and `--expect <count>` equal to the recipients selected.
- `--only a@x,b@y` sends to named approved test addresses, never stamps `notified_at`, and uses a different idempotency key from the real send.
- **Claim, then send.** Each row is claimed before its message goes out: `notified_at` is set by a conditional update that succeeds only while the row is still active and not yet notified. A removal or an earlier notice is therefore respected at the moment of sending, not at the moment the list was read. If the database refuses the claim, nothing is sent and the run stops, so nobody is ever mailed without a record.
- **Outcomes.** A 2xx answer is sent. A plain client-side refusal (4xx other than 409) proves nothing was sent, so the claim is released and a rerun can try again. A lost response is retried once under the same idempotency key `notice-<template id>-<digest>`, which Resend answers without sending twice. A 409 (a request with that key is still in flight), a 5xx, or no answer after the retry may have been processed, so the row stays claimed and its `email_digest` is printed, the run stops there so an outage cannot claim every remaining row, and it exits non-zero. A refusal whose claim cannot be released is printed separately (`releaseFailed`): nothing was sent and the row stays claimed. Check `notified_at` first: if it is empty the release did save and a rerun will send it, so do not send by hand; if it is set, clear it to retry, or send by hand and leave it set. A test send (`--only`) that stops on an unknown outcome claims nothing, so a rerun mails every test address again; within 24 hours Resend replays the same `notice-test-` key and does not send a second copy.
- **Lost attempts never prove a refusal.** If any send attempt got no answer, a later 4xx (including 422 and 429) does not release the claim: the first attempt may have been processed. A claim whose own answer is lost is named separately (`claimUncertain`), because that row may be claimed and never mailed; the operator checks `notified_at` for each printed digest. If it is empty, the claim did not save: do not send by hand, a rerun will send it. If it is set, the row is claimed and may be unsent: check Resend by the idempotency key first, because a second notice run may already have mailed it, then send it by hand if it was not; a rerun will skip it. Run only one notice at a time. Test sends (`--only`) claim nothing and report `notice-test-` keys.
- **Never rerun blindly.** A rerun skips every claimed row, so it cannot mail anyone twice, even after Resend's 24-hour key window. For each printed digest the operator checks Resend by the key, and only then decides whether to send that person by hand. The tool never clears a claim it could not prove unsent.

**Two earlier limits, kept on record.** The first review rounds found that a notice run read its list once and stamped a row only after sending. That allowed (a) an address removed by hand during a run to be mailed once in that run, and (b) a send that timed out after Resend accepted it to be left unstamped and mailed again by a rerun after 24 hours. The migration's own header comment still says `notified_at` is stamped after the notice is sent; the migration is not edited, and since claim-then-send the column means "claimed for sending". Claim-then-send closes both: (a) is checked per row at claim time, and (b) leaves the row claimed and named rather than retryable. One window remains: a removal that lands in the milliseconds between a row's claim and its send still sends that one message. Handle removal requests before a run, not during it.

Early-access consent covers this availability notice only. It is not marketing consent and does not feed `news.cuadrao.ai` ([#892](https://github.com/lagarcess/argus/issues/892)).

## Confirmation email

None at launch. Durable signup does not depend on a second message. The cost is that anyone can type another person's address. The exposure is bounded: the only message the address receives is the single availability notice, which tells the reader how to leave, and removal is permanent. A double opt-in confirmation can be added later without changing this contract.

## Configuration

| Variable | Used by | Secret |
| --- | --- | --- |
| `RESEND_API_KEY` | Inquiries, notice tool | Yes |
| `CUADRAO_INQUIRY_FROM` | Inquiries sender, for example `Cuadrao <website@notify.cuadrao.ai>` | No |
| `CUADRAO_INQUIRY_TO` | The one mailbox that receives inquiries. A single bare address; a list, a display name or a line break reads as unset. No default, so an unset value means the form is unavailable rather than delivering to an address nobody confirmed | No |
| `SUPABASE_URL` | Signups, operator tool | No |
| `SUPABASE_SERVICE_ROLE_KEY` | Signups, operator tool | Yes |
| `CUADRAO_SITE_INDEXING` | `public` on the approved public host only | No |
| `CUADRAO_SOCIAL_PREVIEW` | `1` shows the planned social icons as placeholders in the footer. Leave unset in production; an icon appears once its account link is set in `marketing/lib/social.ts`. Read when the pages are built | No |
| `CUADRAO_TRUSTED_CLIENT_IP_HEADER` | Only if a trusted proxy sits in front, for example `CF-Connecting-IP`; unset on the Render address | No |
| `RESEND_API_URL` | Defaults to `https://api.resend.com`; tests point it at a mock | No |
| `CUADRAO_NOTICE_FROM` | Operator notice tool only, never set on Render | No |

Without the provider variables the pages still render and each form shows its truthful unavailable state.

## Privacy mapping

The page [privacy text](../../marketing/components/privacy-copy.ts) describes exactly this contract: what is received, the processors (Render, Resend, Supabase in the United States, Cloudflare for the domain), retention, and removal. A browser test asserts the site sets no cookies and writes nothing to local or session storage, which is what the text claims.
