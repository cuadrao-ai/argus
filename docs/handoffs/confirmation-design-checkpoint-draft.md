# Auth entry and confirmation design checkpoint draft

Status: the user approved the signup, sign-in, and confirmation designs on
2026-10-22 and then cleared the checkpoint handoff and integration. The integration
branch is `codex/auth-checkpoint2-integration-20261022`, based on design commit
`db1887d91d0a1c603e7a98e3bba56e9995d86010` and fetched integration commit
`b8eed7ee4ec2422324ebb61ad1459777fd135fd4`. The original design branch is preserved.
Root owns independent Eval, merge, and the return to the frontend design owner.
Deployment and hosted acceptance remain separate gates.

## Provider evidence and design decision

On 2026-10-22 the user explicitly confirmed these settings match in production
and staging. This confirmation supersedes the earlier screenshot uncertainty and
the earlier report that the current-password requirement was off.

| Setting | Confirmed in both environments |
| --- | --- |
| Email provider | On |
| Secure email change | On |
| Secure password change | Off |
| Require current password when updating | On, staging corrected |
| Prevent leaked passwords | Off |
| Minimum password length | 8 characters |
| Password composition requirements | No required character classes, staging corrected |
| Email OTP expiry | 3,600 seconds |
| Email OTP length | 8 digits |

Source: the user's settings confirmation, not an independent provider readback.
The design lane made no hosted settings changes and sent no verification emails.
Delivered-code and connected-workflow evidence remain integration checks.

The confirmation field now uses eight slots over one string. The length constant
controls validation, slot count, selection bounds, and translated help. CSS derives
column count from the rendered slots. Paste removes spaces and keeps leading zeros.
Six and seven digits are incomplete. The approved artwork and themes remain.

The earlier six-digit assumption was based on local configuration, not hosted proof.
The existing email verification helper accepts six through ten digits. It is not
proof of what the provider generates. This change leaves that shared helper alone.
The password strength indicator is guidance, not a leaked-password check.

## Confirmation integration

- Confirmation keeps eight slots over one string. Spaces are removed. Leading
  zeros remain. Invalid characters and overlong input produce an error without
  becoming valid tokens. The shared helper keeps its six-through-ten-digit
  contract for existing callers.
- Temporary verification failures keep the code for retry. Rejected and expired
  service categories use the approved rejected-code copy and clear the code.
  The service can use its expired category for invalid or used codes too.
- The existing auth client verifies the token and installs the returned session.
  A rejected signup token can continue only when a current session exists and a fresh
  identity request proves the same confirmed email. Other email OTP types still
  reject their failed tokens. Another email, an unconfirmed
  user, a missing session, and a failed identity check cannot take this path.
- A failed continuation keeps verified status. Retry runs continuation only and
  never verifies the consumed code again.
- Verification and resend share one synchronous lock. Mode changes and unmounts
  invalidate pending UI responses. No automatic resend loop runs.
- Resend makes a bounded request to the existing auth service with a fresh browser
  security check. Acceptance appears only after service acceptance. The response
  controls a supplied Retry-After delay. A missing or hidden header uses the
  existing 30-second advisory delay. That fallback is not the service's limit.
- The service owns actual token validity, expiry, invalidation, account obfuscation,
  browser-check acceptance, and abuse limits. The UI does not infer email delivery
  or whether an account exists from a successful resend response.
- No code, password, or confirmation context is saved for reload. The explicit
  signup or login URL returns to email-first entry. The ordinary home URL retains
  its existing current-account check. Reload never triggers a resend or invents
  confirmation success. Service limits still apply after reload.

## Separate release evidence

The synthetic email-hook test confirms that an eight-digit code with a leading
zero appears unchanged in subject, text, and HTML. It does not prove delivery.
Connected signup, a delivered email, hosted header exposure, old-code behavior,
and physical-phone keyboard, autofill, and screen-reader acceptance remain open.
The user reports eight-digit codes and a 3,600-second expiry in staging. No hosted
setting was read or changed in this integration. No real email was sent.

A change-email escape, recovery redesign, and profile-name persistence are outside
this checkpoint. Return any additional product decision to the user before edits.

## Approved signup and sign-in refinements

- Entry starts with email. Signup also collects optional first and last names.
  Continue validates locally and reveals the password before any auth request.
- One mounted card expands and contracts in place. Shared fields and the submit
  button keep their DOM identity. Collapsed sections are inert and hidden from
  assistive technology. Reduced motion removes the transition.
- Persistent labels stay above muted, translated placeholders. Focus outlines
  have space around the animated sections and no longer clip at the sides.
- Email can be edited from the password step. Editing or switching auth mode clears
  the password and preserves the email. The eyelash visibility toggle stays.
- The hero types on first arrival only. Later language and mode changes show the
  complete phrase with a short hero-only fade. The whole form does not fade.

## Deferred profile-name follow-up

The user requested that names entered during signup can prefill the Settings
profile form. The current profile modal appears to repeat name editing in its
header and its preferred-name section. Review that surface in a later checkpoint.
Use one canonical profile value and define any separate preferred-name meaning
explicitly. Do not overwrite a later profile edit with stale signup data.
This is a recorded product follow-up, not a claim that persistence is wired.
No profile components or backend code were changed for this checkpoint.

## Proposed next checkpoint

Recommendation only, pending the user's scope decision: group forgot-password
entry, request confirmation, recovery-link handling, and password reset into one
connected recovery checkpoint. Treat signed-in password change as a distinct
entry path with its own current-password requirements. Confirm its scope before
editing. Start dependent work from the resulting integration commit after the
orchestrator returns ownership. This recommendation does not assign recovery implementation.

## Local verification

The regression tests first reproduced malformed input becoming a valid token and
temporary failures clearing entered digits. Focused helper and DOM tests cover
those cases, resend locking, stale mode responses, and safe continuation retry.
They also reproduced rejected non-signup OTPs becoming successful when a signup
session was present, then proved that only signup can use that fallback.
The email-hook proof uses an injected synthetic sender and sends no email.

Before the final signup-only guard, the full web suite passed with 3,534 tests,
one skipped, and zero failed. The final focused tests pass with 48 tests.
Lint passes with zero errors and 11 existing warnings. The production build passes.
The baseline captures were taken before confirmation wiring changed. The existing
headless evidence workflow captures the final head and uploads images outside Git.
The matrix covers both languages and themes, reduced motion, entry, confirmation,
keyboard input, spaced paste, leading zeros, malformed input, temporary failures,
rejection, resend pending, acceptance, failure, rate limits, and reload behavior.
Its manifest records the exact head and image hashes. Browser evidence uses only
synthetic local responses. Root must inspect the final artifact and run independent
Eval before merge. A passing test or build does not authorize a deploy.
