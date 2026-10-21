# Staging recovery email, issue #1117

Base integration: `2fdae8c5e443c9bf8f59d22b1fb081cc0589ee37`.
Code is implemented with the hook disabled. Hosted activation, real delivery,
SPF/DKIM/DMARC and actual email-client dark-mode proof remain pending.

## Owners and delivery

The hand-written renderer in `marketing/lib/email/account-layout.ts` owns the
shared account and waitlist layout. `scripts/emails/sync-layout.mjs --check`
checks its generated web copy. Auth and security copy lives in
`web/server/emails`; Supabase owns tokens, verification and expiry.

The sender is `Cuadrao <no-responder@mail.cuadrao.ai>` with Reply-To
`hola@cuadrao.ai`. Mail has a hidden preheader, HTML title, a greeting above the
code, and the footer `Saludos,` followed by `Cuadrao` on a new line. The legal
line contains the company and approved address from `MARKETING_POSTAL_ADDRESS`.
The renderer refuses missing or multiline postal configuration. Callers may
supply the same address through `postalAddress`; account mail has no unsubscribe
link or headers. No environment files or hosted settings were changed.

Images use `CUADRAO_EMAIL_ASSET_ORIGIN`, defaulting to `https://cuadrao.ai`, or an
explicit `assetOrigin`. The shared renderer supports media-query dark styles
and Outlook `data-ogsc` selectors. The generated Business close artifact carries
a full `tokens.postalAddress` marker; its Python caller must substitute the
configured legal line once, just like the asset-origin marker.

The hook supports signup, magic link, recovery, secure two-recipient email
change and reauthentication. Supabase invitation is excluded. Business invitation
has a separate owner and template. Password-changed and email-changed notices
have approved copy; email-changed goes to the old address. The other five
security notices are disabled and send nothing. Committed notification flags do
not prove hosted activation. Security notices use send time in
`America/Santo_Domingo`, with non-breaking day-period spaces normalized so ICU
versions produce identical snapshots.

Signed payloads are capped at 64 KiB. Standard Webhooks verifies the raw body
and timestamp before JSON schema parsing. The dedicated secret, project ref,
Supabase URL, signed web origin, expiry and built-in `RENDER_SERVICE_ID`
`srv-db5ihr7lot8c73f3b3h0` all bind this route to staging. Next can construct
`Request.url` with an internal server hostname behind Render, so request URLs
and forwarded headers do not establish deployment identity.
[Render supplies the service ID automatically](https://render.com/docs/environment-variables#all-runtimes);
no manually configured environment value is needed. User metadata
is not authorization. Recipients come only from the signed payload. PKCE token
prefixes are retained. Empty redirects preserve Supabase's site default;
nonempty redirects remain in the staging origin. No payload, recipient, token,
provider response or secret is logged.

Resend receives explicit HTML and generated plain text from the same shared
render. A hashed webhook/action/recipient key makes repeats and partial
email-change retries duplicate-safe within Resend's idempotency retention.
The sender shares a four-second deadline across both recipients and does not
retry automatically. A failed or uncertain send returns a generic hook error.

## Staging activation, root coordinator only

1. Complete exact-head review/Eval and obtain explicit activation authority.
2. Read back `skedzwocnmrhfigiwyzi` Auth settings. Require `mailer_otp_exp=3600`,
   the reviewed core templates and the two approved notification flags.
   The other five notices must stay disabled. Do not infer hosted enablement
   from committed template presence.
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
approved HTML/plain snapshots, sender headers, MIME parts, signature mutation/staleness,
project/origin/expiry refusal, body limits, PKCE, empty redirects, two-recipient
mapping and partial-send retry keys. Root retains browser CSS layout evidence.


## October 17 template verification

The Auth snapshot tests check all eight recipient-specific renders. The shared
presentation test snapshots four waitlist templates, nine disabled preview slots
and Business close mail. Each render checks visible text/background contrast at
4.5:1 in light CSS and Outlook dark CSS. The tests inject bad colors in each mode
to prove the checks fail. New invite and transfer writers must call
`assertEmailPresentation(html, text)` from
`web/__tests__/helpers/email-presentation.ts` beside their own snapshots.

Fresh synthetic Chromium light/dark screenshots for all eight Auth renders are
in `evidence/shared-account-email/final-delta`. They confirm the address, absence
of account unsubscribe and lack of horizontal overflow. They are browser CSS
proof only. Gmail, iOS Mail and Outlook screenshots still need explicit staging
hook activation and real inbox delivery authority.

The universal checker command is `node scripts/emails/check-branding.mjs`.
It scans canonical/deployed email renderers, generated Python artifacts and
active email snapshots. It currently fails on the live legacy
`src/argus/domain/access_approval_email.py`. Removal is blocked because its send
path is coupled to admission approval and a database guard. The coordinator
needs a product decision before that path can change. CI activation of this
checker is held until that dependency is resolved; no legacy allowlist is used.
The universal branding requirement remains open.
