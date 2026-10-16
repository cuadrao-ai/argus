# Personal waitlist WIP evidence

This draft is incomplete and must not be deployed. Owner: the personal waitlist
lane. The root coordinator owns merge and staging actions.

The before screenshot shows the existing staging page without a submission.
The after images show the local production build. The CAPTCHA widget is an
explicit fixture. The success image also uses an explicit API response fixture.
The actual local `/api/waitlist/signups` returns 503 and performs no write.
These images prove layout and UI state only, not signup durability or email delivery.

- `before-mobile.png` is the unchanged staging page.
- `after-mobile.png` and `after-desktop.png` show the new Spanish fields.
- `confirmation-fixture-mobile.png` shows the approved response sentence.
- The three legal images show exact Spanish source text at 390 pixels.

Verification used `bun run lint`, `bun run typecheck`, `bun test __tests__`,
`bun run build --webpack`, and the focused Playwright legal and waitlist tests.
All 194 unit tests passed with 465 assertions. All 18 browser checks passed.
The browser checks include 320-pixel and 390-pixel legal layout, accessibility,
source text equality, optional fields, the inline digit warning, and the
unfinished endpoint's 503 response. The production build passed.

`python3 marketing/scripts/verify-legal-source.py` reproduces source equality.
The latest supplied Markdown files are retained byte-for-byte under
`marketing/content/legal-waitlist-source/`. Their manifest records source hashes.
The Spanish rendered text contains 1455 privacy words, 204 deletion words and
405 terms words. No date placeholder remains in the supplied terms file.

Real CAPTCHA cookie and browser-storage behavior is not verified. The synthetic
widget wrote no cookie, local storage or session storage. No cookie banner was
added. No provider call, customer email, hosted database write or deletion ran.

Storage approval, durable confirmation, reminder delivery, retention scheduling,
shared email integration, exact-head CI and independent Eval remain open.
See `docs/specs/cuadrao-personal-waitlist.md` for the pending data-contract choice.
