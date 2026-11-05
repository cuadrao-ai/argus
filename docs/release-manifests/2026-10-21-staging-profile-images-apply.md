# Apply one staging migration: profile images

Apply `20261021040000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-21-staging-profile-images-apply.json`. Its id is `staging-apply-2026-10-21-d`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply this one version. Pass no `--unrecorded` version. The file runs as one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261021040000` (`20261021040000_profile_images.sql`): adds the private `profile-images` Storage bucket and one row per profile photo and Business logo (#1350).

This record covers exactly this version. It runs after record `staging-apply-2026-10-21-c` has applied `20261021020000`.

The candidate is `e23c9d902b6f0e8acf3ce7f75d85fdbe7cddca40`, the head of #1350. #1350 got Eval SHIP at that exact head. #1350 is not merged when this runs. The staging API keeps running the code from before #1350 until #1350 lands and deploys.

The candidate tree does not hold every version already in the staging ledger. The tool plans from the ledger head and the candidate's files above it, so a ledger row without a file in the candidate does not stop the run.

## Effects to expect

`20261021040000` inserts the bucket `profile-images` into `storage.buckets` with `public = false`, a 1 MiB file size limit, and `image/webp` as the only media type. On a repeat it forces the bucket private and resets the limit and media types.

The insert leaves both lifecycle columns null, so the hosted `protect_bucket_control_insert` trigger accepts it from `postgres`. The staging bucket `financial-document-sources` was created the same way by `20261008100000`.

It creates `public.profile_photos` (keyed by `auth.users.id`) and `public.business_logos` (keyed by `public.spaces.id`). Each row goes with its user or its space.

It enables row level security on both tables. It revokes every privilege from `public`, `anon`, `authenticated`, and `service_role`, then grants `select`, `insert`, `update`, and `delete` to `service_role` only.

The change is additive. There is no data step and no down migration.

## Approval

Lucas, 2026-10-21, standing rule for staging only. Relayed to this lane by the orchestrator.

Approval source, verbatim: "Yes, as a standing rule: any migration whose PR got Eval SHIP may be applied to staging skedzwocnmrhfigiwyzi only, with a committed approval record and a dry run first, before that PR merges. Never prod. Tell me after each one." The rule covers staging `skedzwocnmrhfigiwyzi` and migrations whose PR got Eval SHIP.

#1350 got Eval SHIP at `e23c9d902`: https://github.com/lagarcess/argus/pull/1350#issuecomment-6313015098.

The record is issued at `2026-10-21T10:45:00-05:00` and expires at `2026-10-24T10:45:00-05:00`.

## Apply

Set the environment variable named by `--database-url-env` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Run from a checkout whose `HEAD` is the commit that adds this record on top of the candidate. The tool refuses a record that is not committed on top of the candidate.

Write this JSON list to `approved.json`.

```json
["20261021040000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha e23c9d902b6f0e8acf3ce7f75d85fdbe7cddca40 \
  --approved-file approved.json \
  --database-url-env STAGING_DB_URL \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-21-staging-profile-images-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261021020000` when this runs. When the dry run lists only this version, run the same command with `--execute --hosted-confirm staging-apply-2026-10-21-d`.
