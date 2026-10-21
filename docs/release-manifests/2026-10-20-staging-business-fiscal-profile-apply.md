# Apply one staging migration: business fiscal profile

Apply `20261019070000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-20-staging-business-fiscal-profile-apply.json`. Its id is `staging-apply-2026-10-20-a`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261019070000` (`20261019070000_business_fiscal_profile.sql`): stores whether a business tax id is an RNC or a cédula (#1245).

This record covers exactly this version. Record `staging-apply-2026-10-20-b` applies `20261020120000` after it.

## Effects to expect

`20261019070000` adds nullable `public.spaces.business_tax_id_type`. It sets that column to `rnc` for every 9-digit `business_rnc` and to `cedula` for every 11-digit one. It then drops the check `business_rnc_shape` and adds the check `business_tax_id_pair`, which requires the id and its type together, with the digit count the type names. It sets `lock_timeout` 5s and `statement_timeout` 60s for its transaction.

The migration gate classifies `20261019070000` as destructive under `classify_migration`, because it drops a constraint. No table, column, or row is removed. The old check already held every non-null `business_rnc` to 9 or 11 digits on a business space and refused an all-zero id, so every existing row meets the new check after the update. Before executing, run a read-only query that counts staging rows that would fail `business_tax_id_pair` after the update. Stop if the count is not zero.

## Approval

Lucas yes, 2026-10-20, staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes. Apply 20261019070000 and 20261020120000 to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run before each. Never prod." The approval covers staging `skedzwocnmrhfigiwyzi` and exactly this version.

The record is issued at `2026-10-20T20:55:00-05:00` and expires at `2026-10-23T20:55:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Write this JSON list to `approved.json`.

```json
["20261019070000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha 468de3986c4673ddda2bd94fc19746dff921f818 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-20-staging-business-fiscal-profile-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261019060000` when this runs. That is the version in record `staging-apply-2026-10-19-c`. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-20-a`.
