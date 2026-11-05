-- Invite code hardening (#789).
-- Spec: docs/API_CONTRACT.md "Invite code security"; issue #789.
--
-- 1. Code digests move off client-readable tables. They lived in
--    public.household_invitations.code_hash and public.beta_invitations.code_hash,
--    beside owner-scoped SELECT policies. No client role has SELECT on either
--    table today, but one later grant would have exposed them. They now live in
--    argus_private, which anon and authenticated cannot even reach. service_role
--    does have usage on that schema (granted by earlier migrations for other
--    tables) but gets no privilege on this table. RLS is on with no policy for
--    any role, and anon, authenticated and service_role hold no table grant.
--    Only the backend database owner reads and writes it.
-- 2. Digests are HMAC-SHA-256 under a server secret (ARGUS_INVITE_CODE_SECRET)
--    and say which key made them: v2.<key id>.<hex>. The check below refuses
--    anything else, so an unkeyed digest can never be written again.
-- 3. The old v1 digests were unkeyed SHA-256 of 8-character codes. A digest
--    cannot be turned back into its code, so they cannot be re-hashed; they
--    are dropped. Existing invitations keep every other column and still open
--    by their link token; only their old typed code stops working. All such
--    rows are test data (no code flag has been on in any hosted environment).

create schema if not exists argus_private;
revoke all on schema argus_private from public, anon, authenticated;

create table argus_private.invite_code_digests (
    digest text primary key
        check (digest ~ '^v2\.[0-9a-f]{8}\.[0-9a-f]{64}$'),
    household_invitation_id uuid unique
        references public.household_invitations(id) on delete cascade,
    beta_invitation_id uuid unique
        references public.beta_invitations(id) on delete cascade,
    created_at timestamptz not null default now(),
    -- Set when a code found under the previous secret moves to the current one.
    rehashed_at timestamptz,
    check (num_nonnulls(household_invitation_id, beta_invitation_id) = 1)
);

comment on table argus_private.invite_code_digests is
    'Keyed (HMAC-SHA-256) digests of typed invite codes. Backend only: no table grant to anon, authenticated or service_role (service_role has schema usage only), RLS on with no policy.';

alter table argus_private.invite_code_digests enable row level security;
revoke all on argus_private.invite_code_digests
    from public, anon, authenticated, service_role;

drop index if exists public.household_invitations_code_hash_idx;
alter table public.household_invitations drop column if exists code_hash;
alter table public.beta_invitations drop column if exists code_hash;
