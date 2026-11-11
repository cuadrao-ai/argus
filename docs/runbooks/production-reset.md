# Reset production and apply the baseline

Status: NOT APPROVED. This PR changes nothing hosted. Lucas performs the
Dashboard steps only after approving the maintenance window. Cuadrao engineering is the operator for the apply commands. Engineering fills
and commits the approval draft after Lucas's go. Lucas runs the numbered Dashboard steps. The SQL is destructive.

Use the same project, `lgdhvepyrzbnscqssgqq`. Do not create a new project, rotate
keys, or change URLs. This procedure assumes old test data only. It cannot undo
a committed reset. Keep services suspended if any step fails.

## 1. Confirm the project

1. Open the production project in the Dashboard.
2. Check that the address contains `/project/lgdhvepyrzbnscqssgqq/`.

Stop if the ref differs or the data may belong to real users. Tell us the ref
and the concern, without passwords, keys, or row contents.

## 2. Suspend writers

1. In Render, open **cuadrao-api**.
2. Open **Settings**.
3. At the bottom, click **Suspend Web Service**.
4. Confirm suspension.
5. Wait until the service says **Suspended**.
6. Open **cuadrao-documents-worker**.
7. Open **Settings**.
8. At the bottom, click **Suspend Background Worker**.
9. Confirm suspension.
10. Wait until the worker says **Suspended**.
11. Open **cuadrao-app**, the production web app.
12. Open **Settings**.
13. At the bottom, click **Suspend Web Service**.
14. Confirm suspension.
15. Wait until the app says **Suspended**.

The API, worker, and app must not recreate data while the database is empty.
Existing clients, direct Auth requests, other workers, scheduled jobs, and
webhooks must also be quiet throughout the window. Suspending the API alone
does not block direct Auth or Storage calls. Confirm that the no-real-users
premise covers those clients before proceeding.

Stop if a service name or button differs, a service will not suspend, or another
writer is active. Tell us which service or writer remains. Do not deploy,
resume, or change keys to work around it. These Dashboard clicks have not been
checked through a signed-in browser in this local-only task.

## 3. Run the inventory

1. Return to the confirmed project.
2. Open **SQL Editor**.
3. Click **New query**.
4. Select the **postgres** role and the primary database.
5. Paste the complete file `scripts/ops/production_reset/inventory.sql`.
6. Click **Run**.
7. Compare the result sets with the expectations below.

The database must be `postgres`. User and row counts may be nonzero, but every
row must be known test data. The two normal buckets are
`financial-document-sources` and `profile-images`. The old migration ledger can
differ from the local 207-row history. The reset deletes its old rows rather
than pretending that those migrations ran after the reset. Cron job count must
be zero. Extensions in `public`, including `vector`, remain through reset.
The approved baseline drop migration explicitly removes the old app-installed
`pg_cron` and `pg_net`. The reset itself preserves all extensions.

Review every app relation, routine, extension, bucket, and trigger in the
inventory. The trigger result lists every trigger that deletion can reach.
The `reset_action` column separates drops from retained platform triggers.
Only app-table triggers and the auth exceptions below may be removed. Any other
platform-table dependency blocks the entire reset.
The six allowed app-created triggers on `auth.users` are below. Their matching
zero-argument handlers may be in `public` or `argus_private`; the baseline uses
`argus_private`. No other trigger name or handler is allowed by this exception.

| Trigger | Handler in `argus_private` |
| --- | --- |
| `bind_guest_signup_handoff` | `bind_guest_signup_handoff()` |
| `business_auth_retention_guard` | `business_auth_retention_guard()` |
| `business_fiscal_actor_retained` | `business_fiscal_actor_retained()` |
| `business_invitation_auth_retention` | `business_invitation_auth_retention()` |
| `finalize_linked_guest_identity` | `finalize_linked_guest_identity()` |
| `refuse_placeholder_email` | `refuse_placeholder_email()` |

The reset also removes triggers attached to deleted app tables and the
PostgreSQL internal triggers belonging to app foreign keys. The inventory
names every one, its table, and its constraint. Internal names contain local
object IDs, so their numeric suffixes differ between databases. The complete
local list is part of this runbook in the [trigger appendix](../reports/evidence/production-reset/triggers.md).
For production, retain the full trigger result from this step alongside the
approval. An unexpected trigger on `auth.users` is a stop condition. The reset
never changes auth table columns, platform triggers, or platform functions.
It also removes the app event trigger `ensure_rls`, backed by
`public.rls_auto_enable()`. The baseline recreates these app definitions.

Stop if anything is unexpected, any count query fails, or cron jobs remain.
Tell us the object names, counts, and error text only. Do not paste row data,
function bodies, migration statements, job commands, or credentials.

## 4. Empty and delete every inventoried bucket

For each bucket listed by the inventory:

1. Open **Storage**.
2. Open the bucket's **⋮** menu.
3. Click **Empty bucket**.
4. Confirm the bucket name if asked.
5. Wait until emptying finishes and the bucket shows no objects.
6. Open the bucket's **⋮** menu again.
7. Click **Delete bucket**.
8. Confirm deletion.

Delete each bucket after emptying it. Emptying alone is insufficient: the
baseline inserts both bucket configurations without an upsert. It recreates
`financial-document-sources` and `profile-images`, their private access setting,
file-size limits, and MIME types. It recreates no uploaded files. Other legacy
buckets are not recreated.

