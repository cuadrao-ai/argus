-- Coordinated service/schema cutover: ended membership pins authorized facts.
-- Current Goal backing becomes unknown; last authorized support is history only.
begin;
lock table public.household_members, public.household_plan_bindings,
 public.financial_plan_links, public.financial_goal_allocations in share row exclusive mode;

alter table public.household_plan_archived_claims
 add column membership_ended_at timestamptz,
 add column last_applied_minor bigint;
alter table public.household_plan_archived_allocations
 add column membership_ended_at timestamptz,
 add column last_supported_minor bigint check(last_supported_minor>=0),
 add column owner_archived boolean not null default true;
alter table public.household_plan_archived_allocations
 drop constraint household_plan_archived_allocations_pkey;
alter table public.household_plan_archived_allocations
 add primary key(binding_id,allocation_id,revision);

-- A prior unrecorded departure cannot be repaired using today's private facts.
-- Reject incomplete legacy consent rather than invent an authorized old revision.
do $$ begin
 if exists (
  select 1 from public.financial_plan_links l
  join public.household_members m on m.id=l.contributor_membership_id
  join public.household_plan_bindings b on b.id=l.binding_id
  where m.left_at is not null and b.departed_at is null and b.revoked_at is null
 ) or exists (
  select 1 from public.financial_goal_allocations a
  join public.household_members m on m.id=a.contributor_membership_id
  join public.household_plan_bindings b on b.id=a.binding_id
  where m.left_at is not null and b.departed_at is null and b.revoked_at is null
 ) then
  raise exception 'missing last authorized contributor facts: recover verified historical consent before cutover'
   using errcode='23514';
 end if;
end $$;

-- Existing exact revision FKs, RESTRICT lifetimes, RLS and denied authenticated
-- table reads remain in force. Only canonical service readers select these caps.
commit;
