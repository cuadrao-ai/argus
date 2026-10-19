# Apply one staging migration: business consent acceptances

Apply `20261019050000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-19-staging-business-consent-acceptances-apply.json`. Its id is `staging-apply-2026-10-19-b`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261019050000`: saves a person's acceptance of the Business data-use screen on the server (#1312).

This record covers exactly this version. It runs after record `staging-apply-2026-10-19-a` has applied, and before record `staging-apply-2026-10-19-c`.

## Effects to expect

`20261019050000` creates `public.business_consent_acceptances` with an index on `space_id`, enables row level security, and adds select and insert policies for the row's own user. No existing table, column, or row changes.

The migration gate classifies `20261019050000` as contract-replacing (`expand_contract_or_maintenance_required` under `classify_migration`). It is add-only: no table, column, or row is removed.

## Approval

Lucas yes, 2026-10-19 3:25 PM CT, staging only. Relayed by Yelena.

Approval source: Lucas, 1:1 chat with Yelena · cuadrao, Oct 19 2026 3:25 PM CT, pre-approving add-only staging migrations that Priya SHIPs (staging only, merged PR plus committed record, never prod). The approval covers staging `skedzwocnmrhfigiwyzi` and exactly this version.

The record is issued at `2026-10-19T16:55:00-05:00` and expires at `2026-10-22T16:55:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Write this JSON list to `approved.json`.

```json
["20261019050000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha 43001d9f83306bd245605e676f205fda225b4998 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-19-staging-business-consent-acceptances-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261019040000` when this runs. That is the last version in record `staging-apply-2026-10-19-a`. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-19-b`.
