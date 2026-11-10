-- The production reset step (#1789): after the database is emptied, bring back the
-- empty migration ledger before the apply tool records anything. Same shape as the
-- table the Supabase CLI creates. prove.sh runs it on database C.
create schema if not exists supabase_migrations;
create table if not exists supabase_migrations.schema_migrations (
    version text primary key,
    statements text[],
    name text
);
