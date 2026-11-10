-- Extend the landed Household authority with incarnation-bound consent and retries.
alter table public.households add column version bigint not null default 1 check (version > 0);
alter table public.household_members add column display_name text not null default 'Member' check (char_length(display_name) between 1 and 60);
alter table public.household_invitations add column accepted_membership_id uuid references public.household_members(id) on delete set null;
update public.household_invitations i set accepted_membership_id=m.id
from public.household_members m where i.household_id=m.household_id
  and i.accepted_by=m.user_id and m.joined_at<=i.accepted_at
  and (m.left_at is null or m.left_at>=i.accepted_at);
alter table public.household_account_grants add column owner_membership_id uuid;
alter table public.household_account_grants add column recipient_membership_id uuid;
-- A previous whole-household grant has no record of named recipient consent.
update public.household_account_grants set revoked_at=now() where revoked_at is null;
drop index public.household_account_grants_one_active_idx;
alter table public.household_account_grants add constraint household_grant_owner_membership
 foreign key (owner_membership_id,household_id,owner_user_id)
 references public.household_members(id,household_id,user_id);
alter table public.household_members add constraint household_member_identity unique(id,household_id);
alter table public.household_account_grants add constraint household_grant_recipient_membership
 foreign key (recipient_membership_id,household_id) references public.household_members(id,household_id);
alter table public.household_account_grants add constraint household_grant_named_consent
 check (revoked_at is not null or (owner_membership_id is not null and recipient_membership_id is not null and owner_membership_id<>recipient_membership_id));
create unique index household_account_grants_one_active_idx on public.household_account_grants(household_id,account_id,recipient_membership_id) where revoked_at is null;
create table public.household_command_receipts (
 actor_id uuid not null references auth.users(id) on delete cascade,
 operation text not null,
 idempotency_key text not null,
 identity_hash text not null,
 household_id uuid not null references public.households(id),
 membership_id uuid references public.household_members(id) on delete set null,
 invitation_id uuid references public.household_invitations(id) on delete set null,
 created_at timestamptz not null default now(),
 primary key(actor_id,operation,idempotency_key)
);
alter table public.household_command_receipts enable row level security;
revoke all on public.household_command_receipts from anon,authenticated;
-- Authorization records are projected only by the service, including token hashes.
revoke all on public.households,public.household_members,public.household_invitations,public.household_account_grants from anon,authenticated;
