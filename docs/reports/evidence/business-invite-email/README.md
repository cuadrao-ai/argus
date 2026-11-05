# Business invite email

The owner can create an invite or explicitly resend one. An invite lasts seven days. Expired invites stay visible. Their server state is `expired`; sign-in grants no access. An explicit resend creates a new seven-day window and an access-ledger receipt. Existing confirmed accounts retain the existing direct read-and-prepare grant behavior.

The email uses the shared account layout. TypeScript owns the copy and HTML. `bun scripts/emails/sync-business-invite.ts --check` verifies the adjacent generated JSON. Python substitutes escaped values once. A built wheel includes that JSON. The link opens the configured ordinary app origin, with no Supabase invitation or acceptance token. The expiry date uses America/Santo_Domingo.

The shared SMTP sender is `Cuadrao <no-responder@mail.cuadrao.ai>` and Reply-To is `hola@cuadrao.ai`. Provider acceptance is reported as `accepted`; this does not prove receipt. A configured failure returns `failed`, logs only the invite ID and error class, preserves the invite and leaves the owner in control of resend. A replay, list or sign-in never sends an email automatically. The UI reuses the existing approved generic failure text. The only new UI wording is the approved Spanish expiry sentence and `Reenviar`. Locale catalogs remain unchanged. Explicit Spanish fallbacks account for the app's empty-string missing-key handler.

## Activation and ownership

Delivery reads the existing `CUADRAO_APP_ORIGIN`, with legacy `ARGUS_APP_ORIGIN` fallback, through `setting_value`. It also requires `CUADRAO_BUSINESS_INVITE_EMAIL_ENABLED=true` and the existing `MARKETING_POSTAL_ADDRESS`. The renderer refuses a missing, company-only or multiline postal address. That failure leaves the invite saved and reports `failed`; an explicit resend after configuration recovery can deliver. Account mail includes the configured legal address and no unsubscribe link. The example and staging declaration leave the flag `false`. An enabled local test exercises the real router, renderer and shared transport with mocked provider delivery. No environment file, hosted setting, provider credential, real email or paid call changed.

Shared layout dependency is PR #1226, reconciled through `c95e3e248f733861b218a62f515509cb0ebdf1a4`. Its dependency commits remain separate from invite work. Transfer and close methods are excluded from this lane. The only shared SMTP change is the separately approved sender correction.

The fetched integration base and final integration refresh are both `651870a54be4e5506dbb38f3902fef1a97eef8df`. No reconciliation merge was needed. Integration did not advance; retained evidence therefore has no new integration overlap. The transfer writer owns separate methods in the shared access store and router. Root must reconcile that overlap before landing. The mandatory combined-tree acceptance plan below records the exact seams.

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

The PR is unmerged. It is marked ready only to run full CI after final reconciliation. Independent root review, exact-head CI, receipt gate 3, the fresh root-owned evaluation, migration promotion, runtime activation and actual email acceptance remain separate gates. No merge, deploy or hosted migration is authorized by these results.


## Final shared-template reconciliation

The invite retains the original delivery and sender commits. Exact shared dependencies were imported without rebasing or editing their runtime files. `eba4e8506` maps to `f489bf46b`, `3724de837` to `493180cdc`, and `95bd30349` to `c6c963971`. Final signed-time retry tests `18755fe31` map to `0f4cb6862` and fix `c95e3e248` maps to `87168b599`. Both branch ownership entries remain present. Imported dependency paths are registered under this branch for CI.

The invite generator now carries `Cuadrao LLC, __CUADRAO_POSTAL_ADDRESS__` as a complete legal-line token. Python resolves the configured legal line and performs one escaped substitution pass. A configured company prefix is not duplicated. Token-looking content stays literal. Subject, preheader, seven-day semantics, sender, Reply-To and both locale catalogs are unchanged.

Fresh final checks pass. There are 102 hermetic Python tests and 62 Bun shared/auth/invite tests, including the signed retry regression. Runtime TypeScript, generated invite/close freshness, Ruff, ownership, whitespace and modularity pass. An installed Poetry-core runtime built a wheel whose invite JSON matches the source bytes. Backend tests use the approved read-only Python 3.10.20 environment at `/private/tmp/cuadrao-lane6c-parsers-deps/.venv/bin/python3.10` with `env -i`, synthetic settings and dotenv disabled. No shared runtime was changed.

`invite-postal-light-390.png` and `invite-postal-dark-390.png` are actual local Chromium renders of the generated invite snapshot at 390 pixels. Both show the full legal address and ordinary sign-in link. The preview substituted local wordmark asset paths only, so it made no network or API calls. The screenshots are email rendering proof, not inbox-client or hosted delivery proof. Existing owner-panel browser and nine PostgreSQL checks remain retained evidence for their unchanged paths. This pass did not create a database or rerun unaffected expiry migrations.

## Mandatory combined-tree acceptance with transfer

PR #1222 at `3bb6d448badf19dac8e5971f011cd0dbba3bec9a` changes existing access methods from creator identity to current owner identity. Its successor does not edit invite methods. No transfer branch was imported into this invite branch. Root must serialize the resulting merge and verify these exact seams before customer readiness.

1. In the new resend route, select `context.scope.acting_person_id` like the transfer-aware adjacent give/revoke routes. Preserve the transfer branch's current-owner `_owned` check and open-space refusal in the shared store. Do not restore `created_by` as owner authority when resolving the access-file merge.
2. Create an open Business owned by A, with a pending expired invite for C. Complete the approved transfer to B while A retains only the existing Editar grant. With mocked email transport and configured legal address, B's explicit resend must return 200, renew to seven days, record B as actor/issuer under the combined contract, and deliver once. A's same resend must be denied, preserve the saved expiry and emit no mail. C's sign-in must never restore an old owner's authority.
3. Repeat refusal after closure and for a revoked or accepted invite. Confirm only the current owner can act, and accepted access history stays intact. Run the resulting probe on a disposable database and the actual combined router. This plan is pending, not passing evidence.
4. Transfer adds only the optional `transferId` prop and entry in `BusinessApp`; this invite branch changes its separate access panel. Preserve both. Shared transfer slot removal and snapshots remain the transfer owner's changes.

Root owns the fresh independent evaluation on the final invite head, terminal exact-head CI readback, combined-tree acceptance, receipt gate 3, migration promotion and actual delivery/activation. Merge stays held. The Prove It Works principle required fresh tests and actual footer renders for this delta rather than adopting the older review counts.
