# Prepare the Marketing production release

Lucas chose to launch without reminder or retention scheduling. Immediate confirmation email, welcome email after confirmation, and leave remain in scope. The existing staging scheduler stays on staging. This source preparation changes no hosted configuration, sends no mail, and makes no provider mutation. Lucas owns the setup steps and the later Manual Deploy. Production schema application still requires his explicit yes.

## Confirm the target

The October 16, 2026 read-only check found Render `cuadrao-web`, service `srv-d7ap6bmslomc73eqp8m0`, on branch `main` with root `marketing`. Auto-deploy is off. The verified domains are `cuadrao.ai` and `www.cuadrao.ai`. All ten required names below are missing, and the service has no linked environment groups. Refresh this metadata before any approved action.

Production Supabase is `lgdhvepyrzbnscqssgqq`. Staging is `skedzwocnmrhfigiwyzi`. Production lacks the waitlist table and both selected migration versions. Staging already has the table, confirmation RPCs, and its separate scheduler. A successful staging page GET does not prove production writes or email delivery.

Use [`.env.example`](.env.example) as the single copyable name inventory. It contains empty placeholders. Never commit values or paste service-role keys into browser code.

## Fill each variable from its owner

Prepare these four groups with the same names in each environment pair. Keep them UNLINKED until a deployment is authorized.

- `cuadrao-prod-shared` and `cuadrao-staging-shared` hold shared server credentials and the approved waitlist sender.
- `cuadrao-prod-web` and `cuadrao-staging-web` hold Marketing settings.

Each row below belongs to exactly one group. Production and staging use different project credentials, matching widget pairs, origins, and mail destinations. Do not add `PROD_` or `STAGING_` prefixes to runtime names.

| Required name | Production group | Staging group | Production value source and check | Staging value source |
| --- | --- | --- | --- | --- |
| `SUPABASE_URL` | `cuadrao-prod-shared` | `cuadrao-staging-shared` | Production project's API URL in Supabase, for `lgdhvepyrzbnscqssgqq`. | Staging project's API URL, for `skedzwocnmrhfigiwyzi`. |
| `SUPABASE_SERVICE_ROLE_KEY` | `cuadrao-prod-shared` | `cuadrao-staging-shared` | Matching production project's legacy service-role key. Server only. | Matching staging service-role key. |
| `RESEND_API_KEY` | `cuadrao-prod-shared` | `cuadrao-staging-shared` | Approved Resend production sending credential for the verified sender domain. | Approved staging sending credential. |
| `MARKETING_WAITLIST_FROM` | `cuadrao-prod-shared` | `cuadrao-staging-shared` | Approved sender `"Cuadrao" <no-responder@mail.cuadrao.ai>` on the verified `mail.cuadrao.ai` domain. | Same approved sender `"Cuadrao" <no-responder@mail.cuadrao.ai>`. |
| `MARKETING_POSTAL_ADDRESS` | `cuadrao-prod-web` | `cuadrao-staging-web` | The responsible operator address already locked in the legal and email-footer decision. Use that approved source. | Approved staging operator address. |
| `CUADRAO_WAITLIST_ORIGIN` | `cuadrao-prod-web` | `cuadrao-staging-web` | Existing canonical HTTPS origin `https://cuadrao.ai`. No path, query, credentials, or fragment. | Exact staging HTTPS origin. |
| `CUADRAO_WAITLIST_TURNSTILE_SECRET` | `cuadrao-prod-web` | `cuadrao-staging-web` | Secret from the production Marketing Turnstile widget described below. | Matching staging widget secret. |
| `CUADRAO_WAITLIST_TURNSTILE_SITE_KEY` | `cuadrao-prod-web` | `cuadrao-staging-web` | Public site key from that same production widget. The app serves it through `/api/signups/config`. | Public site key from that same staging widget. |
| `CUADRAO_INQUIRY_FROM` | `cuadrao-prod-web` | `cuadrao-staging-web` | Approved sender `"Cuadrao" <no-responder@mail.cuadrao.ai>`. This name explicitly belongs to web. | Same approved inquiry sender. |
| `CUADRAO_INQUIRY_TO` | `cuadrao-prod-web` | `cuadrao-staging-web` | Inbox Lucas confirms receives production Business inquiries. No default recipient exists. | Staging-only recipient. |

