# Apply four staging migrations

Apply `20261018040438`, `20261018180000`, `20261018190000`, and `20261018210000` to staging project `skedzwocnmrhfigiwyzi` only. Production stays untouched.

## Target

The record is `docs/release-manifests/2026-10-18-staging-invites-bank-matching-registry-apply.json`. Its id is `staging-apply-2026-10-18-b`. The database name is `postgres`.

The record lists the direct host `db.skedzwocnmrhfigiwyzi.supabase.co` and no other host. The pooler host is decided at apply time. The record's hosts list stays the direct host only.

## Versions

Apply the versions in this order. Pass no `--unrecorded` version. Each file splits into one transaction, so do not pass `--allow-mid-file-commit`.

1. `20261018040438`: sets the Business invite expiry default to 7 days and shortens pending invites to 7 days after creation (#1228).
2. `20261018180000`: adds Business bank statement lines and suggested matches. Raw lines are immutable and kept for 10 years (#1253).
3. `20261018190000`: adds the public RNC registry tables, its swap and lookup functions, and service-role-only grants (#1262).
4. `20261018210000`: seeds the 24-month retention policy for retention sweep evidence. It installs no purge executor or schedule (#1224).

This list stops at `20261018210000`. `20261018220000` and `20261018230000` have no approval and are not part of this record.

## Effects to expect

Applying `20261018040438` expires live invites older than 7 days. Every pending invite (not accepted, not revoked) gets `expires_at = least(expires_at, created_at + 7 days)`. A pending invite created more than 7 days ago is expired as soon as the file commits. Younger pending invites keep their link, with expiry moved to 7 days after creation. Accepted and revoked invites are unchanged. An owner can resend an expired invite.

The migration gate classifies `20261018190000` as destructive, because its swap function truncates the registry and load tables. Those tables are created by the same file, so applying it removes no existing data. The other three classify as contract-replacing.

## Approval

Lucas yes, 2026-10-18 10:53 AM CT, staging only. Relayed by Yelena. The approval covers staging `skedzwocnmrhfigiwyzi` and exactly these four versions.

The record is issued at `2026-10-18T10:56:00-05:00` and expires at `2026-10-21T10:56:00-05:00`.

## Apply

Set `ARGUS_APPLY_DATABASE_URL` in the environment to the staging database URL. Do not put that URL on the command line.

Write this JSON list to `approved.json`.

```json
["20261018040438", "20261018180000", "20261018190000", "20261018210000"]
```

Run the dry run first. The dry run prints the plan and applies nothing.

```bash
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha fb6d969505f364fa08e4eb89e7317619f7de4781 \
  --approved-file approved.json \
  --allow-host db.skedzwocnmrhfigiwyzi.supabase.co \
  --allow-database postgres \
  --hosted-approval docs/release-manifests/2026-10-18-staging-invites-bank-matching-registry-apply.json \
  --ssl-root-cert /path/to/ca-bundle.pem
```

The tool refuses a list that skips a version above the ledger head, so the staging ledger head must be `20261018040000` when this runs. When the dry run lists only those four versions, run the same command with `--execute --hosted-confirm staging-apply-2026-10-18-b`.
