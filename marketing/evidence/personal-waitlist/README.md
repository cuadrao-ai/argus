# Personal waitlist verification

Owner: the personal waitlist lane. Root owns merge, migration, scheduling and
staging deployment. The legal pages and waitlist must release together.

`before-mobile.png` shows the unchanged staging page. The after images show the
local production build. CAPTCHA and mail are explicit fixtures. The form success
image uses a response fixture; confirmed and left images exercise the real local
handlers and their provider adapters. The leave check proves the entire fixture
row is absent. These images do not prove hosted delivery.

- `after-mobile.png` and `after-desktop.png` show the Spanish fields.
- `confirmation-fixture-mobile.png` shows the approved check-email state.
- `confirmed-mobile.png` and `left-mobile.png` show completed link actions.
- The three legal images show exact supplied Spanish text at 390 pixels.

The production build, lint and typecheck pass. The unit suite has 200 passes
and 552 assertions. The full browser suite
has 215 passes and one existing mobile fine-pointer skip. It checks legal text,
320/390-pixel geometry, accessibility, the English CTA to the Spanish form, and
signup to confirmation to whole-row leave through real local handlers. The
CAPTCHA adapter uses an explicit test-process fixture, never a runtime bypass.

The SQL suite has 29 passing assertions on local PostgreSQL 17. It covers RLS,
constraints, ten-minute delivery reservations, confirmation expiry, a single
24-hour reminder, seven-day and calendar-year retention, and whole-row removal.
Ten concurrent registration workers produce one send reservation. Ten reminder
workers also produce one reservation. No hosted migration or purge ran.

`python3 marketing/scripts/verify-legal-source.py` proves all six language routes
match the exact supplied Markdown source. The source manifest records hashes.

The real widget's cookies and local storage are NOT PROBED. The explicit fixture
writes neither. No cookie banner was added. Live staging confirmation, delivery,
reminder scheduling and leave proof remain release checks owned by root. The
launch template is never sent automatically.