`MARKETING_WAITLIST_FROM` belongs to shared under Lucas's approved sender ownership. Its current consumer is Marketing; this placement does not claim that an API service reads it or authorize linking another service. `CUADRAO_INQUIRY_FROM` remains in web by Lucas's explicit assignment. No generic sender variable is invented.

Lucas approved `"Cuadrao" <no-responder@mail.cuadrao.ai>` for both sender settings in production and staging. The October 16 read-only Resend check found `mail.cuadrao.ai` verified with sending enabled. Waitlist validation accepts that exact mailbox with either `Cuadrao` or `"Cuadrao"` as the display name. Existing root `@cuadrao.ai` addresses remain compatible. Other subdomains and other mailboxes on `mail.cuadrao.ai` remain rejected. Waitlist mail keeps `Reply-To: hola@cuadrao.ai`. Business inquiries keep the visitor's address as Reply-To so the operator can answer the inquiry. This code change does not set hosted values, deploy, or send mail.

| Optional or operator name | Where it belongs | Production value source or reason to leave unset |
| --- | --- | --- |
| `CUADRAO_SITE_INDEXING` | `cuadrao-prod-web` and `cuadrao-staging-web` | Set `public` for the approved production launch. Any other value, including unset, keeps noindex and disallow-all robots. Staging stays private. |
| `CUADRAO_TRUSTED_CLIENT_IP_HEADER` | `cuadrao-prod-web` and `cuadrao-staging-web` | Set only after the actual trusted proxy chain is verified. Otherwise leave unset and retain the Render fallback. |
| `CUADRAO_SOCIAL_PREVIEW` | `cuadrao-prod-web` and `cuadrao-staging-web`, build time | Leave unset in production. Local design previews can show unlinked placeholder icons. |
| `RESEND_API_URL` | Local fixture only | Leave absent on hosted services. Runtime defaults to `https://api.resend.com`. Never send production credentials to a fixture URL. |
| `CUADRAO_NOTICE_FROM` | Manual operator shell only | Sender approved for a separate availability-notice operation. Provisioning does not authorize that operation. |
| `PORT`, `NODE_ENV` | Platform | Render and Next.js supply these framework inputs. Marketing source does not read them directly. Do not put them in the groups. |
| `CI` | CI platform | GitHub Actions supplies this for Playwright configuration. Do not put it in the groups. |
| `MARKETING_CAPTURE_URL` | Local capture scripts | Target of a local screenshot session. No production group value. |
| `MARKETING_E2E_MOCK_PORT`, `MARKETING_E2E_SITE_PORT`, `MARKETING_E2E_PUBLIC_PORT`, `MOCK_PROVIDER_PORT` | Local browser fixtures | Owned by the local test runner. No production group values. |
| `CUADRAO_WAITLIST_TEST_CONTAINER` | Local database test | Name of an owned disposable test container. Never point this at hosted production. |

`NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY` is a legacy service setting. The Marketing app does not read it. It cannot satisfy either required Marketing widget name.

## Prepare Render without starting a deploy

