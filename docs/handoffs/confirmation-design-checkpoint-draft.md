# Auth entry and confirmation design checkpoint draft

Status: on 2026-10-22 the user accepted signup, sign-in, and confirmation
designs as complete and requested a local commit.
Not approved for handoff, integration, or release.
Ownership remains in the design lane. No confirmation checkpoint has been sent
to the orchestrator. The user approved a local commit of this iteration.

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

## Remaining integration evidence and wiring

These items are recorded for a future approved handoff, not assigned work now.

- Retain the user-confirmed eight-digit contract. Record the target environment
  when collecting connected-workflow evidence.
- Confirm the signup email template includes the code, and verify one controlled
  end-to-end signup at the approved integration test gate.
- The preview resend countdown is 30 seconds and sends no email. This is separate
  from the one-hour code expiry. Real resend needs pending, sent, failure, and
  rate-limit handling based on the service response.
- Verification currently clears the code on any failure. Error classification
  needs to distinguish rejected or expired codes from temporary connection errors.
- A change-email escape was raised during the audit but is not part of the accepted
  confirmation design. If required for recovery during integration, bring the
  proposed experience back to the user before adding it.
- Physical-phone keyboard, autofill, and screen-reader acceptance remain open.
- Inputs longer than eight digits are currently trimmed by the frontend. Backend
  validation must reject malformed tokens without truncating them into valid ones.
  Any change to the accepted input experience needs user review.

## OTP edge cases for the eventual backend handoff

Confirmation design approval is not end-to-end auth acceptance. The integration
owner must preserve the approved design while handling these cases gracefully.
This list records expectations for the eventual handoff; it does not start work.

| Case | Required behavior |
| --- | --- |
| Incorrect or expired code | Return a stable error category with a useful next step. Keep the user on confirmation. Distinguish expiry from an incorrect code when the service supports it. |
| Offline, timeout, or temporary service failure | Keep the typed code and offer retry. Do not label a connection problem as an incorrect code or clear the field. The current generic clear-on-failure behavior needs integration repair. |
| Verification succeeds but navigation or session continuation fails | Preserve verified status and retry continuation safely. Do not require the user to reuse a consumed code. |
| Used code, already-confirmed account, or concurrent tabs | Reconcile the real confirmation and session state. Provide a safe continuation or sign-in path without inventing success or exposing another account's state. |
| Duplicate clicks and concurrent verification or resend | Prevent duplicate requests and ignore stale responses. An old request must not overwrite the current email, code state, or auth mode. |
| Resend rejected, delayed, or rate-limited | Show sent status only after service acceptance. Respect the service retry delay, including Retry-After when supplied. Keep expiry separate from resend cooldown. Avoid automatic resend loops. |
| Old code after resend | Match the provider's actual invalidation behavior and explain what to do next. Do not assume that every resend invalidates previous codes without checking. |
| Reload during cooldown or an interrupted request | Reconcile with server state. Reloading must not bypass rate limits or produce a false success. |
| Missing or mismatched email, malformed code | Validate the signup confirmation context and eight-digit token on the server. Preserve leading zeros and never interpret the code as a number. |
| Abuse and sensitive data | Enforce verification and resend limits on the server. Do not log raw codes, tokens, or passwords, and do not leak account existence through errors. |

Errors and recovery actions must have natural Spanish and English copy, accessible
feedback, and the stable button placement already approved. Do not expose raw
provider errors. Missing product decisions or material visual changes return to
the user before implementation. The delivered-code length and real workflow still
need evidence from the intended environment at the approved integration test gate.

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
orchestrator returns ownership. No handoff or integration work is assigned now.

## Verification results

- Before the change, regression tests failed on the six-slot rendering and acceptance
  of incomplete six-digit codes.
- All 35 focused auth tests pass, including eight-digit submission, whitespace,
  leading zeros, incomplete input, rejection, pending lock, and duplicate prevention.
- The prior confirmation-only matrix passed all 16 local browser cases. Chromium covers 320, 390, and 1440 px. WebKit
  covers 390 px. Both languages and themes have no horizontal overflow or CTA
  movement after incomplete and rejected codes. Typing, backspace, spaced paste,
  and focus restoration pass. These tests use synthetic requests only.
- The latest entry refinements were inspected in the local browser in both themes
  and languages. The password focus outline and placeholders were checked visually.
  These desktop checks do not extend the prior confirmation matrix to all entry viewports.
- TypeScript and diff checks pass. The prior lint run had zero errors and 11 existing warnings.
- Screenshots are stored outside Git in the task visualization folder with the
  prefix `confirmation-eight-`. Mobile light and dark captures were inspected.
- Following Model the Domain, the existing one-string state is retained. One length
  constant supplies the rendering and validation contract. No new state is added.

The local commit does not authorize a push, deployment, provider edit, or checkpoint
handoff. The user must approve and request the handoff separately.
