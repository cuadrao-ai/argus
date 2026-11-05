# Apply one staging migration: profile table density

Apply `20261020220000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-21-staging-profile-table-density-apply.json`. Its id is `staging-apply-2026-10-21-b`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261020220000` (`20261020220000_profile_table_density.sql`): stores each person's row height for dense tables (#1346).

This record covers exactly this version. It runs after record `staging-apply-2026-10-21-a` has applied.

The candidate is `c1f6d369dcb56a2a5eb8e29d1502571e35a243dd`, the head of #1346. #1346 got Eval SHIP at `4e9d1f25`. The migration file is byte-identical at `4e9d1f25` and at the candidate. The later commit on #1346 merges the #1344 head only. #1346 is not merged when this runs. The staging API keeps running the code from before #1346 until #1346 lands and deploys. That code does not read this column.

## Effects to expect

`20261020220000` adds `public.profiles.table_density`, a `text not null` column with default `'normal'`. The check `profiles_table_density_check` allows `compacto`, `normal`, or `amplio`. Every existing profile reads `normal`.

The migration adds no grant. It is add-only: no table, column, or row is removed.

## Approval

Lucas yes, 2026-10-21, staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes. Apply 20261020210000 and 20261020220000 to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run before each, before #1344 and #1346 merge. Never prod." The approval covers staging `skedzwocnmrhfigiwyzi` and exactly these two versions.

#1346 got Eval SHIP at `4e9d1f25`: https://github.com/lagarcess/argus/pull/1346#issuecomment-6309029995.

The record is issued at `2026-10-21T00:55:00-05:00` and expires at `2026-10-24T00:55:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Run from a checkout whose `HEAD` is the commit that adds this record on top of the candidate. The tool refuses a record that is not committed on top of the candidate.

Write this JSON list to `approved.json`.

```json
["20261020220000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha c1f6d369dcb56a2a5eb8e29d1502571e35a243dd \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-21-staging-profile-table-density-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The staging ledger head must be `20261020210000` when this runs. That is the version in record `staging-apply-2026-10-21-a`. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-21-b`.
