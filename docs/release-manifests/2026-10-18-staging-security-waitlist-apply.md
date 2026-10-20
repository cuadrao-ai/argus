# Apply three staging migrations

Apply `20261018030000`, `20261018030016`, and `20261018040000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-18-staging-security-waitlist-apply.json`. Its id is `staging-apply-2026-10-18`. The database name is `postgres`.

The record names the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and the session pooler `aws-0-us-east-1.pooler.supabase.com`. The direct host has no IPv4 address, so the connection path is the session pooler on port 5432. The user is `postgres.skedzwocnmrhfigiwyzi`.

## Versions

Apply the versions in this order. Pass no `--unrecorded` version. Each file splits into one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261018030000`
2. `20261018030016`
3. `20261018040000`

## Approval

Lucas (founder) approved in his 1:1 with Yelena, relayed by Yelena, 2026-10-18 03:38 America/Chicago. The approval covers staging `skedzwocnmrhfigiwyzi` only.

The record is issued at `2026-10-18T03:38:00-05:00` and expires at `2026-10-21T03:38:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` to the staging session pooler URL. The host is `aws-0-us-east-1.pooler.supabase.com`, the port is 5432, the database is `postgres`, and the user is `postgres.skedzwocnmrhfigiwyzi`. Do not put that URL on the command line. One matching pair of quotes around the value is removed before the URL is read. Mismatched quotes are left in place.

Write this JSON list to `approved.json`.

```json
["20261018030000", "20261018030016", "20261018040000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha c940a8b319086bea023bc63b8b6817a87dbffafd \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-host aws-0-us-east-1.pooler.supabase.com \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-18-staging-security-waitlist-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

When the dry run lists only those three versions, run the same command with `--execute --hosted-confirm staging-apply-2026-10-18`.

## Scheduler state

The scheduler key was not provisioned for this apply. Pre-apply step done: Yelena paused the cuadrao-waitlist-reminders cron job on staging at about 2026-10-18 03:44 America/Chicago and confirmed active=false. cuadrao-waitlist-retention stays active. Reminders stays paused until the Edge secret CUADRAO_WAITLIST_SCHEDULER_KEY and the Vault secret cuadrao_waitlist_scheduler_key are confirmed to hold the same scheduler-only secret. That key setup is a later follow-up and is not part of this apply.
