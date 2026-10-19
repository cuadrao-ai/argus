# Apply one staging migration: profile age confirmation

Apply `20261019060000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-19-staging-profile-age-confirmation-apply.json`. Its id is `staging-apply-2026-10-19-c`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261019060000` (`20261019060000_profile_age_confirmation.sql`): requires an 18+ confirmation when an account is created (#1231).

This record covers exactly this version. It runs after record `staging-apply-2026-10-19-b` has applied.

## Effects to expect

`20261019060000` adds nullable `public.profiles.age_confirmed_at`, plus the function `public.protect_profile_age_confirmation()` and the trigger `profiles_age_confirmation_first_write`, which keep the value write-once and backend-only. Existing rows keep `age_confirmed_at` null and are not rewritten. It sets `lock_timeout` 5s and `statement_timeout` 60s for its transaction.

## Approval

Lucas yes, 2026-10-19 3:25 PM CT, staging only. Relayed by Yelena. The approval covers staging `skedzwocnmrhfigiwyzi` and exactly this version.

The record is issued at `2026-10-19T16:55:00-05:00` and expires at `2026-10-22T16:55:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Write this JSON list to `approved.json`.

```json
["20261019060000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha d7fdf5a55719582372226617a6ad28310561f085 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-19-staging-profile-age-confirmation-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261019050000` when this runs. That is the version in record `staging-apply-2026-10-19-b`. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-19-c`.
