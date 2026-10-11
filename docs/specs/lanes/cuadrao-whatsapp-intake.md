# Cuadrao WhatsApp receipt intake: activation packet

**Status:** built locally on `claude/business-pilot-whatsapp`, default-off, not
pushed. Parent scope: `docs/specs/lanes/cuadrao-business-owner-pilot.md`
("WhatsApp receipt intake"). The destination owner is pending the Business
boundary decision (`cuadrao-business-boundary-proposal.md`, not approved).

## What it does

A linked owner sends a receipt photo (JPEG, PNG) or PDF to the Cuadrao WhatsApp
number. Cuadrao saves it as a document draft with `consent: false` and replies
with a signed-in review link, `/biz?receipt=<id>`. Correction, "Prepare with
AI" and approval happen only on the web. WhatsApp never queues AI preparation.

**October 10, 2026:** the [Business agent execution spec](cuadrao-business-agent-execution-spec.md)
connects WhatsApp to the Business agent (PR W1). The rule "WhatsApp never
queues AI preparation" stays true until W1 lands. Approval stays on the web.

Linking needs proof of possession. The signed-in owner creates a one-time code
on the web, then sends `CUADRAO <code>` from their own WhatsApp. A typed phone
number proves nothing. Unknown senders get no capture and a "connect from the
web app" reply. A new message carrying a receipt already in the owner's inbox
gets a "duplicate" reply instead of "captured". Each reply uses one language:
the one the web app was in when the owner asked for the link code (Spanish
by default).
The founder approved the reply copy on October 8, 2026. Contract: `docs/API_CONTRACT.md`.

## Proof levels

| Level | What it proves | How |
| --- | --- | --- |
| Fixture proof (done) | Signature gate, parsing, linking, replay, isolation, media limits, no AI queueing, privacy-safe logs | Synthetic Meta payloads in `tests/fixtures/whatsapp/`, a scripted Graph API and a recording reply transport. No network. Same cases on real Postgres. |
| Real delivery proof (not done) | Meta reaches the callback, the signature and media download work against Meta, and a reply arrives on a phone. Fixture proof cannot show this. | The founder steps below with one synthetic receipt and an approved test sender. |

## Founder setup in Meta (one time)

1. In the Meta App Dashboard, create an app with the WhatsApp use case. Meta
   creates a test WhatsApp Business account and a test business number.
2. In WhatsApp > API Setup, note the **Phone number ID** and the test number.
   Generate an access token. Under the "To" field, choose "Manage phone number
   list" and add your personal WhatsApp as a test recipient. Confirm the code
   Meta sends to that phone.
3. In App settings > Basic, copy the **App secret**.
4. Choose a verify token: any long random string you keep private.
5. In WhatsApp > Configuration > Webhook, set the callback URL to
   `https://<tunnel host>/api/v1/webhooks/whatsapp` and the verify token from
   step 4, then Verify and save. Subscribe to the webhook field `messages` only.

Proof: step 5 shows "Verified" only if our GET handler answered the challenge.

## Environment (API process only, never the web app)

| Variable | Value |
| --- | --- |
| `ARGUS_WHATSAPP_INTAKE_ENABLED` | `true` |
| `ARGUS_WHATSAPP_VERIFY_TOKEN` | step 4 |
| `ARGUS_WHATSAPP_APP_SECRET` | step 3 |
| `ARGUS_WHATSAPP_ACCESS_TOKEN` | step 2 token |
| `ARGUS_WHATSAPP_PHONE_NUMBER_ID` | step 2 Phone number ID |
| `ARGUS_WHATSAPP_DISPLAY_PHONE_NUMBER` | the test number, for the `wa.me` link |
| `ARGUS_WHATSAPP_SENDER_KEY` | a new random secret; rotating it unlinks every sender |
| `ARGUS_WHATSAPP_GRAPH_API_VERSION` | optional, default `v23.0` |
| `ARGUS_WHATSAPP_OUTBOUND_ENABLED` | `false` for the first run, then `true` for the reply check |
| `ARGUS_APP_ORIGIN` | the web origin used in the review link |

