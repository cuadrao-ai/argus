# Apply one staging migration: business due date

Apply `20261020120000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-20-staging-business-due-on-apply.json`. Its id is `staging-apply-2026-10-20-b`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261020120000` (`20261020120000_business_due_on.sql`): keeps each revision's before and after due date when a person sets a record's due date in review (#1335).

This record covers exactly this version. It runs after record `staging-apply-2026-10-20-a` has applied.

## Effects to expect

`20261020120000` adds nullable `before_due_on` and `after_due_on` date columns to `public.business_draft_revisions`. Existing rows keep both null and are not rewritten. It enables row level security on the table and revokes every privilege from `public`, `anon`, and `authenticated`, so only the service role reads and appends rows. It sets `lock_timeout` 5s and `statement_timeout` 60s for its transaction.

The migration gate classifies `20261020120000` as contract-replacing under `classify_migration`. It is add-only: no table, column, or row is removed.

## Approval

Lucas yes, 2026-10-20, staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes. Apply 20261019070000 and 20261020120000 to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run before each. Never prod." The approval covers staging `skedzwocnmrhfigiwyzi` and exactly this version.

The record is issued at `2026-10-20T20:55:00-05:00` and expires at `2026-10-23T20:55:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Write this JSON list to `approved.json`.

```json
["20261020120000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha 468de3986c4673ddda2bd94fc19746dff921f818 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-20-staging-business-due-on-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261019070000` when this runs. That is the version in record `staging-apply-2026-10-20-a`. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-20-b`.
