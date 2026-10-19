# Apply two staging migrations

Apply `20261018220000` and `20261018230000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-18-staging-dgii-export-month-close-apply.json`. Its id is `staging-apply-2026-10-18-c`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply the versions in this order. Pass no `--unrecorded` version. Each file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261018220000`: adds the Business RNC column on spaces and the DGII snapshot columns on draft revisions, and lets the human-only `approve_refund` and `set_business_rnc` actions be recorded (#1233).
2. `20261018230000`: adds the month close settlement table and its immutable revision history, with service-role-only grants (#1238).

This record covers exactly these two versions. It runs after records `staging-apply-2026-10-18` and `staging-apply-2026-10-18-b` have applied.

## Effects to expect

`20261018220000` adds nullable columns, so existing rows keep null values and pass the new checks. It drops and re-adds `business_action_receipts_unplanned_command` with the same list plus `approve_refund` and `set_business_rnc`. The new `business_dgii_human_commands` check is validated against existing action receipts. Those two actions are new, so no existing row should carry them.

`20261018230000` creates two new tables, two trigger functions, and two triggers. It changes no existing table.

The migration gate classifies `20261018220000` as destructive, because it drops and re-adds a check constraint. No table, column, or row is removed. `20261018230000` classifies as contract-replacing.

## Approval

Lucas yes, 2026-10-18 2:13 PM CT, staging only. Relayed by Yelena. The approval covers staging `skedzwocnmrhfigiwyzi` and exactly these two versions.

The record is issued at `2026-10-18T14:20:00-05:00` and expires at `2026-10-21T14:20:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Write this JSON list to `approved.json`.

```json
["20261018220000", "20261018230000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha 789ee2236325f9a2df4a03c49f07a69d49318104 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-18-staging-dgii-export-month-close-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261018210000` when this runs. That is the last version in record `staging-apply-2026-10-18-b`. When the dry run lists only those two versions, run the same command with `--execute --hosted-confirm staging-apply-2026-10-18-c`.
