# Apply two staging migrations

Apply `20261019020000` and `20261019040000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-19-staging-bank-import-receipt-address-apply.json`. Its id is `staging-apply-2026-10-19-a`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply the versions in this order. Pass no `--unrecorded` version. Each file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261019020000`: lets a business bank import keep its statement upload when the importer's account is deleted, by making `imported_by` nullable and setting it null on delete (#1277).
2. `20261019040000`: adds business receipt aliases, retired aliases, authorized senders and address events, the delivery authentication and review columns, and `business_sources.origin`, with service-role-only grants (#1280).

This record covers exactly these two versions. It runs after record `staging-apply-2026-10-18-c` has applied.

## Effects to expect

`20261019020000` drops `not null` on `business_bank_imports.imported_by` and drops and re-adds `business_bank_imports_imported_by_fkey` with `on delete set null`. Existing rows keep their values.

`20261019040000` adds nullable or defaulted columns to `business_email_routes` and `business_email_deliveries`, and creates four new tables. It adds `business_sources.origin` (`email` or `direct`, default `direct`) and backfills `email` on sources an email delivery already links, with the immutability trigger disabled only for that one update. Existing deliveries keep `auth_result` null and are not rewritten.

The migration gate classifies `20261019020000` as destructive, because it drops `not null` and drops and re-adds a foreign key. No table, column, or row is removed. `20261019040000` classifies as contract-replacing.

## Approval

Lucas yes, 2026-10-19 11:51 AM CT, staging only. Relayed by Yelena. The approval covers staging `skedzwocnmrhfigiwyzi` and exactly these two versions.

The record is issued at `2026-10-19T13:00:00-05:00` and expires at `2026-10-22T13:00:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Write this JSON list to `approved.json`.

```json
["20261019020000", "20261019040000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha 471d4dd778fe2bf6e70af2327a0e77db74d65e88 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-19-staging-bank-import-receipt-address-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261018230000` when this runs. That is the last version in record `staging-apply-2026-10-18-c`. When the dry run lists only those two versions, run the same command with `--execute --hosted-confirm staging-apply-2026-10-19-a`.
