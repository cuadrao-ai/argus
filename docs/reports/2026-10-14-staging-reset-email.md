# Staging recovery email, issue #1117

Base integration: `2fdae8c5e443c9bf8f59d22b1fb081cc0589ee37`.
Code is implemented with the hook disabled. Hosted activation, real delivery,
SPF/DKIM/DMARC and actual email-client dark-mode proof remain pending.

## Owners and delivery

`web/server/emails` owns one shared React Email layout, the approved Spanish
reset email, explicit current core Auth templates and the signed hook transport.
Supabase owns tokens, verification and expiry. The existing web recovery route
owns CAPTCHA, configured origin, rate limits and enumeration-safe responses.
The sender is `Cuadrao <hola@mail.cuadrao.ai>` with Reply-To `hola@cuadrao.ai`.
The approved preview is “Crea una nueva contraseña para tu cuenta.” The footer
is only “Cuadrao LLC”. Brand art comes from `marketing/brand/README.md`, using
existing staging `/icons/cuadrao-192.png`. The template has paired light/dark
colours, including a green button in both modes, media-query and Outlook
`data-ogsc` selectors. Browser CSS rendering is not actual email-client proof.

The staging snapshot on October 14 has six default core templates and seven
disabled notifications. Golden fixtures retain the non-recovery subjects and
bodies, with equivalent HTML escaping normalized. There is no Go template
engine. The hook covers signup confirmation, invitation, magic link, recovery,
secure two-recipient email change and reauthentication. Unknown actions return
an error. No email is silently acknowledged or delegated to Supabase SMTP.

Signed payloads are capped at 64 KiB. Standard Webhooks verifies the raw body
and timestamp before JSON schema parsing. The dedicated secret, project ref,
Supabase URL, web origin and expiry all bind this route to staging. User metadata
is not authorization. Recipients come only from the signed payload. PKCE token
prefixes are retained. Empty redirects preserve Supabase's site default;
nonempty redirects remain in the staging origin. No payload, recipient, token,
provider response or secret is logged.

Resend receives explicit HTML and generated plain text from the same React
render. A hashed webhook/action/recipient key makes repeats and partial
email-change retries duplicate-safe within Resend's idempotency retention.
The sender shares a four-second deadline across both recipients and does not
retry automatically. A failed or uncertain send returns a generic hook error.

## Staging activation, root coordinator only

1. Complete exact-head review/Eval and obtain explicit activation authority.
2. Read back `skedzwocnmrhfigiwyzi` Auth settings. Require `mailer_otp_exp=3600`,
   all seven notification flags disabled and unchanged five non-recovery
   subject/body templates. Do not infer enablement from template presence.
3. Verify `mail.cuadrao.ai` sender identity and disable auth-link tracking.
4. Inject `CUADRAO_AUTH_EMAIL_HOOK_SECRET` and the dedicated server-only
   `CUADRAO_AUTH_EMAIL_RESEND_API_KEY` using an authorized staging sending
   credential. Do not fall back to Business/marketing environment variables or
   production keys. Both names are held in the staging environment tool
   until activation. No key uses a `NEXT_PUBLIC_` name.
5. Configure the reviewed staging web with project ref
   `skedzwocnmrhfigiwyzi`, exact staging Supabase URL, existing staging
   `ARGUS_APP_ORIGIN`, and `CUADRAO_AUTH_EMAIL_OTP_EXP_SECONDS=3600`.
   This number is an activation assertion of actual Supabase configuration;
   it is not a second expiry authority. Recheck it whenever Auth settings change.
6. Enable the web handler, then point only staging Supabase's Send Email Hook
   at `https://cuadrao-web-staging.onrender.com/api/auth/send-email` using its
   signed secret. Enabling replaces delivery for every Auth email action.
7. Under the separate approved send budget, prove recovery delivery, exact
   headers, both MIME parts, configured redirect and one-use expiry/session
   behavior. Verify secure email-change delivery to both addresses and retained
   other enabled core actions. Never expose live links in evidence.

Default configuration declares `CUADRAO_AUTH_EMAIL_HOOK_ENABLED=false`.
Changing the one-hour Auth expiry requires coordinated approved copy/config
changes; the handler refuses an asserted expiry other than 3600.
Local QA's 60-second expiry stays unchanged.

Rollback disables staging Supabase's hook first, restoring its previous default
sender, then disables the web handler. Restore captured Auth settings if any
were changed. No database migration is needed. Production is outside this scope.

## Local verification

Use Bun for render, hook, sender and existing auth-security tests. Provider fetch
is injected and mocked; these tests send no email. Focused tests cover full
captured core content, sender headers, MIME parts, signature mutation/staleness,
project/origin/expiry refusal, body limits, PKCE, empty redirects, two-recipient
mapping and partial-send retry keys. Root retains browser CSS layout evidence.
