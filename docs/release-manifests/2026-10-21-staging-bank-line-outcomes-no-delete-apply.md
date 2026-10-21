# Apply one staging migration: no delete on bank line outcomes

Apply `20261021060000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-21-staging-bank-line-outcomes-no-delete-apply.json`. Its id is `staging-apply-2026-10-21-f`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261021060000` (`20261021060000_business_bank_line_outcomes_no_delete.sql`): takes `delete`, `truncate`, and the other inherited privileges on `public.business_bank_line_outcomes` away from `service_role` (#1354).

This record covers exactly this version. It runs after record `staging-apply-2026-10-21-e` has applied `20261021050000`.

The candidate is `d3bb0dd6c7d10c8d3d98d8374a24ec245a045b13`, the head of #1354. #1354 got Eval SHIP at that exact head. #1354 is not merged when this runs. The staging API keeps running the code from before #1354 until #1354 lands and deploys.

The candidate tree does not hold every version already in the staging ledger. The tool plans from the ledger head and the candidate's files above it, so a ledger row without a file in the candidate does not stop the run.

## Effects to expect

`20261021060000` revokes every privilege on `public.business_bank_line_outcomes` from `service_role`, then grants back `select`, `insert`, and `update`.

Before this runs, `service_role` holds every table privilege on that table, including `delete` and `truncate`. That was recorded when `staging-apply-2026-10-21-a` applied `20261020210000`.

The change touches grants only. There is no data step and no down migration.

## Approval

Lucas, 2026-10-21, standing rule for staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes, as a standing rule: any migration whose PR got Eval SHIP may be applied to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run first, before that PR merges. Never prod. Tell me after each one." The rule covers staging `skedzwocnmrhfigiwyzi` and migrations whose PR got Eval SHIP.

#1354 got Eval SHIP at `d3bb0dd6c`: https://github.com/lagarcess/argus/pull/1354#issuecomment-6312937971.

The record is issued at `2026-10-21T10:45:00-05:00` and expires at `2026-10-24T10:45:00-05:00`.

## Apply

Set the environment variable named by `--database-url-env` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Run from a checkout whose `HEAD` is the commit that adds this record on top of the candidate. The tool refuses a record that is not committed on top of the candidate.

Write this JSON list to `approved.json`.

```json
["20261021060000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha d3bb0dd6c7d10c8d3d98d8374a24ec245a045b13 \
  --approved-file approved.json \
  --database-url-env STAGING_DB_URL \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-21-staging-bank-line-outcomes-no-delete-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261021050000` when this runs. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-21-f`.
