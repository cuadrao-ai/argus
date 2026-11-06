# Auth email source of truth

This document owns the Cuadrao Auth email design, code handling, delivery boundary, and pilot notice scope. The decisions were locked on November 5, 2026, around 11:17 to 11:25 PM CT.

The repo enforces the eight-digit contract and generates all eight Auth template slots locally. Local generation authorizes no hosted publication and does not claim that hosted settings match.

## Design standard

Auth emails use a light card with the dark-green Cuadrao header and short copy. Code-bearing emails show the eight-digit code prominently. All eight Auth emails open directly with their purpose, followed by the existing code or action and safety copy. They omit the “Hola,” greeting and “Saludos, Cuadrao” sign-off. The help, contact and legal footer stays.

Signup, recovery, invite, and security notices share the same layout. Only the message and action change. A notice does not become a code challenge merely because it shares the layout.

The all-dark signup template and Argus-branded Auth templates are retired as design standards. The local generator uses the shared layout for all eight slots. Hosted replacement remains separate publication work.

## Ownership and publication

Supabase Auth owns code creation and verification. Resend only delivers the email. Delivery does not create, shorten, pad, or validate Auth codes.

Design and copy live in the repo. Supabase Auth templates are generated from those sources, then explicitly published and read back. A local render is not a hosted update. Readback confirms the intended template slot, content, sender, notice settings, and code length without copying secrets or environment values into evidence.

A new Auth hook is not the solution to a visual mismatch. The existing staging hook is not removed by this decision or this document.

The current repo paths establish the source and generation boundaries.

| Role | Verified repo path | Boundary |
| --- | --- | --- |
| Shared account layout source | [marketing/lib/email/account-layout.ts](../../marketing/lib/email/account-layout.ts) | Owns the shared card and code presentation. |
| Layout and shared copy generation | [scripts/emails/sync-layout.mjs](../../scripts/emails/sync-layout.mjs) | Generates the web layout, marketing shared copy, and marketing OTP contract from repo sources. |
| Generated web layout | [web/server/emails/account-layout.generated.ts](../../web/server/emails/account-layout.generated.ts) | Generated output, not a second design authority. |
| Auth message copy and rendering | [web/server/emails/auth-actions.tsx](../../web/server/emails/auth-actions.tsx) | Defines action-specific copy and rendering. |
| Revised security notice copy | [Spanish catalog](../../web/public/locales/es-419/common.json) and [English catalog](../../web/public/locales/en/common.json) | `account_email.auth_security` owns the revised descriptions, recovery contact and safety warning. Auth continues to select Spanish. |
| Security notice rendering | [web/server/emails/security-notices.ts](../../web/server/emails/security-notices.ts) | Renders password and email change notices and defines disabled notice kinds. Older unchanged hardcoded copy is deferred in #1839. |
| Auth template slot map | [web/server/emails/auth-paste.ts](../../web/server/emails/auth-paste.ts) | Owns the typed registry for confirmation, magic-link, recovery, invite, email-change, reauthentication, password-changed notice, and email-changed notice slots. |
| Local template rendering | [scripts/emails/render-staging-auth.ts](../../scripts/emails/render-staging-auth.ts) | Syncs shared sources and writes or checks local template artifacts. Does not publish configuration or send mail. |

The generation and publication rule applies to all eight slots, including notices. The approved notice copy omits date and time and shows the full new email address. Hosted notices provide no send timestamp. The email-changed notice uses `{{ .OldEmail }}` for the old address and `{{ .Email }}` for the new address. Local generator coverage is not proof that any hosted slot has been published.

## Eight-digit code contract

The form, local email Auth configuration, and code-bearing templates use eight digits. Codes are never trimmed, truncated, or padded to force a match. A length mismatch is drift, not a reason to alter the issued code.

Hosted Auth already uses eight digits according to the November 5 record. That is recorded context, not a fresh hosted readback performed for this document.