[Render's environment-variable guide](https://render.com/docs/configure-environment-variables) says that linking a group starts a new deployment. Auto-deploy off does not prevent this explicit action. The [group-link API](https://api-docs.render.com/reference/link-service-to-env-group) has no documented `deploy=false` option.

1. Lucas opens Render **Dashboard > Environment Groups > New Environment Group**. Enter `cuadrao-prod-shared`, add its four required keys from the table, and select **Create** without linking a service. Repeat for `cuadrao-prod-web`, `cuadrao-staging-shared`, and `cuadrao-staging-web` with their matching keys and environment-specific values. If project environment controls are available, use **Manage > Move group** to place each group in its matching production or staging environment. This PR performs none of those writes.
2. Compare group key names. Shared and web must have no duplicate key in the same environment. Never link a production group to staging or a staging group to production.
3. Audit service-level settings by key name. Render gives direct service values precedence over linked groups. Remove or replace an obsolete override only in an approved deployment window, after reviewing its effect.
4. Keep group linking held while the instruction remains "no deploy." Do not use **Link** as an environment-only save action.
5. If Lucas wants **Manual Deploy** to be the only launch action, Lucas opens **cuadrao-web > Environment > Add variables**, enters the same values, and selects **Save only**. Do not select **Save, rebuild, and deploy** or **Save, deploy**. Keep the prepared groups unlinked. Direct values are a temporary configuration until a later approved group-link deployment.
6. Read back only target service identity, key names, set/unset status, group links, and deploy metadata. Do not copy secret values into evidence. Confirm auto-deploy remains off and no new deployment has started.

A later group-link change requires its own approved deployment window. Audit duplicate direct keys before that window so an old direct secret cannot mask the group. The groups are a planned configuration, not evidence that this PR linked or populated them.

## Prepare the production Turnstile pair

Use Cloudflare's [dashboard widget guide](https://developers.cloudflare.com/turnstile/get-started/widget-management/dashboard/). Production widget permissions remain unverified. A previous management token returned HTTP 401, error 1000. Render's verified domains do not establish Cloudflare widget permission.

1. Lucas opens Cloudflare **Turnstile**, then **Add widget**, or opens the existing Marketing widget's **Settings**.
2. Name the widget for production Marketing. Add `cuadrao.ai` and `www.cuadrao.ai`. Do not use a staging widget as the production pair.
3. Select **Non-Interactive** mode. Leave pre-clearance off, with `no_clearance`.
4. Select **Create**, or **Save** for the existing widget.
5. Put its site key in `CUADRAO_WAITLIST_TURNSTILE_SITE_KEY` and its matching secret in `CUADRAO_WAITLIST_TURNSTILE_SECRET`. Use the Render save-only procedure above while deployment is held.
6. Read back allowed hostnames, mode, and pre-clearance status without displaying the secret. After the release, verify browser requests use action `personal_waitlist` and that the server sees the selected canonical hostname.

## Approve the exact schema-forward packet

This is a plan for Lucas's explicit yes before production application. It contains no executable apply script. Do not use a repository-wide database push, `--include-all`, migration repair, or history rewrite. Production history differs from main beyond this waitlist work. An October 16 read-only census found 81 production versions and 82 main files, with 12 legacy production-only versions and 13 repository-only versions. Refresh the actual version sets before application. Counts alone do not prove compatibility.

The only proposed SQL inputs, in this order, are unchanged files already on main.

| Order | Original file | SHA-256 |
| --- | --- | --- |
| 1 | `supabase/migrations/20260920000000_cuadrao_early_access_signups.sql` | `ea2a2a010d31f1c05222561d5f90fa024df2fac46a466107c7bdf3138d11aad0` |
| 2 | `supabase/migrations/20261017010000_personal_waitlist_confirmation.sql` | `84c2f097f3b6cd518762d6479aef649d1f572a4287ca8d4a3c0fcd623e35861b` |

The first file needs standard Supabase roles `anon`, `authenticated`, and `service_role`, plus the standard PostgreSQL digest functions used by the table. Production was read back as PostgreSQL 17.6. The table's digest uses PostgreSQL `sha256`, `convert_to`, and `encode`. The second file needs that table and its eight original columns. It has transaction-local timeouts. Neither file needs pg_cron, pg_net, Vault, or an Edge Function. The app supplies each random verification id.

Explicitly exclude `20261017020000_waitlist_supabase_scheduling.sql`, the `waitlist-reminders` Edge deployment, all scheduler configuration and secrets, and every unrelated migration. Leave every applied SQL file unchanged. The second selected file defines reminder and purge RPCs but does not call them, schedule them, or send mail.

The separately approved application procedure must do the following.

1. Pin the exact reviewed main commit and recheck both hashes. Refresh production project identity, table/function absence, grants, and original-version absence. Stop on an unexpected pre-existing object, version, or schema/history disagreement.
2. Prepare a reviewed, narrow transaction that submits only these two unchanged file bodies in order and records their original migration versions in `supabase_migrations.schema_migrations` through the approved history owner. Include the exact history-write method in the packet before Lucas's production-application yes. Do not silently assign new versions, omit history, or repair unrelated history.
3. Obtain Lucas's explicit yes for production project `lgdhvepyrzbnscqssgqq`, both hashes, both original versions, the narrow transaction, and its history writes. Neither PR approval nor a source merge is that yes.
4. Apply only the approved transaction with an authorized database owner. Roll back the transaction if any statement or history write fails. Stop on uncertainty. Do not retry by broadening the migration scope.
5. Read back the objects and grants listed below through catalog metadata. Do not invoke the six RPCs, insert a signup, or send mail as a schema check. Record exact source commit, hashes, project, two versions, and pass/fail results without credentials or row contents.

No production apply runner is created here. Existing history must be understood before the later transaction is built and reviewed.

## Read back the schema without writing user data

After an authorized application, expect `public.cuadrao_early_access_signups` with exactly these 15 columns.

`email_digest`, `email`, `language`, `consent_version`, `source`, `created_at`, `notified_at`, `removed_at`, `expense_method`, `wish`, `confirmed_at`, `privacy_policy_version`, `last_confirmation_sent_at`, `reminder_sent_at`, and `verification_id`.

Expect the email digest primary key, original email/language/consent/source checks, the active-email and digest checks, and six named `cuadrao_waitlist_*` constraints for expense method, wish length, verification id, privacy version, confirmation order, and verification uniqueness. RLS remains enabled with no public policy. `PUBLIC`, `anon`, and `authenticated` have no table access. `service_role` has SELECT, INSERT, UPDATE, and DELETE after the second file. DELETE is needed by leave and later purge, although purge remains unscheduled.

Expect these six `SECURITY INVOKER` functions with empty search paths and EXECUTE only for `service_role` apart from owner authority.

- `cuadrao_waitlist_register(text,text,text,text,text)`.
- `cuadrao_waitlist_confirm(text,timestamptz)`.
- `cuadrao_waitlist_release(text,timestamptz,boolean)`.
- `cuadrao_waitlist_leave(text)`.
- `cuadrao_waitlist_reminders(integer)`.
- `cuadrao_waitlist_purge(integer)`.

Catalog SELECT checks can inspect `information_schema.columns`, `pg_class.relrowsecurity`, `pg_constraint`, `pg_policies`, `information_schema.role_table_grants`, `pg_proc.prosecdef`, `pg_proc.proconfig`, and `pg_proc.proacl`. Check effective privileges as well as listed grants, including the PUBLIC default. Check `supabase_migrations.schema_migrations` for original versions `20260920000000` and `20261017010000`. It must not gain version `20261017020000` from this release. Production must not gain waitlist cron jobs, scheduler functions, Edge configuration, or Vault secrets.

## Keep scheduling as a follow-up

Immediate signup reserves and sends confirmation mail through the existing request path. Confirmation can send the welcome mail. Leave deletes the person's complete current waitlist row. Those paths use the first two migrations and the ten required settings, without a scheduler.

Without scheduling, the 24-hour reminder is not automatic. Unconfirmed rows are not automatically purged after seven days, and confirmed rows are not automatically purged after twelve months. Existing register and confirm age checks still apply, but they do not delete rows. Leave remains immediate. This is the retention delay Lucas accepted for this launch, pending a separate follow-up. Track the production retention owner and deadline before the first records reach their deletion age. Do not change website or email copy in this preparation PR.

Do not run `scripts/waitlist-maintenance.ts` as a substitute. It both purges and sends reminders. A future scheduling proposal must separately cover production project guards, authorization, retention timing, provider calls, operational readback, and Lucas's approval. Existing staging behavior stays unchanged.

## Verify the source guard and release boundary

From `marketing`, run `bun run check:env`, `bun test __tests__/env-example.test.ts`, `bun run typecheck`, and `bun run lint`. Marketing CI runs the guard before the normal unit/build/browser checks. The guard uses the existing TypeScript compiler API with no added package.

The guard scans authored TypeScript and JavaScript throughout Marketing, including app code, library wrappers, operator scripts, build configuration, and Playwright configuration. It follows `process.env`, process aliases, literal CommonJS process imports, global process access, imported Node env aliases, variable aliases, default parameters, and parameters reached through local calls. It records literal dot/bracket and destructured names. It fails on dynamic keys, environment spreads/rest, unresolved object escapes, or external object consumers instead of silently dropping them. Keep environment reads static if the code needs a new shape.

Only test/fixture paths `__tests__`, `e2e`, and files named `*.test.*` or `*.spec.*` are excluded from the authored-source inventory. Generated/dependency directories `.next`, `node_modules`, `.git`, `playwright-report`, and `test-results`, and declaration files are also excluded. Test-only knobs are still listed in the example, but they never belong on the production service. Framework internals and languages other than JavaScript/TypeScript are outside this guard.

Source checks prove the example covers authored environment reads. They do not prove hosted configuration, delivery, or production acceptance. Lucas completes the environment and widget setup, gives the explicit schema-application yes, and checks the read-only results before his Manual Deploy. Set production indexing to `public` for that launch and leave staging private. Retain auto-deploy off. A code revert leaves hosted schema and collected rows intact, so any database rollback needs a separate data-preserving plan.
