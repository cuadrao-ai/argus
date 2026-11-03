# Import the DGII RNC registry

The hosted staging cron downloads the two public RNC zips, parses them, and loads the rows into staging only when the approval checks pass. The GitHub workflow only downloads and parses.

## What the job does

Two jobs share `scripts/ops/dgii_rnc_daily.sh`, which owns the URLs and the download. Only the cron loads.

- The hosted cron `cuadrao-dgii-rnc-staging` in `render.yaml` runs the script at 07:00 UTC every day. See [Run the hosted cron](#run-the-hosted-cron).
- `.github/workflows/dgii-rnc-import.yml` runs `dgii_rnc_daily.sh download` and then the parse, so CI checks the real published files. It runs on a pull request that touches the job and on `workflow_dispatch`. It has no schedule, because the cron already downloads and parses the files every day. It has no database credential and never loads.

The publisher has one zip for each button on its page, and each zip holds one file.

| Saved as | URL | Holds | When the download fails |
| --- | --- | --- | --- |
| `rnc-csv.zip` | `https://dgii.gov.do/app/WebApps/Consultas/RNC/RNC_CONTRIBUYENTES.zip` | `RNC_Contribuyentes_Actualizado_<date>.csv`, the canonical source | The job stops and loads nothing. |
| `rnc-txt.zip` | `https://dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip` | `DGII_RNC.TXT`, read only for the trade name | The load goes on, and each RNC keeps its previous `trade_name`. |

A download fails on a curl error or on any HTTP status other than 200.

The job finds the CSV by that name pattern in any folder of `rnc-csv.zip`. It reads the CSV as comma separated, double quoted Latin-1 with a quote-aware parser, and finds each column by its header. A file that is not a zip, or a zip without that entry, fails the job, prints the entries it found, and loads nothing.

`file_date` is the CSV entry's modification date, read as the America/Santo_Domingo calendar date.

```bash
python3 scripts/ops/dgii_rnc_import.py parse rnc-csv.zip rnc-txt.zip
```

In the cron, the gate then decides whether to load. A load copies `rnc`, `name`, `trade_name`, `status`, `file_date`, `activity`, `start_date`, and `regime` into `public.dgii_rnc_load` and finishes that session. A later session calls `public.dgii_rnc_swap(min_rows integer)`, which returns the integer row count now in `public.dgii_rnc`. `min_rows` is 700000. The job prints that integer as `swap_rows` and fails if it is below 700000. The job does not call `public.dgii_rnc_lookup`.

`name` is the razón social, `activity` the actividad económica, `start_date` the fecha de inicio, and `regime` the régimen. A blank value is NULL. A `fecha` that is not a real dd/mm/yyyy date is NULL. On the first real parse, 729443 rows held a date of that shape and 729442 of them parsed. Status is copied as written, and the load keeps every estado.

`trade_name` is the only value that does not come from the CSV. It is column 3 of the `DGII_RNC.TXT` entry in `rnc-txt.zip`, joined by RNC. The TXT adds no rows and changes no other field. A row with no match stores NULL, and a blank column 3 is NULL. On the first real parse the column looked like a trade name: 448071 values all joined a CSV row, 435062 were distinct, the average was 20 characters, 52 held no letter, and 24911 equaled the legal name. Those are counts, and nobody has read the values.

A failed or empty TXT never erases a name and never stops the load. A missing file, a file that is not a zip, a torn zip, a zip without exactly one `DGII_RNC.TXT`, and a TXT that parses to 0 names all count as failed. The summary then prints `trade_names=unavailable reason=<why>: previous names stay`, and `load` reads the current names from `public.dgii_rnc` and joins them by RNC. A new RNC stays NULL until the next good TXT. If that read fails, the job fails and the previous rows stay.

The TXT parser accepts CRLF and LF line ends. It joins a wrapped record over at most 5 lines and drops it after that, and a line over 1 MiB counts as a failed TXT. So a TXT with no pipes ends in linear time with 0 names.

The loader keeps a row only when the RNC normalizes to 9 or 11 digits and the trimmed name is not blank. The file has one eight-digit RNC. It is quarantined, which means it is counted in `dropped`, reported in a `dropped_sample` line with its reason and digit count, not padded, and not loaded. Repeated RNCs keep the last row. A row with the wrong number of fields counts as an anomaly, and more than 25 anomalies fail the job. A header without one RNC, razón social, actividad, fecha, estado, and régimen column fails the job. The error prints the column count and the header words it found, and no cell, because a headerless file has a row in that place.

More than 25 lost rows fail the job and load nothing. A lost row is a dropped row or a kept row with a blank estado. RNC and name are the other fields the table requires, and a row without either is already a dropped row. The file dated 2026-10-31 has 1 dropped row and 0 blank estados. A blank `activity`, `start_date`, `regime`, or `trade_name` is not a lost row, because the table allows NULL there.

`parse` and `load` print the summary before they apply the checks, so a failed check still leaves the file facts in the log. No line and no error prints a name, an RNC, or a row. A failed `psql` prints only its `ERROR:` line, because its `DETAIL` and `CONTEXT` lines quote the row.

| Line | What it tells you |
| --- | --- |
| `rows`, `anomalies`, `dropped`, `blank_status`, `duplicates`, `parsed_bytes` | The counts the checks use and the size of the load. |
| `trade_name_filled`, `activity_filled`, `start_date_filled`, `regime_filled` | The rows with a value in each optional column. |
| `activity_avg_length` | The average characters in a filled actividad. |
| `csv_header` | The header cells as written, so a renamed column shows here. |
| `date_shape` | The most common shapes of the date cell, with digits as `d` and letters as `a`. A `start_date_filled` far below the `dd/dd/dddd` count means the date format is not dd/mm/yyyy. |
| `trade_names`, `trade_name_txt_*`, `trade_name_same_as_name` | Whether the TXT loaded, and counts that describe column 3. The `trade_name_txt_*` counts are 0 when the TXT failed. |
| `status`, `rnc_length` | One count for each estado and each RNC length. |

## Run the hosted cron

`render.yaml` declares the cron `cuadrao-dgii-rnc-staging` on `codex/private-alpha-next`. It is staging only, its deploy trigger is `off`, and its build installs nothing, because the importer uses only the standard library. Each value is set on the service, and `render.yaml` holds none.

| Setting | Value |
| --- | --- |
| `DGII_RNC_LOAD_ENABLED` | `true` turns the load on. Any other value downloads nothing and exits 0. |
| `SUPABASE_STAGING_DB_URL` | The staging database URL on direct port 5432. An empty value downloads nothing and exits 0. |
| `DGII_RNC_STATEMENT_TIMEOUT`, `DGII_RNC_LOAD_HEADROOM_FLOOR`, `DGII_RNC_SIZE_LIMIT` | Optional. An empty value keeps the default. |

The image must hold `psql`. A missing `psql` fails the job with `psql is not installed`.

The cron is the only loader. Never set `SUPABASE_STAGING_DB_URL` or `DGII_RNC_LOAD_ENABLED` as a secret or variable on GitHub. The workflow reads neither.

## Turn loading on

Set `DGII_RNC_LOAD_ENABLED` to `true` on the cron service. Any other value, including an empty one, skips the load. The gate prints `load skipped: DGII_RNC_LOAD_ENABLED is not true`.

## Set the staging database secret

Set `SUPABASE_STAGING_DB_URL` on the cron service only. An empty value skips the load. The gate prints `load skipped: SUPABASE_STAGING_DB_URL is absent`. The job does not print the URL.

## Check the files without loading

A pull request that touches the job, or a manual run of the workflow, downloads the real zips and parses them. Neither run loads, because the workflow has no database credential. Manual dispatch is listed once this workflow file is on the repository default branch.

## Verify a load

After a load, compare `swap_rows` in the job log with the staging count, then look up one RNC.

```sql
select count(*) from public.dgii_rnc;
select * from public.dgii_rnc_lookup('123456789');
```

Replace the quoted argument with the RNC you want to read. Run that lookup as the database owner or `service_role`. `authenticated` cannot execute it. The swap replaces `public.dgii_rnc` in one transaction. A failed swap leaves the previous rows in place. A lookup waits only for the renames, because the key is built before the swap locks the registry.

## Watch the database size

The first real parse ran on 2026-11-02 against the CSV dated 2026-10-31. It printed `rows=796924`, `parsed_bytes=127691030`, `activity_filled=772164`, and `activity_avg_length=70.4`. The free database limit is 500 MB.

The sizes below are measured on a local Postgres 16 database, not on staging. 796924 synthetic rows matched those real counts and that exact `parsed_bytes`, and each of two file orders loaded four times through the real importer. The results matched to 0.1 MiB, because the swap builds the key in one pass, so file order does not change its size. Write-ahead log and sort temp files are not counted.

| Measure | Size |
| --- | --- |
| Table heap | 137.6 MiB |
| Primary key | 24.0 MiB |
| Table plus key | 161.7 MiB |
| Growth during any load | 161.7 MiB |
| First load peak, base database 7.7 MiB | 169.4 MiB |
| Reload peak, base database 7.7 MiB | 331.0 MiB |

A reload holds two copies at its peak: the old table and the new table. So `7.7 + 161.7 + 161.7 = 331.1 MiB`, which matches the measured 331.0 MiB. With 31 MiB outside the table, a reload peaks near 354 MiB.

Before the truncate or the copy, the load reads `pg_database_size(current_database())` and `pg_total_relation_size` of `public.dgii_rnc` and `public.dgii_rnc_load`. A missing table counts as zero. The check predicts `database size - load table + headroom`. It leaves out the load table because the copy truncates that table first, so a failed swap does not block the next day. The headroom is the larger of the live table size and a floor of 170 MB, which is 178257920 bytes. The floor is the measured growth plus 5 percent. The load fails without loading when the prediction exceeds the threshold. The default threshold is 450 MB, which is 471859200 bytes, under the 500 MB limit.

| Case | Database before | Predicted peak | Real peak | Result |
| --- | --- | --- | --- | --- |
| First load, 31 MiB outside the table | 31 MiB | 201 MiB | 193 MiB | Passes |
| Reload, 31 MiB outside the table | 193 MiB | 363 MiB | 354 MiB | Passes |
| Any load, table under 170 MB | Above 280 MiB | Above 450 MiB | Above 442 MiB | Refused |

The floor is a fixed number, so it follows the table only through the live table size. A file much larger than the last load can pass the check and peak above its prediction.

Set the cron variables `DGII_RNC_LOAD_HEADROOM_FLOOR` and `DGII_RNC_SIZE_LIMIT` to change the floor and the threshold. An empty value keeps the default. The value is a number plus `B`, `KB`, `MB`, or `GB`.

The workflow parse prints `parsed_bytes`. After the swap, the log prints `database_bytes_after` and `relation_bytes` for `public.dgii_rnc` and `public.dgii_rnc_load`. The load table ends empty after a good swap, and a failed swap leaves its rows until the next copy.

The three DGII migrations set no function timeout.

## Set the swap timeout

The cron load runs `psql` against `SUPABASE_STAGING_DB_URL`, the database owner. It does not call the swap through an HTTP API, and it does not `SET ROLE authenticated`. The copy session ends before the swap session starts. Each session starts with `SET statement_timeout = '5min'`.

Loading waits on migration slots `20261018190000`, `20261102204200`, and `20261102225200`.

Set the cron variable `DGII_RNC_STATEMENT_TIMEOUT` to another interval, such as `10min`, when the swap of about 800000 rows needs longer. An empty value keeps 5 minutes. The value must be a number followed by `ms`, `s`, `min`, or `h`.

## Wait for the migration

Loading waits on migrations `20261018190000_dgii_rnc_registry.sql`, `20261102204200_dgii_rnc_csv_columns.sql`, and `20261102225200_dgii_rnc_rename_swap.sql`, and on a separate staging approval. The importer copies the three new columns, so it fails on a database without the second migration. `public.dgii_rnc_swap(min_rows integer)` is security definer with an empty search path. It renames the load table into place, then sets each table's grants again, because grants stay with a table through a rename. A null or non-positive `min_rows` raises before the swap locks `public.dgii_rnc_load`. `public.dgii_rnc_lookup(p_rnc text)` is volatile and is not security definer. `anon` and `authenticated` cannot execute it. The load job does not call lookup. This runbook does not record a completed load.
