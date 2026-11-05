# Apply one staging migration: business search memory

Apply `20261020200000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-20-staging-business-search-memory-apply.json`. Its id is `staging-apply-2026-10-20-c`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261020200000` (`20261020200000_business_search_memory.sql`): keeps each member's recent searches and the records they opened from a result, per Business (#1339).

This record covers exactly this version. It runs after record `staging-apply-2026-10-20-b` has applied.

The candidate is `b50f01f3271384e213d206add1c0ada63e746907`, the head of #1339 that got Eval SHIP. #1339 is not merged when this runs. The staging API keeps running the code from before #1339 until #1339 lands and deploys. That code does not read these tables.

## Effects to expect

`20261020200000` creates `public.business_search_recents` and `public.business_search_opens`. Each row references `public.spaces` and `auth.users` with `on delete cascade`. Both tables are new, so no existing row is read or rewritten.

It enables row level security on both tables. It revokes every privilege from `public`, `anon`, `authenticated`, and `service_role`, then grants `select`, `insert`, `update`, and `delete` to `service_role` only. Clients hold no grant.

The migration gate classifies `20261020200000` as contract-replacing under `classify_migration`. It is add-only: no table, column, or row is removed.

## Approval

Lucas yes, 2026-10-20, staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes. When #1339 passes Eval, apply 20261020200000 to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run first, before #1339 lands. Never prod." The approval covers staging `skedzwocnmrhfigiwyzi` and exactly this version.

#1339 got Eval SHIP at `b50f01f3`: https://github.com/lagarcess/argus/pull/1339#issuecomment-6307137871.

The record is issued at `2026-10-20T22:15:00-05:00` and expires at `2026-10-23T22:15:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Run from a checkout whose `HEAD` is the commit that adds this record on top of the candidate. The tool refuses a record that is not committed on top of the candidate.

Write this JSON list to `approved.json`.

```json
["20261020200000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha b50f01f3271384e213d206add1c0ada63e746907 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-20-staging-business-search-memory-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261020120000` when this runs. That is the version in record `staging-apply-2026-10-20-b`. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-20-c`.
