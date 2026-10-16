# Personal waitlist implementation checkpoint

Owner: the personal waitlist lane. The root coordinator owns staging deployment.
This draft follows the October 16 personal waitlist request. It does not change
Business CTA destinations, Business inquiries, the English form, or account emails.

The current branch is incomplete and must not be deployed. The new Spanish form
posts to `/api/waitlist/signups`, which returns 503 without writing or sending.
The existing deployed site remains unchanged. The legacy `/api/signups` route is
unchanged for the existing English form.

## Verified work

The optional spending answer uses the five approved choices. The optional wish
is capped at 280 characters and is never rendered back by the server. Seven or
more decimal digits, including digits separated by spaces or punctuation, remove
only the wish. HTML and links are removed. The email remains valid for signup.

The CAPTCHA verifier requires a successful response for the request hostname
and the `personal_waitlist` action. Missing tokens or secrets fail closed. The
browser widget resets after a submit attempt. The page sets no tracking state.
Real CAPTCHA cookie and storage behavior still requires a staging observation.

The four email body entries preserve the approved confirmation, reminder and
welcome copy. Launch is a template-only entry with no approved launch body and
cannot be sent automatically. The shared account-email writer owns rendering.
Waitlist transport owns one-click unsubscribe headers. Account emails receive
neither an unsubscribe link nor an unsubscribe header.

The three legal Markdown files are byte-identical copies of the source directory.
The Spanish routes render the Spanish portion, as the existing legal renderer
does. The English form and English privacy route remain unchanged. The source
hashes are in `marketing/content/legal-waitlist-source/manifest.json`.

## Pending decisions and checks

The requested stored-field list omits signup time, but the 24-hour reminder,
48-hour link, seven-day unconfirmed retention and twelve-month confirmed retention
need it. Durable send limits and an exactly-once reminder also require bounded
operational state. Storage approval is pending. No migration, stored field,
retention run, hosted email or staging database write has been made by this lane.

Timing functions currently use synthetic records only. Tests cover exact time
boundaries, repeated reminder suppression and leap-day retention. They do not
prove durable scheduling, email delivery, database concurrency or deletion.

The full acceptance gate remains unchecked until storage is approved, the shared
layout is integrated, the real database lifecycle is implemented and tested, and
Priya evaluates the final head. This checkpoint is not a SHIP verdict.

## Detection and tradeoffs

The unavailable route returns 503 so an unfinished flow cannot silently create
an unconfirmed signup through the legacy route. This blocks new Spanish signup
only if someone deploys the draft, which is forbidden until the acceptance gate
passes. The digit check can remove an innocent long number. That is preferable
to storing an account number, and it never rejects the email signup.
