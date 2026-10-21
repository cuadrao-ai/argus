# Apply one staging migration: business bank line outcomes

Apply `20261020210000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-21-staging-business-bank-line-outcomes-apply.json`. Its id is `staging-apply-2026-10-21-a`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261020210000` (`20261020210000_business_bank_line_outcomes.sql`): records one live outcome per bank line, a match to one document or "no comprobante", and narrows bank suggestions to pending or declined (#1344).

This record covers exactly this version. It runs after record `staging-apply-2026-10-20-c` has applied. Record `staging-apply-2026-10-21-b` runs after this one.

The candidate is `c1f6d369dcb56a2a5eb8e29d1502571e35a243dd`, the head of #1346. It contains the #1344 head `5ee90796`. #1344 got Eval SHIP at `fb7d1d18`. The migration file is byte-identical at `fb7d1d18` and at the candidate. The later commits on #1344 merge the base branch only. #1344 is not merged when this runs. The staging API keeps running the code from before #1344 until #1344 lands and deploys.

## Effects to expect

`20261020210000` creates `public.business_bank_line_outcomes` with five named indexes and a guard trigger that allows only the end of a live outcome. It adds the trigger `business_document_settlement_follows_match` on `public.business_document_settlements`. While a document has a live match, its settlement must be the one that match wrote.

This migration is one-way. A data step turns each `confirmed` row in `public.business_bank_suggestions` into a live `match` outcome. It writes the settlement that match owns, with a revision row when the settlement changes. It then sets those suggestions back to `pending` and narrows the status check to `pending` or `declined`. The index `business_bank_suggestions_one_confirmed_idx` is dropped. There is no down migration.

The settlement insert references the document through `public.financial_activity_groups`. A confirmed suggestion whose document no longer exists stops the transaction. Check for such rows before the dry run.

It enables row level security on the new table. It revokes every privilege from `public`, `anon`, and `authenticated`, then grants `select`, `insert`, and `update` to `service_role` only. Clients hold no grant.

## Approval

Lucas yes, 2026-10-21, staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes. Apply 20261020210000 and 20261020220000 to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run before each, before #1344 and #1346 merge. Never prod." The approval covers staging `skedzwocnmrhfigiwyzi` and exactly these two versions.

#1344 got Eval SHIP at `fb7d1d18`: https://github.com/lagarcess/argus/pull/1344#issuecomment-6309029661.

The record is issued at `2026-10-21T00:55:00-05:00` and expires at `2026-10-24T00:55:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Run from a checkout whose `HEAD` is the commit that adds this record on top of the candidate. The tool refuses a record that is not committed on top of the candidate.

Write this JSON list to `approved.json`.

```json
["20261020210000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha c1f6d369dcb56a2a5eb8e29d1502571e35a243dd \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-21-staging-business-bank-line-outcomes-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261020200000` when this runs. That is the version in record `staging-apply-2026-10-20-c`. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-21-a`.
