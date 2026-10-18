# Import the DGII RNC registry

The scheduled workflow downloads the public RNC zip, parses it, and loads the rows into staging only when the approval checks pass.

## What the job does

`.github/workflows/dgii-rnc-import.yml` runs at 07:00 UTC every day. You can also start it with `workflow_dispatch`.

The job checks out this repository and downloads `DGII_RNC.zip`. It parses the `DGII_RNC.TXT` entry.

```bash
python3 scripts/ops/dgii_rnc_import.py parse rnc.zip
```

The gate then decides whether to load. A load copies the parsed rows and swaps them into `public.dgii_rnc`.

## Turn loading on

Set the repository variable `DGII_RNC_LOAD_ENABLED` to the string `true`.

Any other value skips the load, including an empty value. The gate prints `load skipped: DGII_RNC_LOAD_ENABLED is not true`.

## Set the staging database secret

Set the repository secret `SUPABASE_STAGING_DB_URL` to the staging database URL.

An empty secret skips the load. The gate prints `load skipped: SUPABASE_STAGING_DB_URL is absent`. The workflow does not print the URL.

## Choose a dry run

The `workflow_dispatch` input `dry_run` defaults to true. A manual run with that default prints `load skipped: dry run` and does not load.

The schedule sets dry run to false. It still does not load until `DGII_RNC_LOAD_ENABLED` is `true` and `SUPABASE_STAGING_DB_URL` is set.

## Verify a load

After a load, run these queries on staging.

```sql
select count(*) from public.dgii_rnc;
select rnc, name, status, file_date from public.dgii_rnc where rnc = '...';
```

Replace the quoted placeholder with the RNC you want to read.

## Watch the database size

The table plus its primary key is about 95 MB. A reload peaks around 213 MB on staging. The free database limit is 500 MB.

## Wait for the migration

Loading waits on the backend migration and a separate staging approval. This runbook does not record a completed load.
