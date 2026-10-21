# Apply one staging migration: business country

Apply `20261021020000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-21-staging-business-country-apply.json`. Its id is `staging-apply-2026-10-21-c`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261021020000` (`20261021020000_business_country.sql`): adds a country and a currency to every space and fixes a Business's country once it is set (#1349).

This record covers exactly this version. It runs after record `staging-apply-2026-10-21-b` has applied `20261020220000`.

The candidate is `0252425cb321a5db56b9e76c662b5e8a4b9a8149`, the head of #1349. #1349 got Eval SHIP at that exact head. #1349 is not merged when this runs. The staging API keeps running the code from before #1349 until #1349 lands and deploys.

The candidate tree does not hold every version already in the staging ledger. The tool plans from the ledger head and the candidate's files above it, so a ledger row without a file in the candidate does not stop the run.

## Effects to expect

`20261021020000` adds `public.spaces.country` (`text not null default 'DO'`) and `public.spaces.currency` (`text not null default 'DOP'`). Every existing space gets `DO` and `DOP`.

It adds two checks that apply to Business spaces only. `business_country_known` allows `DO`, `US`, or `CA`. `business_currency_shape` requires three upper-case letters.

It adds `argus_private.business_country_immutable()` and the `before update` trigger `business_country_immutable` on `public.spaces`. The trigger refuses a change to a Business's country. The function is not executable by `public`, `anon`, or `authenticated`.

The change is additive. There is no data step and no down migration.

## Approval

Lucas, 2026-10-21, standing rule for staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes, as a standing rule: any migration whose PR got Eval SHIP may be applied to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run first, before that PR merges. Never prod. Tell me after each one." The rule covers staging `skedzwocnmrhfigiwyzi` and migrations whose PR got Eval SHIP.

#1349 got Eval SHIP at `0252425cb`: https://github.com/lagarcess/argus/pull/1349#issuecomment-6311191680.

The record is issued at `2026-10-21T10:45:00-05:00` and expires at `2026-10-24T10:45:00-05:00`.

## Apply

Set the environment variable named by `--database-url-env` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Run from a checkout whose `HEAD` is the commit that adds this record on top of the candidate. The tool refuses a record that is not committed on top of the candidate.

Write this JSON list to `approved.json`.

```json
["20261021020000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha 0252425cb321a5db56b9e76c662b5e8a4b9a8149 \
  --approved-file approved.json \
  --database-url-env STAGING_DB_URL \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-21-staging-business-country-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261020220000` when this runs. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-21-c`.
