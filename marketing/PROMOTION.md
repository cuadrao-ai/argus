# Marketing promotion

This PR copies the accepted marketing app to main. Lucas confirmed the footer on his physical iPhone and authorized this source promotion. Merge does not authorize deployment, migrations, provider calls, or public-form activation.

## Source and scope

- Main base: `a9286b21886eb03df7a21f2f4b7d5e79af570679`.
- Integration source: `02502122aae107bc71ff123c7fb8060dc88f93ab`.
- The 188 selected marketing files include the app, assets, legal source, ES/EN forms, tests, operator scripts, and package lock. Nineteen historical files under `marketing/evidence/` are omitted. No source reads those omitted files.
- Marketing runtime, assets, tests, and configuration retain their exact integration bytes. README links use the pinned integration source because the linked owner documents are outside this promotion.
- No Business application menu, Consumer application, Argus backend, or unrelated integration change is included.

The source shape remains one independent Next.js package with its own Bun lockfile. Its build has no import from outside `marketing/`. The scheduler unit test imports the reminder handler below. The handler imports the shared marketing email renderer.

## Required companion files

| Path | Reason |
| --- | --- |
| `supabase/migrations/20260920000000_cuadrao_early_access_signups.sql` | Signup table, constraints, and service-role grants. |
| `supabase/migrations/20261017010000_personal_waitlist_confirmation.sql` | Confirmation fields and six waitlist RPCs, including complete removal and retention. |
| `supabase/migrations/20261017020000_waitlist_supabase_scheduling.sql` | Existing staging-only cron companion. Its staging guard is unchanged. |
| `supabase/functions/waitlist-reminders/{handler.ts,index.ts,deno.json,README.md}` | Existing staging-only handler, entrypoint, build configuration, and operating guide. |
| `supabase/config.toml` | Only the JWT-enabled reminder function stanza differs from main. |
| `supabase/tests/waitlist-scheduler.sql` | Scheduler privilege, configuration, and queue verification. |
| `tests/test_cuadrao_early_access_postgres.py` | Focused table and grant checks, included by main's existing local-Postgres CI glob. |
| `.github/workflows/marketing.yml` | Independent package lint, typecheck, unit, build, and browser checks. Main has no marketing check. |

The first two migrations depend only on normal Supabase roles and the signup table. The scheduler also needs pg_cron, pg_net, and Vault. The repository files do not apply themselves to a hosted database.

## Verification

Local lint, typecheck, production build, and modularity checks pass. The unit command reports 213 passes and four database-dependent skips. Those four tests then pass against a separate owned, network-isolated PostgreSQL container. The three selected migrations and scheduler replay pass. The 29 waitlist SQL assertions pass.

The final scheduler SQL queue check could not complete because the disposable container has no Vault server key. Automatic approval review rejected reading the image's key bootstrap script. No workaround, credential read, or hosted call followed. Fixture scheduler tests pass, but this run does not claim complete local scheduler acceptance.

The first sandboxed unit attempt could not bind its localhost fixture server. The same command passed with local socket permission. Local tools are Node 26.10.0 and Bun 1.4.2. CI pins the accepted Node 24.21.0 and Bun 1.3.14 versions.

The full browser suite passes 309 checks with one existing touch-only skip. All six legal source comparisons pass. Terminal CI is recorded in the PR. All browser provider requests use the existing local recorder and CAPTCHA fixtures. No real email is sent. The exact runtime matches the integration source whose footer Lucas accepted. No new physical-device acceptance is claimed by the local browser run.

## Main automation

The existing main-push CI only builds, tests, and resets a disposable local Supabase instance. It contains no hosted migration or deployment action. The existing canary is scheduled or manually dispatched, not triggered by a main merge. This PR leaves those workflows unchanged. The new marketing workflow has read-only repository permission, uses no repository secrets, and contains no deploy command.

## FOR LUCAS before Manual Deploy

The coordinator checked production read-only on October 16, 2026. Render `cuadrao-web` uses root `marketing`, branch `main`, and auto-deploy off. Its `cuadrao.ai` and `www.cuadrao.ai` domains are verified. There are no linked environment groups.

Production has no signup table, waitlist columns, six public RPCs, three scheduler functions, or record of the three migration versions above. Staging has the table with 15 columns and all those functions and migration versions. The first two schema migrations and required settings are deployment prerequisites. Scheduler objects and the third migration are excluded from this production launch under Lucas's later decision below. Their absence does not block source merge or this launch.

Before Lucas's Manual Deploy:

1. Provision the production waitlist schema through an approved forward release.
2. Supply these ten missing production settings: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `MARKETING_WAITLIST_FROM`, `MARKETING_POSTAL_ADDRESS`, `CUADRAO_WAITLIST_ORIGIN`, `CUADRAO_WAITLIST_TURNSTILE_SECRET`, `CUADRAO_WAITLIST_TURNSTILE_SITE_KEY`, `CUADRAO_INQUIRY_FROM`, and `CUADRAO_INQUIRY_TO`. Confirm the production sender and HTTPS origin. The canonical [environment example](.env.example) now lists every authored runtime read and separates shared, web, local, and platform names. Follow the [production checklist](PRODUCTION_CHECKLIST.md) for value sources and the exact two-file schema proposal. Applying the selected SQL files to production still needs Lucas's explicit yes.
3. Launch without reminder or retention scheduling, as Lucas decided for this release. Keep `20261017020000_waitlist_supabase_scheduling.sql` and the existing reminder Edge handler out of production. They are staging-only. Immediate confirmation, welcome, and leave still use the first two unchanged migrations. Automatic reminders and age-based deletion are deferred to a separate follow-up. The approved `"Cuadrao" <no-responder@mail.cuadrao.ai>` sender is accepted in production and staging.
4. Verify that the production Turnstile widget permits the live domains and configure its matching key pair. Widget domain authorization remains unverified because the existing management token returned HTTP 401, error 1000. Render domain verification does not prove widget permission. The existing `NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY` is not read by this app.

No production settings, schema, scheduler, provider, domain, or deployment changed during this promotion. Reverting the eventual promotion commit removes these source additions and restores the prior Supabase config. A code revert does not change hosted data.

## Environment and schema preparation follow-up

The [production checklist](PRODUCTION_CHECKLIST.md) supersedes the former scheduling launch prerequisite. It proposes only the unchanged signup and confirmation migrations, records their hashes and expected objects, and keeps the staging scheduler excluded. Production history has unrelated differences, so no blanket database push, include-all, or migration repair is permitted. No executable apply runner is added.

Prepare shared and web groups with matching variable names for production and staging, but leave them unlinked while deployment is held. Render group linking starts a deployment even with auto-deploy off. Lucas's environment-only setup can use direct service values with **Save only**, followed by metadata readback. Lucas approved `"Cuadrao" <no-responder@mail.cuadrao.ai>` for `MARKETING_WAITLIST_FROM` and `CUADRAO_INQUIRY_FROM` in production and staging. The waitlist validator accepts this exact mailbox on the verified sending domain. Hosted configuration and deployment remain separate actions.