| Surface | Repo evidence | Status |
| --- | --- | --- |
| Shared contract | [web/lib/email-otp-contract.ts](../../web/lib/email-otp-contract.ts) | Owns the length, ASCII pattern and exact-length validator. |
| Signup form | [web/components/auth/AuthForm.tsx](../../web/components/auth/AuthForm.tsx) | Reads the shared length and rejects whitespace without changing the code. |
| Local email Auth configuration | [supabase/config.toml](../../supabase/config.toml), `[auth.email].otp_length` | Specifies eight digits, checked against the shared contract by tests. |
| OTP verification helper | [web/lib/email-otp.ts](../../web/lib/email-otp.ts) | Accepts exactly eight ASCII digits and forwards them unchanged. |
| Auth rendering input validation | [web/server/emails/auth-actions.tsx](../../web/server/emails/auth-actions.tsx) | Parsing and runtime rendering use the shared validator. Trusted template rendering accepts the exact token placeholder. |
| Shared layout code validation | [marketing/lib/email/account-layout.ts](../../marketing/lib/email/account-layout.ts) | Uses the generated shared validator; accepts exactly eight digits or the exact Auth token placeholder. |

The separate SMS `otp_length` entry is not the email drift. Phone notices are outside the pilot notice scope.

## Pilot security notices

Password-change and email-change notices are on. Phone-change notices are off. This matches repo intent, not a claim that staging and production are synchronized.

The local notice intent is recorded in [supabase/config.toml](../../supabase/config.toml) under `auth.email.notification.password_changed`, `auth.email.notification.email_changed`, and `auth.email.notification.phone_changed`. The notice renderer is [web/server/emails/security-notices.ts](../../web/server/emails/security-notices.ts).

## Local generation and future publication

Run from the repository root with installed web dependencies:

```bash
bun scripts/emails/render-staging-auth.ts --output temp/generated-auth-email
bun scripts/emails/render-staging-auth.ts --output temp/generated-auth-email --check
```

For a target with a 60-second email OTP expiry, use the same explicit value for generation and checking:

```bash
bun scripts/emails/render-staging-auth.ts --output temp/generated-auth-email --expiry-seconds 60
bun scripts/emails/render-staging-auth.ts --output temp/generated-auth-email --expiry-seconds 60 --check
```

`--expiry-seconds` accepts a positive safe integer in seconds and defaults to `3600`. It controls the expiry text in every action template. The chosen seconds must match the target environment's email OTP expiry. For local Auth, that setting is `[auth.email].otp_expiry` in `supabase/config.toml`. Generation does not change that setting. `--check` must use the same chosen seconds; checking with a different expiry fails.

Each generation command syncs the shared generated sources and writes each of the eight slots' `.html`, `.txt` and `.subject.txt` files. Each `--check` command checks both the shared sources and artifacts without rewriting them. Output uses Auth placeholders for site URL, token hash, token, email and old email, with `https://cuadrao.ai` as the explicit asset origin. It contains no environment-specific app origin or example recipient.

`manifest.json` says the artifacts are generated, records `expirySeconds`, lists their filenames, and maps each slot to its hosted subject and HTML field. The HTML itself has no added generated comment. The approved #1832 copy removes only the greeting and sign-off, so confirmation intentionally differs from #1831 and the previously published staging copy. Publication of this copy remains pending in #1833. Do not edit generated artifacts.

[scripts/emails/auth-hosted-settings.json](../../scripts/emails/auth-hosted-settings.json) owns the intended sender name, email rate limit and pilot notice flags. It contains values only. The shared OTP contract owns code length; the settings file does not duplicate it.

#1833 will publish the eight generated slots only after the required copy and visual review are complete:

1. Regenerate and run `--check` at the approved commit with `--expiry-seconds` matching the approved target email OTP expiry.
2. Use the manifest to publish each generated subject and HTML to its matching hosted slot in the explicitly approved environment.
3. Apply the sender, rate limit and notice flags from the versioned settings file, the email code length from the shared contract, and email OTP expiry matching the generated manifest.
4. Read back every slot's subject and HTML, sender, rate limit, notice flags, code length and `mailer_otp_exp`. Compare the exact values to the approved local artifacts and sources.
5. Record the environment, commit and comparison result without secrets. Keep the existing hook unchanged; its separate work is #1834.

No publication or hosted readback runs in #1832.

## Historical hosted drift inventory

The November 5 record identifies the following drift. This is historical inventory only. No hosted dashboard was inspected or changed for this document.

| Environment | Recorded drift |
| --- | --- |
| Staging | The signup template is miswired to email-change. |
| Production | Auth templates still carry Argus branding. |
| Staging compared with production | Notice settings and sender differ. |

The inventory contains no sender addresses, secrets, or environment values. It does not authorize a fix or replace a future explicit readback.

## Out of scope

- Touching the hosted dashboard or publishing hosted templates or settings.
- Removing the staging hook or building a new Auth hook to fix the look.
- Changing the Business Resend path.
- Retiring the access-approval email.
