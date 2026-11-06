# Auth email source of truth

This document owns the Cuadrao Auth email design, code handling, delivery boundary, and pilot notice scope. The decisions were locked on November 5, 2026, around 11:17 to 11:25 PM CT.

These are target rules, not a claim that every repo or hosted setting already matches. This documentation change implements no fixes and authorizes no publication.

## Design standard

Auth emails use a light card with the dark-green Cuadrao header and short copy. Code-bearing emails show the eight-digit code prominently.

Signup, recovery, invite, and security notices share the same layout. Only the message and action change. A notice does not become a code challenge merely because it shares the layout.

The all-dark signup template and Argus-branded Auth templates are retired as design standards. Replacing them in code or hosted configuration is separate implementation work.

## Ownership and publication

Supabase Auth owns code creation and verification. Resend only delivers the email. Delivery does not create, shorten, pad, or validate Auth codes.

Design and copy live in the repo. Supabase Auth templates are generated from those sources, then explicitly published and read back. A local render is not a hosted update. Readback confirms the intended template slot, content, sender, notice settings, and code length without copying secrets or environment values into evidence.

A new Auth hook is not the solution to a visual mismatch. The existing staging hook is not removed by this decision or this document.

The current repo paths establish the source and generation boundaries.

| Role | Verified repo path | Boundary |
| --- | --- | --- |
| Shared account layout source | [marketing/lib/email/account-layout.ts](../../marketing/lib/email/account-layout.ts) | Owns the shared card and code presentation. |
| Layout and shared copy generation | [scripts/emails/sync-layout.mjs](../../scripts/emails/sync-layout.mjs) | Generates the web layout and marketing shared copy from repo sources. |
| Generated web layout | [web/server/emails/account-layout.generated.ts](../../web/server/emails/account-layout.generated.ts) | Generated output, not a second design authority. |
| Auth message copy and rendering | [web/server/emails/auth-actions.tsx](../../web/server/emails/auth-actions.tsx) | Defines action-specific copy and rendering. |
| Security notice copy | [web/server/emails/security-notices.ts](../../web/server/emails/security-notices.ts) | Defines password and email change notices and disabled notice kinds. |
| Auth template slot map | [web/server/emails/auth-paste.ts](../../web/server/emails/auth-paste.ts) | Maps generated content to the confirmation, magic-link, recovery, invite, and email-change slots. |
| Local template rendering | [scripts/emails/render-staging-auth.ts](../../scripts/emails/render-staging-auth.ts) | Writes local template artifacts. Does not publish configuration or send mail. |

The generation and publication rule applies to the shared Auth layout, including notices. Existing generator coverage is not proof that every required hosted slot has been published.

## Eight-digit code contract

The form, local email Auth configuration, and code-bearing templates use eight digits. Codes are never trimmed, truncated, or padded to force a match. A length mismatch is drift, not a reason to alter the issued code.

Hosted Auth already uses eight digits according to the November 5 record. That is recorded context, not a fresh hosted readback performed for this document.

| Surface | Repo evidence | Status |
| --- | --- | --- |
| Signup form | [web/components/auth/AuthForm.tsx](../../web/components/auth/AuthForm.tsx), line 25, `CONFIRMATION_CODE_LENGTH` | The form already expects eight digits. |
| Local email Auth configuration | [supabase/config.toml](../../supabase/config.toml), line 246, `[auth.email].otp_length` | Still specifies six digits. This is drift to fix later, not a change in this documentation task. |
| OTP verification helper | [web/lib/email-otp.ts](../../web/lib/email-otp.ts), line 16 | Accepts six to ten digits today. The eight-digit contract is not yet enforced here. |
| Auth rendering input validation | [web/server/emails/auth-actions.tsx](../../web/server/emails/auth-actions.tsx), line 10 | Accepts six to ten digits today. This document does not change validation. |
| Shared layout code validation | [marketing/lib/email/account-layout.ts](../../marketing/lib/email/account-layout.ts), line 57 | Accepts six to ten digits or the Auth token placeholder today. Template alignment remains implementation work. |

The separate SMS `otp_length` entry is not the email drift. Phone notices are outside the pilot notice scope.

## Pilot security notices

Password-change and email-change notices are on. Phone-change notices are off. This matches repo intent, not a claim that staging and production are synchronized.

The local intent is recorded in [supabase/config.toml](../../supabase/config.toml), lines 267 to 274, under `auth.email.notification.password_changed`, `auth.email.notification.email_changed`, and `auth.email.notification.phone_changed`. The notice renderer is [web/server/emails/security-notices.ts](../../web/server/emails/security-notices.ts).

## Historical hosted drift inventory

The November 5 record identifies the following drift. This is historical inventory only. No hosted dashboard was inspected or changed for this document.

| Environment | Recorded drift |
| --- | --- |
| Staging | The signup template is miswired to email-change. |
| Production | Auth templates still carry Argus branding. |
| Staging compared with production | Notice settings and sender differ. |

The inventory contains no sender addresses, secrets, or environment values. It does not authorize a fix or replace a future explicit readback.

## Out of scope

- Implementing template, code-length, validation, sender, or notice fixes.
- Touching the hosted dashboard or publishing hosted templates or settings.
- Removing the staging hook or building a new Auth hook to fix the look.
- Changing the Business Resend path.
- Retiring the access-approval email.
