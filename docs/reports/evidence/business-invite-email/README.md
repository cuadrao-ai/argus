# Business invite email

The owner can create an invite or explicitly resend one. An invite lasts seven days. Expired invites stay visible. Their server state is `expired`; sign-in grants no access. An explicit resend creates a new seven-day window and an access-ledger receipt. Existing confirmed accounts retain the existing direct read-and-prepare grant behavior.

The email uses the shared account layout. TypeScript owns the copy and HTML. `bun scripts/emails/sync-business-invite.ts --check` verifies the adjacent generated JSON. Python substitutes escaped values once. A built wheel includes that JSON. The link opens the configured ordinary app origin, with no Supabase invitation or acceptance token. The expiry date uses America/Santo_Domingo.

The shared SMTP sender is `Cuadrao <no-responder@mail.cuadrao.ai>` and Reply-To is `hola@cuadrao.ai`. Provider acceptance is reported as `accepted`; this does not prove receipt. A configured failure returns `failed`, logs only the invite ID and error class, preserves the invite and leaves the owner in control of resend. A replay, list or sign-in never sends an email automatically. The UI reuses the existing approved generic failure text. The only new UI wording is the approved Spanish expiry sentence and `Reenviar`. Locale catalogs remain unchanged. Explicit Spanish fallbacks account for the app's empty-string missing-key handler.

## Activation and ownership

Delivery reads the existing `CUADRAO_APP_ORIGIN`, with legacy `ARGUS_APP_ORIGIN` fallback, through `setting_value`. It also requires `CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED=true`. The example and staging declaration leave the flag `false`. An enabled local test exercises the real router, renderer and shared transport with mocked provider delivery. No environment file, hosted setting, provider credential, real email or paid call changed.

Shared layout dependency is PR #1226, frozen at `d8299d635a8a9eef261118a5f7f9c90dfbd1adfa`. Its dependency commits remain separate from invite work. Transfer and close methods are excluded from this lane. The only shared SMTP change is the separately approved sender correction.

The fetched integration base and final integration refresh are both `651870a54be4e5506dbb38f3902fef1a97eef8df`. No reconciliation merge was needed. Integration did not advance; retained evidence therefore has no new integration overlap. The transfer writer owns separate methods in the shared access store and router. Root must reconcile that overlap before landing.

## Migration

`20261018040438_business_invite_seven_day_expiry.sql` reuses the existing non-null expiry column. It sets the seven-day insert default and shortens only unaccepted, unrevoked pending rows to the earlier of their current expiry and creation plus seven days. It never extends old invites. Old pending invites can become expired. Accepted and revoked invitation history and all membership grants stay unchanged. The transaction uses a five-second lock timeout and a sixty-second statement timeout. Applied migrations were not edited.

The migration and access tests used only `cuadrao_invite_email_20261018`, copied from the named local baseline's schema. Baseline database `postgres` retained its 145 migration records. The isolated copy excluded baseline-only `pg_cron` and `cron`; schema restore used the local administrative owner because Supabase extension functions require that role. Tests included `SET ROLE authenticated` read refusal. This is focused application-schema proof, not a complete Supabase platform clone or hosted acceptance.

## Verification

- 94 hermetic Python checks passed, including the API, MIME transport, missing credentials, seven-day boundary, injection, nonrecursive substitution, and OpenAPI compatibility.
- 9 actual Postgres checks passed, including migration preservation, confirmed-email acceptance, owner-only resend, revoked and cross-owner refusal, and expiry after waiting on the access lock.
- 6 Bun checks passed for the owner list, expired line, explicit resend callback, disabled repeat clicks, and HTML/plain snapshots.
- 2 Chromium flows passed at 1280 and 390 pixels using offline sample data. Each creates an invite, verifies its email remains visible, explicitly resends, and cancels it. Committed screenshots show both widths. These browser flows prove the UI, not a hosted API or email delivery.
- Runtime TypeScript compilation passed with tests excluded. The full repository TypeScript command fails on inherited `bun:test` declarations and unrelated existing test types. No runtime files from this lane produced errors.
- Generated invite and close artifacts, Ruff, ownership, whitespace and modularity checks passed. No modularity budget increased.

The phone-width browser check found that a second action hid the invite's address. The invite-only row now places the buttons below its address on narrow screens. The final screenshot shows the address and both controls.

## Remaining gates

This is a draft, unmerged build. Independent root review, exact-head CI, receipt gate 3, the fresh root-owned evaluation, migration promotion, runtime activation and actual email acceptance remain separate gates. No merge, deploy or hosted migration is authorized by these results.
