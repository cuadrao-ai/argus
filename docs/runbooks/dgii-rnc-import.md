# Import the DGII RNC registry

The scheduled workflow downloads the two public RNC zips, parses them, and loads the rows into staging only when the approval checks pass.

## What the job does

`.github/workflows/dgii-rnc-import.yml` runs at 07:00 UTC every day. You can also start it with `workflow_dispatch`.

The publisher has one zip for each button on its page, and each zip holds one file. The job checks out this repository and downloads both.

| Saved as | URL | Holds | When the download fails |
| --- | --- | --- | --- |
| `rnc-csv.zip` | `https://dgii.gov.do/app/WebApps/Consultas/RNC/RNC_CONTRIBUYENTES.zip` | `RNC_Contribuyentes_Actualizado_<date>.csv`, the canonical source | The job stops and loads nothing. |
| `rnc-txt.zip` | `https://dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip` | `DGII_RNC.TXT`, read only for the trade name | The load goes on, and every `trade_name` is NULL. |

A download fails on a curl error or on any HTTP status other than 200.

The job finds the CSV by that name pattern in any folder of `rnc-csv.zip`. It reads the CSV as comma separated, double quoted Latin-1 with a quote-aware parser, and finds each column by its header. A file that is not a zip, or a zip without that entry, fails the job, prints the entries it found, and loads nothing.

`file_date` is the CSV entry's modification date, read as the America/Santo_Domingo calendar date.

```bash
python3 scripts/ops/dgii_rnc_import.py parse rnc-csv.zip rnc-txt.zip
```

The gate then decides whether to load. A load copies `rnc`, `name`, `trade_name`, `status`, `file_date`, `activity`, `start_date`, and `regime` into `public.dgii_rnc_load` and finishes that session. A later session calls `public.dgii_rnc_swap(min_rows integer)`, which returns the integer row count now in `public.dgii_rnc`. `min_rows` is 700000. The job prints that integer as `swap_rows` and fails if it is below 700000. The job does not call `public.dgii_rnc_lookup`.

`name` is the razón social, `activity` the actividad económica, `start_date` the fecha de inicio, and `regime` the régimen. A blank value is NULL. A `fecha` that is not a real dd/mm/yyyy date is NULL. Status is copied as written, and the load keeps every estado.

`trade_name` is the only value that does not come from the CSV. It is column 3 of the `DGII_RNC.TXT` entry in `rnc-txt.zip`, joined by RNC. The TXT adds no rows and changes no other field. A row with no match stores NULL, and a blank column 3 is NULL.

Any failure in the TXT zip leaves every `trade_name` NULL for that run and does not stop the load. A missing file, a file that is not a zip, a torn zip, and a zip without exactly one `DGII_RNC.TXT` all count. The summary then prints `trade_names=unavailable reason=<why>: names stay null`. A load in that state replaces the names already on staging with NULL, and the next good run fills them again.

The loader keeps a row only when the RNC normalizes to 9 or 11 digits and the trimmed name is not blank. The file has one eight-digit RNC. It is quarantined, which means it is counted in `dropped`, reported in a `dropped_sample` line with its reason and digit count, not padded, and not loaded. Repeated RNCs keep the last row. A row with the wrong number of fields counts as an anomaly, and more than 25 anomalies fail the job. A header without one RNC, razón social, actividad, fecha, estado, and régimen column fails the job and prints the header it found.

The `parse` step prints the summary before it applies the checks, so a failed check still leaves the file facts in the log. The summary never prints a name, an RNC, or a row.

