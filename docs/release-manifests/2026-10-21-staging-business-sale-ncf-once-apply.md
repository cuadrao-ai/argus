# Apply one staging migration: one sale per NCF

Apply `20261021050000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-21-staging-business-sale-ncf-once-apply.json`. Its id is `staging-apply-2026-10-21-e`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261021050000` (`20261021050000_business_sale_ncf_once.sql`): refuses a second accepting or accepted sale with the same NCF or e-CF in one Business (#1352).

This record covers exactly this version. It runs after record `staging-apply-2026-10-21-d` has applied `20261021040000`.

The candidate is `79ed3f456113f624fb15a33d66675f4a21086e55`, the head of #1352. #1352 got Eval SHIP at that exact head. #1352 is not merged when this runs. The staging API keeps running the code from before #1352 until #1352 lands and deploys.

The candidate tree does not hold every version already in the staging ledger. The tool plans from the ledger head and the candidate's files above it, so a ledger row without a file in the candidate does not stop the run.

## Effects to expect

`20261021050000` first counts Business and number pairs that already have more than one accepting or accepted sale. If the count is above 0, it raises `business_sale_ncf_duplicates_present` and the transaction changes nothing. Run that count read-only before the dry run.

It then creates the partial unique index `financial_import_events_sale_ncf_idx` on `public.financial_import_events` over the owner space and the normalized number. The number is the e-CF when present, else the NCF, trimmed and upper case. Only `B` plus ten digits or `E` plus twelve digits counts.

The change is additive. There is no data step and no down migration.

## Approval

Lucas, 2026-10-21, standing rule for staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes, as a standing rule: any migration whose PR got Eval SHIP may be applied to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run first, before that PR merges. Never prod. Tell me after each one." The rule covers staging `skedzwocnmrhfigiwyzi` and migrations whose PR got Eval SHIP.

#1352 got Eval SHIP at `79ed3f456`: https://github.com/lagarcess/argus/pull/1352#issuecomment-6313554583.

The record is issued at `2026-10-21T10:45:00-05:00` and expires at `2026-10-24T10:45:00-05:00`.

## Apply

Set the environment variable named by `--database-url-env` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Run from a checkout whose `HEAD` is the commit that adds this record on top of the candidate. The tool refuses a record that is not committed on top of the candidate.

Write this JSON list to `approved.json`.

```json
["20261021050000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha 79ed3f456113f624fb15a33d66675f4a21086e55 \
  --approved-file approved.json \
  --database-url-env STAGING_DB_URL \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-21-staging-business-sale-ncf-once-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261021040000` when this runs. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-21-e`.
