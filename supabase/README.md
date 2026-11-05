# Supabase migration workflow

Apply staging migrations only after their PR has merged into
`codex/private-alpha-next`. The root coordinator runs `supabase db push` from
that merged branch during the post-merge deploy. Never apply a staging
migration from a feature branch, through MCP `apply_migration`, or through
direct SQL DDL. Do not repair staging migration history.

Before merge, use read-only staging checks and an isolated local database.
`supabase db diff --linked` compares the migration replay with staging.
`supabase db push --linked --dry-run --skip-vault` checks for pending files
without applying migrations or updating Vault secrets. Verify the linked
project before either command.

Use new forward migrations for schema changes. Start each new migration with
`set local lock_timeout = '5s';` and
`set local statement_timeout = '60s';`. Make operations idempotent where
possible and enable RLS on new tables. Do not add these statements to an
already applied migration. An explicitly approved historical reconciliation
must preserve the exact applied SQL body.
