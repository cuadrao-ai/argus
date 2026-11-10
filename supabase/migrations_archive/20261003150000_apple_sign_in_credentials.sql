-- Sign in with Apple: the refresh token account deletion revokes.
-- Spec: docs/specs/lanes/mvee-five-lane-handoff.md (Lane 6, Apple revocation)
-- and docs/DATA_MODEL.md "Apple sign-in credentials".
--
-- App Store Review Guideline 5.1.1(v) requires an app that offers Sign in with
-- Apple to revoke the person's Apple tokens when they delete their account.
-- The API captures Apple's one-time authorization code at sign-in, exchanges
-- it server-side, and keeps only the refresh token, sealed with AES-256-GCM
-- under ARGUS_INGESTION_SECRET_KEY and bound to "apple_sign_in:<user_id>".
-- One row per person: a later sign-in replaces the token, it never adds one.
--
-- No client role can read or write this table. RLS is on with no policy, and
-- every client privilege is revoked; only the API's service role writes it,
-- with the user id taken from the verified JWT. No SECURITY DEFINER function
-- is needed because nothing here runs as a client.
--
-- The foreign key restricts deletion on purpose. Deleting an auth user who
-- still has a stored Apple token would drop the token without revoking it at
-- Apple, so the database refuses until the account-deletion run has revoked it
-- and removed this row. A failed revoke leaves the row (the pending revoke).

create table if not exists public.apple_sign_in_credentials (
    user_id uuid primary key references auth.users(id) on delete restrict,
    -- The Apple client the token was issued to (the app's bundle id for the
    -- native app). Apple's revoke endpoint must be called with the same one.
    client_id text not null check (
        client_id ~ '^[A-Za-z0-9][A-Za-z0-9.-]{0,154}$'
    ),
    secret_ciphertext bytea not null check (octet_length(secret_ciphertext) between 29 and 8192),
    captured_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.apple_sign_in_credentials enable row level security;

revoke all on public.apple_sign_in_credentials from public, anon, authenticated;
grant select, insert, update, delete on public.apple_sign_in_credentials to service_role;
