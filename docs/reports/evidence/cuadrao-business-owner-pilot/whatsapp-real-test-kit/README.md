# WhatsApp real test: setup checklist

Status: prepared, **not approved to send**. This kit is for one founder-run test of real WhatsApp delivery against local services. It uses Meta's free test number. It changes nothing hosted.

## What you set up in Meta (about 15 minutes)

1. **Create the app.** In the [Meta App Dashboard](https://developers.facebook.com/apps), choose Create app, pick the WhatsApp use case and your business portfolio. Meta creates a test WhatsApp account and a test business number.
2. **WhatsApp > API Setup.**
   - Note the **test number** and its **Phone number ID**.
   - Choose **Generate access token**. The token is temporary, so generate it on the day of the test.
   - Under **To**, choose **Manage phone number list** and add your personal WhatsApp number. Enter the code Meta sends to your phone.
   - Note the recipient limit the panel shows. It isn't confirmed from a primary source.
3. **App settings > Basic.** Copy the **App secret**.
4. **Verify token.** Make up a long random string and keep it private.
5. **WhatsApp > Configuration > Webhook.** Do this during the session, after I start the tunnel.
   - Callback URL: `https://<tunnel host>/api/v1/webhooks/whatsapp`.
   - Verify token: the one from step 4. Choose Verify and save. "Verified" proves our API answered Meta.
   - Under Webhook fields, subscribe to **messages** only.
6. **Billing check.** In WhatsApp Manager, confirm the test account has no payment method on file.

Put the four secrets (access token, Phone number ID, App secret, verify token) into the local API env file yourself, under the names in the [activation packet](../../../../specs/lanes/cuadrao-whatsapp-intake.md#environment-api-process-only-never-the-web-app). Never paste them into chat.

## Test sender

Your personal WhatsApp, added in step 2. No other phone takes part. Business owners keep their own numbers; this test does not move your number anywhere.

## What runs where

- The API and web run on this Mac, at the test head, against the local Docker database. The Business pilot and WhatsApp flags are on only in that local process.
- AI preparation stays off. Every receipt is saved without consent, so no model is called.
- A temporary [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) gives Meta a public HTTPS address for the local API.
  - `cloudflared` is not installed yet. It needs `brew install cloudflared`, which is part of the approval below.
  - The tunnel exposes the whole local API, so it runs only for the session. Afterwards it is stopped and the callback URL is removed in Meta.

## The messages

You send these from your phone to the test number. The synthetic receipts are in this folder, each marked SAMPLE DATA.

| Step | You send | Outbound | Expected result | Reply you receive |
| --- | --- | --- | --- | --- |
| 1 | `CUADRAO <code>`, prefilled by the link I give you | off | `GET /api/v1/whatsapp/link` shows `linked: true` and your last four digits | none |
| 2 | `receipt-1-ferreteria.png` | off | It lands in your Business Inbox as saved, with no AI run | none |
| 3 | the same photo again | off | No second receipt | none |
| 4 | `receipt-2-colmado.png`, after outbound is turned on and the API restarts | on | A new receipt in the Inbox; the link opens it only when you're signed in | "Recibimos tu recibo y lo guardamos en tu bandeja. Revísalo y confírmalo en Cuadrao: {link}" |
| 5 | the same photo again | on | No second receipt | "Ya tenemos este recibo en tu bandeja, así que no lo guardamos dos veces. Revísalo en Cuadrao: {link}" |
| 6 | You disconnect on the web (`DELETE /api/v1/whatsapp/link`), then send `receipt-3-panaderia.png` | on | Nothing saved | "Este número no está conectado a Cuadrao. Conéctalo desde Cuadrao en la web y vuelve a enviar el recibo." |

- If you link with the web in English, the replies come in English.
- At most three replies are sent, each answering your own message inside WhatsApp's 24-hour window. No template message is ever sent.
- After step 4, you review and confirm that receipt on the web. It becomes one expense, and its original downloads unchanged.

## Cost

Expected **$0**.
- Messages you send to the business are not charged.
- Meta's pages disagree on replies:
  - the main pricing page says replies inside the 24-hour window are free;
  - the pricing update page says service messages are charged per message from October 1, 2026.
- This test sends at most three replies, from a test account with no payment method.
- No number purchase, no provider subscription and no hosted resource is involved.

## Needs your approval before anything is sent

1. Installing `cloudflared` with Homebrew.
2. Running the temporary tunnel for the session.
3. Turning outbound on for steps 4 to 6, which sends the three replies above to your phone.

## Prepared locally

- Synthetic receipts: this folder.
- The full sequence, with signed Meta-format deliveries and local media, already passes on local services. See `../2026-10-08-isolation-e2e/evidence-log.md`. It is rerun at the final B1 head before the real test.
- There is no web screen for linking yet, so I create the link code and give you the `wa.me` link.
- Afterwards I write the result to `evidence-log.md` in this folder: what Meta delivered, the replies, the counts, and the tunnel and callback removed.
