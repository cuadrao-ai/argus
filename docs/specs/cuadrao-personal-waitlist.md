# Personal app waitlist

Owner: the personal waitlist lane. The root coordinator owns integration and
staging deployment. The English signup CTA links to the Spanish form and collects no data. The old
public signup route uses the same CAPTCHA and opt-in handler. The waitlist and all
six legal routes ship together after an independent exact-head Eval. This PR has made no hosted write, send or purge.

## Data model checklist

- Needs: prove consent, send confirmation and one reminder, confirm membership,
  remove a signup on request and enforce the seven-day or twelve-month deadline.
- Users: the person joining; the automated delivery and retention job; operations
  through aggregate logs. There is no public list or answer readback.
- Grain: one row per normalized email in the existing personal signup table.
  The existing digest is the unique key. No second personal list is introduced.
- History: new consent records the policy version and signup time. Confirmation
  and delivery timestamps change. Existing answers are not overwritten by a
  duplicate submit. An explicit new signup after leaving creates a new row.
- Shape: optional spending answer and plain-text wish, confirmed_at,
  privacy_policy_version, last_confirmation_sent_at, reminder_sent_at and one
  opaque verification ID. Existing created_at is the canonical signup time; no
  redundant signup_at is added. Legacy language, source and consent-version
  columns keep their existing required compatibility values. No IP, browser,
  fingerprint or reply content is stored in the row.
- Constraints: SQL enforces allowed spending choices, 280 characters, unique
  verification IDs and confirmation ordering. RLS remains on; anonymous and
  authenticated roles cannot read or write. RPCs are service-role only.
- Retention: unconfirmed rows expire seven days after signup; confirmed rows
  expire twelve calendar months after signup. Leave immediately removes the
  entire row, including answers and email_digest. No suppression row remains.
  Operator removal by email follows the same whole-row rule, including rows
  previously soft-removed. Repeated requests leave absent addresses absent.
  Existing legacy rows retain their suppression behavior until fresh consent
  is submitted; operator removal no longer creates suppression for absent addresses.
- Idempotency: registration locks the existing email row. Confirmation sends
  reserve a timestamp at least ten minutes apart. Reminder selection claims each
  row once with skip-locked. Provider retries use the same key and body.

## Links, mail and abuse handling

The opaque verification ID is 256 random bits. Email links expose only its first
128 bits and a purpose-bound HMAC. The remaining bits never enter a URL. Each
confirmation link expires after 48 hours, even if a later confirmation is sent.
Leave links do not expire while a row exists, remain valid beyond 30 days, and
repeat successfully after deletion. The leave endpoint accepts one-click POST
and a direct browser GET without login or extra data.

The form checks CAPTCHA hostname and action and includes a honeypot. The service
keeps at most five attempts per IP per hour in the existing process-local limiter;
restarts clear this abuse counter. The durable email limit survives restarts.
Seven or more decimal digits, including separators and invisible format marks,
drop only the optional wish. Links and HTML are stripped. The server never
renders saved answers. No optional resend control is exposed.

Three automatic email types use the shared account layout: confirmation,
24-hour reminder and welcome. All use Reply-To hola@cuadrao.ai, a Cuadrao sender
at cuadrao.ai, the configured postal address, and a small grey leave link with
both one-click unsubscribe headers. They have no code block or Business pitch.
The fourth entry is a launch template, never sent automatically. Its launch body
still needs an explicit future content lock before a manual launch send.

A lost delivery response gets one retry with the same provider key. A second
unknown outcome keeps the claim to avoid duplicate sends. A definite refusal
releases only the matching reservation so it can safely retry. It emits
`waitlist_delivery_failed`; operations must inspect that outcome before retrying.
Welcome retries are limited to the first ten minutes after confirmation and use
the original confirmation timestamp as their provider key.

## Deployment and verification

Apply the new forward migration only after its PR merges. Never apply this
branch directly. Required marketing-server configuration:

- Existing SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and RESEND_API_KEY.
- MARKETING_WAITLIST_FROM: a Cuadrao display name and cuadrao.ai mailbox.
- MARKETING_POSTAL_ADDRESS: the exact approved postal address.
- CUADRAO_WAITLIST_ORIGIN: the HTTPS marketing origin, staging for this release.
- CUADRAO_WAITLIST_TURNSTILE_SITE_KEY and CUADRAO_WAITLIST_TURNSTILE_SECRET.

Schedule `bun scripts/waitlist-maintenance.ts` hourly from the marketing root.
It purges bounded batches first, then sends due reminders. Its output contains
only aggregate counts. A failed send or job exits nonzero. Root owns scheduling
and the first hosted checks; this writer has run only synthetic local deletion.

Run `bun test __tests__`, lint, typecheck, a production build, the marketing
browser suite and `marketing/__tests__/waitlist-postgres.sql` in an isolated local
database after the two signup migrations. Browser tests use explicit CAPTCHA
and provider fixtures; they do not establish live CAPTCHA storage behavior.
The staging walk must observe any cookies/local storage set by the real widget,
verify delivery, confirm, leave, and prove the complete row is absent.

## Legal and shared-file boundaries

The three Markdown sources are exact copies of the approved directory. Both
language sections render at the established ES and EN routes, including
/en/privacy, /en/terms and /en/delete-data. Source hashes are committed. The old
privacy-copy module is removed. No legal page publishes before this waitlist.

In business-footer.tsx this lane owns only LegalNav and the FooterBar copyright
line. The Business CTA writer owns ContactLink and other CTA hrefs. The owning
Eval must re-check this shared file before landing. The website copyright is
only © Cuadrao LLC 2026; the email postal address is not added to that footer.

Legacy notice discovery and claims exclude rows with the new privacy policy
version. This prevents the old manual notice flow from selecting unconfirmed
personal signups or using its old email layout for them.