Stop if the menu differs, emptying is still queued, a bucket exceeds 200,000
objects, or either operation fails. Tell us the bucket name, count, and error.
Never delete Storage rows with SQL. SQL can leave backing files orphaned.
See [supported file deletion](https://supabase.com/docs/guides/storage/management/delete-objects)
and [bucket operations](https://supabase.com/docs/reference/self-hosting-storage/update-properties-of-a-bucket).

## 5. Run the reset

1. In **SQL Editor**, open a new query as **postgres**.
2. Paste and run this project marker statement after rechecking the Dashboard address:

   ```sql
   begin;
   create table public.cuadrao_reset_marker (project_ref text not null);
   insert into public.cuadrao_reset_marker values ('lgdhvepyrzbnscqssgqq');
   commit;
   ```

   This is Lucas's database-side confirmation of the address, not automatic
   project discovery. The reset reads this app-owned table directly, so it
   does not depend on SQL Editor reusing a connection. The marker is consumed
   by a successful reset. The database name alone cannot identify the project.

3. Open a new query as **postgres**.
4. Paste the complete file `scripts/ops/production_reset/reset.sql`.
5. Click **Run** once.
6. Check that the query completes without an error.

The reset uses one transaction. It retains the `public` schema shell and its
extensions, removes app objects in `public` and `argus_private`, deletes users
through auth's own cascades, and recreates the empty migration ledger as
`postgres`. The public schema has its default owner and role grants. A drop
guard rejects protected dependencies. There is no broad schema CASCADE.

Stop on any error. Send us the error and whether SQL Editor reported a commit.
Do not remove the guard, add CASCADE, run fragments, or repeat the reset. A lost
connection can leave the outcome uncertain; we first read back the ledger,
marker, auth count, and app objects. A successful reset has an empty ledger,
zero users, no private app schema, and no marker.

## 6. Hand off for baseline apply

1. Tell us the reset finished and keep all writers suspended.

Stop if the reset result is uncertain. Send the error before any apply.

The operator now fills and commits
`docs/release-manifests/2026-11-10-production-baseline-apply.json` after Lucas's
explicit go. Set `candidate_sha` to the reviewed merged commit, `approved_by`
to `founder`, a real approval reference, and issue/expiry times no more than
three days apart. The draft's placeholder SHA and times cannot pass validation.
The versions file contains both `20261110160000` and `20261110160100`.
Both run and both are recorded. Do not use `--record-only`.

Engineering runs this dry run from the merged tree, with the approved
production connection in `ARGUS_APPLY_DATABASE_URL`. Credentials and the CA
bundle stay outside the repo. `M` and `<ca-bundle>` are filled by the operator.
The direct host and pooler are recorded in the existing production manifest;
confirm the selected connection still identifies the approved project.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha M \
  --approved-file docs/release-manifests/2026-11-10-production-baseline-versions.json \
  --allow-host db.lgdhvepyrzbnscqssgqq.supabase.co \
  --allow-host aws-1-us-east-2.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-11-10-production-baseline-apply.json \
  --ssl-root-cert <ca-bundle>
```

Without `--execute`, the tool performs only a dry run.

Expect exactly `RECORD 20261110160000 cuadrao_baseline` and
`RECORD 20261110160100 drop_unowned_objects`. Stop if the dry run differs,
permission fails, or the approval does not match. Send the error and planned
versions only. No hosted command was executed for this PR.

After checking the dry run, engineering runs the full apply command:

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha M \
  --approved-file docs/release-manifests/2026-11-10-production-baseline-versions.json \
  --allow-host db.lgdhvepyrzbnscqssgqq.supabase.co \
  --allow-host aws-1-us-east-2.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-11-10-production-baseline-apply.json \
  --ssl-root-cert <ca-bundle> \
  --hosted-confirm production-apply-1789-baseline --execute
```

Each migration commits with its ledger row. If execution fails or the connection
is lost, keep services suspended and read back before retrying. Do not clear the
ledger again. A committed first version can remain if the second one fails.

## 7. Verify the result

1. After the operator confirms apply, open a new **SQL Editor** query as **postgres**.
2. Paste the complete file `scripts/ops/production_reset/verify.sql`.
3. Click **Run**.
4. Send us the complete verification output.

Expect both ledger versions, all expected RLS tables enabled, 134 public
policies, 63 non-extension public functions, 99 private functions, zero auth
users, zero Storage objects, and no `pg_cron` or `pg_net`. The two recreated
buckets are empty. Verification is read-only and raises an error on mismatch.

Stop if any check fails or a user/object reappears. Send the check name and
counts, and keep services suspended.

## 8. Wait for the deploy step

1. Leave the API, worker, and app suspended until the separately approved deploy.

This runbook does not authorize deployment or resumption. The operator still
needs production readback and the deployment checks before Lucas resumes use.

## Local proof

The [evidence](../reports/evidence/production-reset/README.md) records full
archived history, synthetic users and uploads, refusal controls, the reset,
the apply-tool dry run and apply, schema comparison, the production gate, and
the Postgres/RLS suite. Local proof does not establish current hosted state or
hosted-role permissions. The project address, service state, complete production
inventory, Storage deletion, approval, hosted apply, and deploy remain manual.
