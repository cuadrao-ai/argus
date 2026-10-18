# Import the DGII RNC registry

The scheduled workflow downloads the public RNC zip, parses it, and loads the rows into staging only when the approval checks pass.

## What the job does

`.github/workflows/dgii-rnc-import.yml` runs at 07:00 UTC every day. You can also start it with `workflow_dispatch`.

The job checks out this repository and downloads `DGII_RNC.zip`. It parses the `DGII_RNC.TXT` entry. `file_date` is that entry's modification date, read as the America/Santo_Domingo calendar date.

```bash
python3 scripts/ops/dgii_rnc_import.py parse rnc.zip
```

The gate then decides whether to load. A load copies `rnc`, `name`, `trade_name`, `status`, and `file_date` into `public.dgii_rnc_load`. It then calls `public.dgii_rnc_swap(min_rows int)`, which returns the row count now in `public.dgii_rnc`. The job prints that integer as `swap_rows` and fails if it is below 700000.

`trade_name` is column 3. A blank commercial name is NULL. Status is copied as written.

The loader keeps a row only when the RNC normalizes to 9 or 11 digits and the trimmed name is not blank. An eight-digit RNC is dropped and is not padded. Repeated RNCs keep the last row. The summary prints `dropped`, `duplicates`, `trade_name_filled`, and a `dropped_sample` line for each of the first few drops.

## Turn loading on

Set the repository variable `DGII_RNC_LOAD_ENABLED` to the string `true`.

Any other value skips the load, including an empty value. The gate prints `load skipped: DGII_RNC_LOAD_ENABLED is not true`.

## Set the staging database secret

Set the repository secret `SUPABASE_STAGING_DB_URL` to the staging database URL.

An empty secret skips the load. The gate prints `load skipped: SUPABASE_STAGING_DB_URL is absent`. The workflow does not print the URL.

## Choose a dry run

The `workflow_dispatch` input `dry_run` defaults to true. A manual run with that default prints `load skipped: dry run` and does not load.

A pull request that touches this job also prints `load skipped: dry run`. Manual dispatch is listed once this workflow file is on the repository default branch. Until then, the pull request run is the dry run you can open from the branch.

The schedule sets dry run to false. It still does not load until `DGII_RNC_LOAD_ENABLED` is `true` and `SUPABASE_STAGING_DB_URL` is set. The schedule itself starts once this workflow file is on the repository default branch.

## Verify a load

After a load, compare `swap_rows` in the job log with the staging count, then look up one RNC.

```sql
select count(*) from public.dgii_rnc;
select * from public.dgii_rnc_lookup('123456789');
```

Replace the quoted argument with the RNC you want to read. The swap replaces `public.dgii_rnc` in one transaction. A failed swap leaves the previous rows in place.

## Watch the database size

The commercial names add 10825191 bytes to the COPY payload, about 10.3 MB. The 2026-10-18 file kept 795000 rows, with `trade_name_filled=446798` and `parsed_bytes=57805193`. The table plus its primary key is about 105 MB. A reload peaks around 223 MB on staging. The free database limit is 500 MB.

Before the truncate or the copy, the load queries `pg_database_size(current_database())` and adds the ceiling. The load fails without loading when the peak exceeds the threshold. The default ceiling is 100 MB, which is 104857600 bytes. The default threshold is 450 MB, which is 471859200 bytes.

Set the repository variables `DGII_RNC_LOAD_CEILING` and `DGII_RNC_SIZE_LIMIT` to change the ceiling and the threshold. An empty value keeps the default. The value is a number plus `B`, `KB`, `MB`, or `GB`.

The dry run prints `parsed_bytes`. After the swap, the log prints `database_bytes_after` and `relation_bytes` for `public.dgii_rnc` and `public.dgii_rnc_load`.

## Set the swap timeout

The load step runs `psql` against `SUPABASE_STAGING_DB_URL`. It does not call the swap through an HTTP API. The session starts with `SET statement_timeout = '5min'`.

Set the repository variable `DGII_RNC_STATEMENT_TIMEOUT` to another interval, such as `10min`, when the swap of about 800000 rows needs longer. An empty value keeps 5 minutes. The value must be a number followed by `ms`, `s`, `min`, or `h`.

## Wait for the migration

Loading waits on migration `20261018130000_dgii_rnc_registry.sql` and a separate staging approval. This runbook does not record a completed load.
