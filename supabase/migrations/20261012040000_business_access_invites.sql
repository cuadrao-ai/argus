-- Business access: a pending invite for an email that has no confirmed account
-- yet. It becomes a read+prepare grant in business_client_grants the first time
-- that confirmed email signs in. Service role only; the owner's own grant needs
-- no new table. The access ledger rows reuse business_action_receipts, whose
-- turn-less actions now include the six access actions.

create table public.business_access_invites (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    issuer_id uuid not null references auth.users(id) on delete cascade,
    email text not null check (email = lower(email) and position('@' in email) > 1 and length(email) <= 254),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    accepted_at timestamptz,
    accepted_grant_id uuid references public.business_client_grants(id) on delete set null,
    revoked_at timestamptz,
    check (expires_at > created_at),
    check (accepted_at is null or revoked_at is null)
);
-- One live invite per Business and email; an accepted or revoked one may repeat.
create unique index business_access_invites_live on public.business_access_invites(space_id, email)
    where revoked_at is null and accepted_at is null;
create index business_access_invites_email on public.business_access_invites(email)
    where revoked_at is null and accepted_at is null;

alter table public.business_access_invites enable row level security;
revoke all on public.business_access_invites from public, anon, authenticated;
grant select, insert, update, delete on public.business_access_invites to service_role;

-- Access changes are ledger rows without a turn. The receipts table allowed
-- only review and approval there; the six access actions join that list.
do $$
declare
    existing text;
begin
    select conname into existing from pg_constraint
    where conrelid = 'public.business_action_receipts'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) like '%review_draft%';
    if existing is not null then
        execute format('alter table public.business_action_receipts drop constraint %I', existing);
    end if;
    alter table public.business_action_receipts add constraint business_action_receipts_turnless_action_check
        check (turn_key is not null or (command->>'action' in (
            'review_draft', 'approve_expense',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite'
        )) is true);
end $$;
