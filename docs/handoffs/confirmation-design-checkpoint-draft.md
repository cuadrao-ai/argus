# Confirmation design checkpoint draft

Status: design iteration only. Not approved for handoff, integration, or release.
Ownership remains in the design lane. No confirmation checkpoint has been sent
to the orchestrator. The user approved a local commit of this iteration.

## Provider evidence and design decision

On 2026-10-22 the user supplied an email-provider settings screenshot showing:

- Email OTP length: 8 digits.
- Email OTP expiration: 3,600 seconds (one hour).
- Minimum password length: 8 characters.
- Password composition requirements: no option selected.
- Leaked-password protection: off.
- Email provider and secure email change: on.
- Secure password change and current-password requirement on update: off.

The screenshot does not establish the project identity or whether the displayed
values were saved. No account login, settings change, or email send was performed
by the design lane. The user approved aligning the frontend to eight digits.

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

- Confirm the target project has the saved eight-digit setting.
- Confirm the signup email template includes the code, and verify one controlled
  end-to-end signup at the approved integration test gate.
- The preview resend countdown is 30 seconds and sends no email. This is separate
  from the one-hour code expiry. Real resend needs pending, sent, failure, and
  rate-limit handling based on the service response.
- Verification currently clears the code on any failure. Error classification
  needs to distinguish rejected or expired codes from temporary connection errors.
- A change-email escape is a pending design decision.
- Physical-phone keyboard, autofill, and screen-reader acceptance remain open.
- Inputs longer than eight digits are currently trimmed; confirm the final treatment
  before checkpoint approval.

## Verification results

- Before the change, regression tests failed on the six-slot rendering and acceptance
  of incomplete six-digit codes.
- All 33 focused auth tests pass, including eight-digit submission, whitespace,
  leading zeros, incomplete input, rejection, pending lock, and duplicate prevention.
- All 16 local browser cases pass. Chromium covers 320, 390, and 1440 px. WebKit
  covers 390 px. Both languages and themes have no horizontal overflow or CTA
  movement after incomplete and rejected codes. Typing, backspace, spaced paste,
  and focus restoration pass. These tests use synthetic requests only.
- TypeScript and diff checks pass. Lint has zero errors and 11 existing warnings.
- Screenshots are stored outside Git in the task visualization folder with the
  prefix `confirmation-eight-`. Mobile light and dark captures were inspected.
- Following Model the Domain, the existing one-string state is retained. One length
  constant supplies the rendering and validation contract. No new state is added.

The local commit does not authorize a push, deployment, provider edit, or checkpoint
handoff. The user must approve and request the handoff separately.