The surface also needs `ARGUS_FINANCIAL_ACCOUNTS_ENABLED`,
`ARGUS_INGESTION_ENABLED` and `ARGUS_DOCUMENT_EXTRACTION_ENABLED`. Apply
`20261008130000_whatsapp_intake.sql` to the local stack first. Nothing is added
to `render.yaml`; hosted activation is a separate decision.

## Temporary tunnel (bounded)

Meta needs a public HTTPS callback. Run the API locally on port 8000, then:

```sh
cloudflared tunnel --url http://localhost:8000
```

Use the printed `https://<random>.trycloudflare.com` host in step 5. The tunnel
exposes the whole local API, so keep it up only for the test session, then stop
it with Ctrl-C and delete the callback URL in the Meta dashboard.

## Real delivery test

1. With outbound off, sign in on the web and call
   `POST /api/v1/whatsapp/link-codes`. Open `wa_me_url` on your phone and send
   the prefilled `CUADRAO <code>`. Proof: `GET /api/v1/whatsapp/link` shows
   `linked: true` and your last four digits.
2. Send one synthetic receipt photo. Proof: the API logs `WhatsApp message
   settled` with `status=captured`, and `GET /api/v1/financial-documents`
   lists a `saved` draft with `consent: false`. No preparation runs.
3. Send the same photo again. Proof: no second draft.
4. Turn outbound on and restart. Send a second synthetic receipt. Proof: the
   phone receives the acknowledgement with the review link, and the link opens
   the draft only when signed in as you.
5. `DELETE /api/v1/whatsapp/link`, then send a photo. Proof: no capture and a
   "connect from the web app" reply.
6. Stop the tunnel. Remove the callback URL. Logs never hold a phone number,
   message text, media id or provider message id, only a digest prefix.

## Cost and messaging limits

- Messages a user sends to a business are not charged
  ([Meta pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)).
- Meta's pages disagree about replies. The main pricing page says non-template
  replies inside the 24-hour customer service window are free. The
  [pricing update page](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages)
  says service messages are charged per message from October 1, 2026. Every
  reply here answers the person's own message inside that window, and a test
  sends at most a handful. Check the billing panel of the test account before
  sending; the test account has no payment method on file.
- Meta generates the test business number automatically
  ([Meta business phone numbers](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers)).
  Its recipient limit was not confirmed from a primary source; confirm it in
  the API Setup panel before the test.
- Outside the 24-hour window a message needs an approved template and may be
  charged. Intake never starts a conversation, so it sends none.
- Media URLs from Meta expire after 5 minutes. A 404 or 410 records the
  delivery as `failed` and asks the person to resend. A resend captures
  normally, and a redelivery of the same message retries the failed record.

## The Business destination

The founder chose separate Personal and Business spaces on October 8
([slice plan, PR #910](https://github.com/lagarcess/argus/pull/910)).

- Intake is on only while the Business pilot is on. Linking needs the person's
  Business space: link codes and link status answer 404 `business_space_missing`
  until the person starts it. Unlinking (`DELETE /api/v1/whatsapp/link`) is never
  gated, so a person can end their link with the pilot or intake off. The sender link stores `destination_space_id`, filled from
  `public.business_space_of` when the link is created.
- A capture resolves the owner's space with `resolve_business_scope` and saves
  the document in that space. If the link ends before the capture settles, the
  message settles `rejected` with `sender_link_revoked`, keeps no connection and
  gets the not-linked reply. `whatsapp_capture_same_space` refuses a captured
  row whose connection is not in the active link's space.
- The reply language is the sender link's `reply_language`, set from the web
  language when the person created the link code.
- The founder approved the reply copy in `whatsapp/replies.py` on October 8, 2026.