| Line | What it tells you |
| --- | --- |
| `rows`, `anomalies`, `dropped`, `duplicates`, `parsed_bytes` | The counts the checks use and the size of the load. |
| `trade_name_filled`, `activity_filled`, `start_date_filled`, `regime_filled` | The rows with a value in each optional column. |
| `activity_avg_length` | The average characters in a filled actividad. |
| `csv_header` | The header cells as written, so a renamed column shows here. |
| `date_shape` | The most common shapes of the date cell, with digits as `d` and letters as `a`. A `start_date_filled` far below the `dd/dd/dddd` count means the date format is not dd/mm/yyyy. |
| `trade_names`, `trade_name_txt_*`, `trade_name_same_as_name` | Whether the TXT loaded, and counts that describe column 3. |
| `status`, `rnc_length` | One count for each estado and each RNC length. |

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

Replace the quoted argument with the RNC you want to read. Run that lookup as the database owner or `service_role`. `authenticated` cannot execute it. The swap replaces `public.dgii_rnc` in one transaction. A failed swap leaves the previous rows in place.

## Watch the database size

The 2026-10-18 TXT kept 795000 rows, with `trade_name_filled=446798` and `parsed_bytes=57805193`. The free database limit is 500 MB.

The numbers below are estimates. They come from 795000 synthetic rows on a local database, one run for each length. The average activity length is the unknown, because no real CSV has been parsed. A reload holds three copies at its peak: the old table, the load table, and the new table. Write-ahead log is not counted.

| Average activity | `parsed_bytes` | Table plus key | Reload growth over the current size |
| --- | --- | --- | --- |
| 30 characters | 95574854 | 133 MiB | 236 MiB |
| 50 characters | 111259061 | 149 MiB | 271 MiB |
| 80 characters | 134770969 | 178 MiB | 323 MiB |

That growth is more than the 200 MB floor below, so the size check can pass a load that peaks above its threshold. On the first real parse, read `parsed_bytes` and set `DGII_RNC_LOAD_HEADROOM_FLOOR` from this table before the second load.

Before the truncate or the copy, the load reads `pg_database_size(current_database())` and `pg_total_relation_size` of `public.dgii_rnc`. The required headroom is the larger of that live size and a floor of 200 MB, which is 209715200 bytes. A missing table counts as zero, so the floor applies. The load fails without loading when the current database size plus that headroom exceeds the threshold. The default threshold is 450 MB, which is 471859200 bytes. A database near 350 MB fails that default, because 350 MB plus the 200 MB floor is 550 MB.

Set the repository variables `DGII_RNC_LOAD_HEADROOM_FLOOR` and `DGII_RNC_SIZE_LIMIT` to change the floor and the threshold. An empty value keeps the default. The value is a number plus `B`, `KB`, `MB`, or `GB`.

The dry run prints `parsed_bytes`. After the swap, the log prints `database_bytes_after` and `relation_bytes` for `public.dgii_rnc` and `public.dgii_rnc_load`.

Migrations `20261018190000_dgii_rnc_registry.sql` and `20261102204200_dgii_rnc_csv_columns.sql` set no function timeout.

## Set the swap timeout

The load step runs `psql` against `SUPABASE_STAGING_DB_URL`, the database owner. It does not call the swap through an HTTP API, and it does not `SET ROLE authenticated`. The copy session ends before the swap session starts. Each session starts with `SET statement_timeout = '5min'`.

Loading waits on migration slots `20261018190000` and `20261102204200`.

Set the repository variable `DGII_RNC_STATEMENT_TIMEOUT` to another interval, such as `10min`, when the swap of about 800000 rows needs longer. An empty value keeps 5 minutes. The value must be a number followed by `ms`, `s`, `min`, or `h`.

## Wait for the migration

Loading waits on migrations `20261018190000_dgii_rnc_registry.sql` and `20261102204200_dgii_rnc_csv_columns.sql`, and on a separate staging approval. The importer copies the three new columns, so it fails on a database without the second migration. `public.dgii_rnc_swap(min_rows integer)` is security definer with an empty search path. A null or non-positive `min_rows` raises before the swap locks `public.dgii_rnc_load`. `public.dgii_rnc_lookup(p_rnc text)` is volatile and is not security definer. `anon` and `authenticated` cannot execute it. The load job does not call lookup. This runbook does not record a completed load.
