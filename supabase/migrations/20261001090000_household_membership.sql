-- Household membership, invitations, and explicit account grants.
-- Spec: docs/specs/lanes/household-permission-policy.md
-- Founder-approved permission policy 2026-10-01.
--
-- Account ownership stays financial_accounts.user_id. Grants never rewrite
-- ownership or space_id. Clients hold no insert/update; the API pool writes.
--
-- Deletion-safe historical identity: attribution columns use ON DELETE SET NULL
-- so account deletion cannot strand household history. An active household still
-- requires a live admin_user_id (CHECK); close or transfer before deleting the
-- admin. Invitation acceptance may retain accepted_at after accepted_by clears.

create table if not exists public.households (
    id uuid primary key default gen_random_uuid(),
    name text check (name is null or char_length(name) between 1 and 80),
    status text not null default 'active' check (status in ('active', 'closed')),
    created_by uuid references auth.users(id) on delete set null,
    admin_user_id uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    closed_at timestamptz,
    check (
        (
            status = 'active'
            and closed_at is null
            and admin_user_id is not null
        )
        or (status = 'closed' and closed_at is not null)
    )
);

create index if not exists households_admin_idx
    on public.households (admin_user_id)
    where status = 'active';

create table if not exists public.household_members (
    id uuid primary key default gen_random_uuid(),
    household_id uuid not null references public.households(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    joined_at timestamptz not null default now(),
    left_at timestamptz,
    unique (id, household_id, user_id)
);

create unique index if not exists household_members_one_active_idx
    on public.household_members (household_id, user_id)
    where left_at is null;

create index if not exists household_members_user_active_idx
    on public.household_members (user_id)
    where left_at is null;

create table if not exists public.household_invitations (
    id uuid primary key default gen_random_uuid(),
    household_id uuid not null references public.households(id) on delete cascade,
    token_hash text not null unique,
    created_by uuid references auth.users(id) on delete set null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    revoked_at timestamptz,
    accepted_by uuid references auth.users(id) on delete set null,
    accepted_at timestamptz,
    check (expires_at > created_at),
    -- Pending: both null. Accepted: accepted_at set; accepted_by may later
    -- clear when the acceptor's auth user is deleted.
    check (accepted_by is null or accepted_at is not null)
);

create index if not exists household_invitations_household_idx
    on public.household_invitations (household_id, created_at desc);

create table if not exists public.household_account_grants (
    id uuid primary key default gen_random_uuid(),
    household_id uuid not null references public.households(id) on delete cascade,
    account_id uuid not null,
    owner_user_id uuid not null,
    permission text not null default 'view' check (permission in ('view', 'edit')),
    created_at timestamptz not null default now(),
    revoked_at timestamptz,
    foreign key (account_id, owner_user_id)
        references public.financial_accounts (id, user_id) on delete cascade
);

create unique index if not exists household_account_grants_one_active_idx
    on public.household_account_grants (household_id, account_id)
    where revoked_at is null;

create index if not exists household_account_grants_household_idx
    on public.household_account_grants (household_id)
    where revoked_at is null;

-- Non-recursive membership predicate for RLS (avoids self-select recursion).
create or replace function public.is_active_household_member(
    p_household_id uuid,
    p_user_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.household_members m
        where m.household_id = p_household_id
          and m.user_id = p_user_id
          and m.left_at is null
    );
$$;

revoke all on function public.is_active_household_member(uuid, uuid) from public;
grant execute on function public.is_active_household_member(uuid, uuid) to authenticated;

alter table public.households enable row level security;
alter table public.household_members enable row level security;
alter table public.household_invitations enable row level security;
alter table public.household_account_grants enable row level security;

drop policy if exists households_member_select on public.households;
create policy households_member_select on public.households
    for select to authenticated
    using (
        public.is_active_household_member(id, (select auth.uid()))
    );

drop policy if exists household_members_peer_select on public.household_members;
create policy household_members_peer_select on public.household_members
    for select to authenticated
    using (
        left_at is null
        and public.is_active_household_member(
            household_id, (select auth.uid())
        )
    );

drop policy if exists household_invitations_admin_select on public.household_invitations;
create policy household_invitations_admin_select on public.household_invitations
    for select to authenticated
    using (
        exists (
            select 1 from public.households h
            where h.id = household_invitations.household_id
              and h.admin_user_id = (select auth.uid())
              and h.status = 'active'
        )
    );

drop policy if exists household_account_grants_member_select on public.household_account_grants;
create policy household_account_grants_member_select on public.household_account_grants
    for select to authenticated
    using (
        revoked_at is null
        and public.is_active_household_member(
            household_id, (select auth.uid())
        )
    );

revoke all on public.households from anon, authenticated;
revoke all on public.household_members from anon, authenticated;
revoke all on public.household_invitations from anon, authenticated;
revoke all on public.household_account_grants from anon, authenticated;

grant select on public.households to authenticated;
grant select on public.household_members to authenticated;
grant select on public.household_invitations to authenticated;
grant select on public.household_account_grants to authenticated;
