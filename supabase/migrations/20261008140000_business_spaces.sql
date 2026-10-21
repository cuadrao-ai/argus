-- Business spaces: one open Business space per person, and the owner_space_id
-- column on the rows that belong to it.
-- Plan: docs/specs/lanes/cuadrao-business-space-slice-plan.md, section 1.
--
-- Null rule: owner_space_id is null means Personal. There is no Personal
-- backfill. user_id stays the person, so account deletion and Storage paths
-- keep their key. Every owner_space_id is pinned to its row's own user_id by a
-- composite key to spaces (id, created_by), so a row can never name another
-- person's space. Only root rows store the space (accounts, connections,
-- import events, conversations); their children inherit it. #819 may later add
-- a Personal space per person and space_memberships without re-keying any
-- record, because records reference spaces(id).

-- M1
create table if not exists public.spaces (
    id uuid primary key default gen_random_uuid(),
    kind text not null check (kind = 'business'),
    name text not null check (char_length(name) between 1 and 80),
    created_by uuid not null references auth.users(id) on delete cascade,
    created_at timestamptz not null default now(),
    closed_at timestamptz,
    unique (id, created_by)
);

-- M2
create unique index if not exists spaces_one_open_business_idx
    on public.spaces (created_by)
    where kind = 'business' and closed_at is null;

-- The one SQL owner of "person to space".
create or replace function public.business_space_of(p_owner uuid)
returns uuid
language sql
stable
set search_path = ''
as $$
    select s.id
      from public.spaces s
     where s.created_by = p_owner
       and s.kind = 'business'
       and s.closed_at is null;
$$;

-- M3, M4
alter table public.financial_accounts
    add column owner_space_id uuid,
    add constraint financial_accounts_owner_space_fkey
        foreign key (owner_space_id, user_id)
        references public.spaces (id, created_by) on delete cascade;
create index if not exists financial_accounts_owner_space_idx
    on public.financial_accounts (owner_space_id)
    where owner_space_id is not null;

alter table public.financial_source_connections
    add column owner_space_id uuid,
    add constraint financial_source_connections_owner_space_fkey
        foreign key (owner_space_id, user_id)
        references public.spaces (id, created_by) on delete cascade;
create index if not exists financial_source_connections_owner_space_idx
    on public.financial_source_connections (owner_space_id)
    where owner_space_id is not null;

alter table public.conversations
    add column owner_space_id uuid,
    add constraint conversations_owner_space_fkey
        foreign key (owner_space_id, user_id)
        references public.spaces (id, created_by) on delete cascade;
create index if not exists conversations_owner_space_idx
    on public.conversations (owner_space_id)
    where owner_space_id is not null;

alter table public.financial_import_events
    add column owner_space_id uuid,
    add constraint financial_import_events_owner_space_fkey
        foreign key (owner_space_id, user_id)
        references public.spaces (id, created_by) on delete cascade;
create index if not exists financial_import_events_owner_space_idx
    on public.financial_import_events (owner_space_id)
    where owner_space_id is not null;

-- M5
create or replace function argus_private.require_import_observation_same_space()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (select c.owner_space_id from public.financial_source_connections c
       where c.id = new.connection_id)
     is distinct from
     (select e.owner_space_id from public.financial_import_events e
       where e.id = new.event_id and e.user_id = new.user_id) then
    raise exception 'import_observation_space_mismatch' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function argus_private.require_import_observation_same_space()
  from public, anon, authenticated;

drop trigger if exists import_observation_same_space on public.financial_import_observations;
create trigger import_observation_same_space
before insert or update on public.financial_import_observations
for each row execute function argus_private.require_import_observation_same_space();

-- M6
alter table public.whatsapp_sender_links
    add column destination_space_id uuid not null,
    add constraint whatsapp_sender_links_destination_space_fkey
        foreign key (destination_space_id, destination_owner_id)
        references public.spaces (id, created_by) on delete cascade;
create index if not exists whatsapp_sender_links_destination_space_idx
    on public.whatsapp_sender_links (destination_space_id);

create or replace function argus_private.fill_sender_link_space()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  new.destination_space_id := coalesce(
    new.destination_space_id, public.business_space_of(new.destination_owner_id)
  );
  if new.destination_space_id is null then
    raise exception 'business_space_missing' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function argus_private.fill_sender_link_space()
  from public, anon, authenticated;

drop trigger if exists fill_sender_link_space on public.whatsapp_sender_links;
create trigger fill_sender_link_space
before insert on public.whatsapp_sender_links
for each row execute function argus_private.fill_sender_link_space();

-- M7
create or replace function argus_private.require_whatsapp_capture_same_space()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (
    select 1
      from public.financial_source_connections c
      join public.whatsapp_sender_links l
        on l.destination_owner_id = c.user_id
       and l.destination_space_id = c.owner_space_id
       and l.status = 'active'
     where c.id = new.connection_id
       and c.user_id = new.destination_owner_id
  ) then
    raise exception 'whatsapp_capture_space_mismatch' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function argus_private.require_whatsapp_capture_same_space()
  from public, anon, authenticated;

drop trigger if exists whatsapp_capture_same_space on public.whatsapp_inbound_messages;
create trigger whatsapp_capture_same_space
before insert or update on public.whatsapp_inbound_messages
for each row
when (new.connection_id is not null)
execute function argus_private.require_whatsapp_capture_same_space();

-- M8
create or replace function argus_private.refuse_business_account_grant()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if exists (
    select 1 from public.financial_accounts a
     where a.id = new.account_id and a.owner_space_id is not null
  ) then
    raise exception 'business_account_not_shareable' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function argus_private.refuse_business_account_grant()
  from public, anon, authenticated;

drop trigger if exists refuse_business_account_grant on public.household_account_grants;
create trigger refuse_business_account_grant
before insert or update on public.household_account_grants
for each row execute function argus_private.refuse_business_account_grant();

-- M9: the 20261004090000 body, with one guard before the account copy.
create or replace function argus_private.deletion_place_unit(
  p_user_id uuid,
  p_unit_kind text,
  p_unit_id uuid,
  p_placeholder_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_binding public.household_plan_bindings%rowtype;
  v_member public.household_members%rowtype;
  v_placeholder_mid uuid;
  v_number integer;
  v_participant public.household_plan_participants%rowtype;
  v_debt_copy uuid;
  v_from uuid[];
  v_to uuid[];
  v_used boolean := false;
begin
  perform argus_private.require_deletion_writer();
  if current_user <> 'postgres' then
    raise exception 'account_deletion_writer_required' using errcode = '42501';
  end if;
  if not exists (select 1 from argus_private.account_placeholders where id = p_placeholder_id)
     or not exists (select 1 from auth.users where id = p_placeholder_id) then
    raise exception 'account_deletion_placeholder_missing' using errcode = 'P0002';
  end if;
  perform argus_private.defer_deletion_keys();

  -- One id map per placeholder for the whole transaction, shared by every
  -- kind: a single-leg activity has its record's id, so the copies must too.
  -- Two plans in one household that pin the same activity share one copy.
  create temp table if not exists deletion_id_map (placeholder_id uuid, old_id uuid, new_id uuid not null, primary key (placeholder_id, old_id)) on commit drop;
  create temp table if not exists deletion_copied (placeholder_id uuid, kind text, old_id uuid, primary key (placeholder_id, kind, old_id)) on commit drop;
  create temp table if not exists deletion_unit_ids (kind text, old_id uuid, primary key (kind, old_id)) on commit drop;
  create temp table if not exists deletion_fresh_ids (kind text, old_id uuid, primary key (kind, old_id)) on commit drop;
  truncate pg_temp.deletion_unit_ids, pg_temp.deletion_fresh_ids;

  if p_unit_kind = 'plan' then
    select * into v_binding from public.household_plan_bindings where id = p_unit_id for update;
    if not found then
      return false;
    end if;
    insert into pg_temp.deletion_unit_ids
    select 'activity', a from (
      select l.activity_id as a from public.financial_plan_links l
       where l.binding_id = p_unit_id and l.activity_owner_id = p_user_id
      union select activity_id from public.household_plan_archived_claims
       where binding_id = p_unit_id and activity_owner_id = p_user_id
      union select activity_id from public.household_plan_archived_activities
       where binding_id = p_unit_id and activity_owner_id = p_user_id
    ) s
    where argus_private.deletion_activity_household(a) = v_binding.household_id
    on conflict do nothing;
    insert into pg_temp.deletion_unit_ids
    select 'account', a from (
      select account_id as a from public.financial_goal_allocation_revisions
       where binding_id = p_unit_id and account_owner_id = p_user_id
      union
      select d.debt_account_id from public.financial_debt_plans d
       where v_binding.kind = 'debt' and v_binding.owner_user_id = p_user_id
         and d.id = v_binding.definition_id and d.user_id = p_user_id
    ) s
    where a is not null
    on conflict do nothing;
  elsif p_unit_kind = 'group' then
    if exists (select 1 from public.financial_activity_groups where id = p_unit_id and user_id = p_user_id) then
      insert into pg_temp.deletion_unit_ids values ('activity', p_unit_id) on conflict do nothing;
    else
      insert into pg_temp.deletion_unit_ids
      select distinct 'record', m.record_id from public.financial_activity_memberships m
       where m.activity_id = p_unit_id and m.record_owner_id = p_user_id
      on conflict do nothing;
    end if;
  else
    raise exception 'account_deletion_unit_invalid' using errcode = '22023';
  end if;

  -- The person's own legs in the copied activities, and the accounts they sit in.
  insert into pg_temp.deletion_unit_ids
  select distinct 'record', m.record_id from public.financial_activity_memberships m
   where m.activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity')
     and m.user_id = p_user_id and m.record_owner_id = p_user_id
  on conflict do nothing;
  insert into pg_temp.deletion_unit_ids
  select distinct 'account', r.account_id from public.financial_records r
   where r.id in (select old_id from pg_temp.deletion_unit_ids where kind = 'record')
  on conflict do nothing;

  -- Activities and records move in place: they keep their ids, revisions
  -- and timestamps, because other people's legs and links name them by id.
  -- Accounts are copied (new ids), since an account also holds rows that go
  -- with the person. An id map per placeholder covers the account copies for
  -- the whole transaction, so units of one scope share one copy.
  insert into pg_temp.deletion_id_map
  select distinct p_placeholder_id, old_id, gen_random_uuid() from pg_temp.deletion_unit_ids
   where kind = 'account'
  on conflict do nothing;
  insert into pg_temp.deletion_fresh_ids
  select u.kind, u.old_id from pg_temp.deletion_unit_ids u
   where u.kind = 'account' and not exists (
     select 1 from pg_temp.deletion_copied c
      where c.placeholder_id = p_placeholder_id and c.kind = u.kind and c.old_id = u.old_id);
  insert into pg_temp.deletion_copied select p_placeholder_id, kind, old_id from pg_temp.deletion_fresh_ids;

  select array_agg(old_id order by old_id), array_agg(new_id order by old_id)
    into v_from, v_to
    from (
      select old_id, new_id from pg_temp.deletion_id_map where placeholder_id = p_placeholder_id
      union all select p_user_id, p_placeholder_id
    ) ids;

  -- The copy below names its columns, so a Business account would silently
  -- become a Personal account of the placeholder.
  if exists (
    select 1 from public.financial_accounts a
      join pg_temp.deletion_unit_ids u on u.kind = 'account' and u.old_id = a.id
     where a.owner_space_id is not null
  ) then
    raise exception 'business_account_in_copy' using errcode = 'P0001';
  end if;

  insert into public.financial_accounts
      (id, user_id, space_id, type, currency, nickname, archived, ownership_share_bps, version, created_at, updated_at)
  select m.new_id, p_placeholder_id, a.space_id, a.type, a.currency, null, a.archived,
         a.ownership_share_bps, 1, a.created_at, now()
    from public.financial_accounts a
    join pg_temp.deletion_id_map m on m.placeholder_id = p_placeholder_id and m.old_id = a.id
    join pg_temp.deletion_fresh_ids f on f.kind = 'account' and f.old_id = a.id;

  -- The person's own receipts and import coverage on the moving rows go with
  -- them (their keys are not deferrable and name the person).
  delete from public.financial_activity_receipts
   where user_id = p_user_id
     and activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity');
  delete from public.financial_operation_receipts
   where user_id = p_user_id
     and record_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'record');
  delete from public.financial_observation_coverage
   where user_id = p_user_id
     and (activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'record')
          or observation_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'record'));

  update public.financial_activity_groups
     set user_id = p_placeholder_id
   where id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity')
     and user_id = p_user_id;
  update public.financial_activity_revisions
     set user_id = p_placeholder_id
   where activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity')
     and user_id = p_user_id;
  update public.financial_records r
     set user_id = p_placeholder_id, account_id = m.new_id
    from pg_temp.deletion_id_map m
   where r.id in (select old_id from pg_temp.deletion_unit_ids where kind = 'record')
     and r.user_id = p_user_id
     and m.placeholder_id = p_placeholder_id and m.old_id = r.account_id;
  -- Kept history holds amount, date, category and currency: notes, source ids
  -- and correction reasons are dropped and recorded_by cleared. purchase_* and
  -- reversal_* are generated from details; a link to one of the person's own
  -- activities that did not move with this placeholder is dropped.
  update public.financial_record_revisions rr
     set user_id = p_placeholder_id,
         recorded_by = null,
         reason = null,
         details = argus_private.deletion_rewrite_ids(
           (case when rr.details ? 'reversal_of_activity_id'
                      and coalesce((rr.details ->> 'reversal_of_owner_id')::uuid, rr.user_id) = p_user_id
                      and not exists (select 1 from public.financial_activity_groups g
                                       where g.id = (rr.details ->> 'reversal_of_activity_id')::uuid
                                         and g.user_id = p_placeholder_id)
                 then rr.details - 'reversal_of_activity_id' - 'reversal_of_revision' - 'reversal_of_owner_id'
                 else rr.details end)
           - (case when rr.details ? 'purchase_activity_id'
                        and not exists (select 1 from public.financial_activity_groups g
                                         where g.id = (rr.details ->> 'purchase_activity_id')::uuid
                                           and g.user_id = p_placeholder_id)
                   then array['purchase_activity_id', 'purchase_revision'] else array[]::text[] end)
           - 'note' - 'source_id',
           v_from, v_to)
   where rr.record_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'record')
     and rr.user_id = p_user_id;
  update public.financial_activity_memberships
     set user_id = p_placeholder_id
   where activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity')
     and user_id = p_user_id;
  update public.financial_activity_memberships
     set record_owner_id = p_placeholder_id
   where record_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'record')
     and record_owner_id = p_user_id;

  -- Every claim or archive on a moved activity, in any plan, follows it now:
  -- the activity's key holds it immediate at the end of this call. In another
  -- household's plan it is the read-only reference of decision c. The
  -- person's own personal claims on it go with them (5.3 deletes the rest).
  delete from public.financial_plan_links
   where binding_id is null and user_id = p_user_id
     and activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity');
  update public.financial_plan_links l
     set activity_owner_id = p_placeholder_id,
         attribution = argus_private.deletion_rewrite_ids(l.attribution, v_from, v_to)
   where l.binding_id is not null and l.binding_id is distinct from p_unit_id
     and l.activity_owner_id = p_user_id
     and l.activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity');
  update public.household_plan_archived_claims c
     set activity_owner_id = p_placeholder_id
   where c.binding_id is distinct from p_unit_id and c.activity_owner_id = p_user_id
     and c.activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity');
  update public.household_plan_archived_activities c
     set activity_owner_id = p_placeholder_id
   where c.binding_id is distinct from p_unit_id and c.activity_owner_id = p_user_id
     and c.activity_id in (select old_id from pg_temp.deletion_unit_ids where kind = 'activity');

  v_used := exists (select 1 from pg_temp.deletion_unit_ids);

  if p_unit_kind = 'plan' then
    -- Claims, archives and allocation history of this plan point at the copies.
    update public.financial_plan_links l
       set activity_owner_id = g.user_id
      from public.financial_activity_groups g
     where l.binding_id = p_unit_id and l.activity_owner_id = p_user_id
       and g.id = l.activity_id and g.user_id <> p_user_id;
    -- Every claim's accepted legs name accounts; the person's now have copies.
    update public.financial_plan_links l
       set attribution = argus_private.deletion_rewrite_ids(l.attribution, v_from, v_to)
     where l.binding_id = p_unit_id and l.attribution is not null;
    update public.household_plan_archived_claims c
       set activity_owner_id = g.user_id
      from public.financial_activity_groups g
     where c.binding_id = p_unit_id and c.activity_owner_id = p_user_id
       and g.id = c.activity_id and g.user_id <> p_user_id;
    update public.household_plan_archived_activities c
       set activity_owner_id = g.user_id
      from public.financial_activity_groups g
     where c.binding_id = p_unit_id and c.activity_owner_id = p_user_id
       and g.id = c.activity_id and g.user_id <> p_user_id;
    update public.financial_goal_allocation_revisions r
       set account_id = m.new_id, account_owner_id = p_placeholder_id
      from pg_temp.deletion_id_map m
     where m.placeholder_id = p_placeholder_id and r.binding_id = p_unit_id and r.account_owner_id = p_user_id and r.account_id = m.old_id;
    -- Live backing from the person's accounts ends; the archive keeps it.
    delete from public.financial_goal_allocations
     where binding_id = p_unit_id and account_owner_id = p_user_id;

    -- The household's one Exmiembro membership for this person, shared by
    -- every plan of theirs in the household. former_member_number orders the
    -- household's former members; plan reads number them per plan.
    select * into v_member from public.household_members
     where household_id = v_binding.household_id and user_id = p_user_id
     order by joined_at desc, id desc limit 1;
    if found then
      select id into v_placeholder_mid from public.household_members
       where household_id = v_binding.household_id and user_id = p_placeholder_id;
      if v_placeholder_mid is null then
        select coalesce(max(former_member_number), 0) + 1 into v_number
          from public.household_members
         where household_id = v_binding.household_id and former_member_number is not null;
        v_placeholder_mid := gen_random_uuid();
        insert into public.household_members
            (id, household_id, user_id, joined_at, left_at, display_name, former_member_number)
        values (v_placeholder_mid, v_binding.household_id, p_placeholder_id, v_member.joined_at,
                coalesce(v_member.left_at, now()), 'Exmiembro', v_number);
      end if;
      select * into v_participant from public.household_plan_participants
       where binding_id = p_unit_id
         and membership_id in (select id from public.household_members
                                where household_id = v_binding.household_id and user_id = p_user_id)
       order by joined_at limit 1;
      insert into public.household_plan_participants
          (binding_id, household_id, membership_id, permission, revoked_at, granted_revision, joined_at)
      values (p_unit_id, v_binding.household_id, v_placeholder_mid,
              coalesce(v_participant.permission, 'view'),
              coalesce(v_participant.revoked_at, now()),
              coalesce(v_participant.granted_revision, v_binding.first_shared_revision),
              coalesce(v_participant.joined_at, v_member.joined_at));
      delete from public.household_plan_participants
       where binding_id = p_unit_id
         and membership_id in (select id from public.household_members
                                where household_id = v_binding.household_id and user_id = p_user_id);
      update public.financial_plan_links
         set contributor_membership_id = v_placeholder_mid
       where binding_id = p_unit_id
         and contributor_membership_id in (select id from public.household_members where user_id = p_user_id);
      update public.financial_goal_allocations
         set contributor_membership_id = v_placeholder_mid
       where binding_id = p_unit_id
         and contributor_membership_id in (select id from public.household_members where user_id = p_user_id);
      update public.financial_goal_allocation_revisions
         set contributor_membership_id = v_placeholder_mid
       where binding_id = p_unit_id
         and contributor_membership_id in (select id from public.household_members where user_id = p_user_id);
      update public.financial_plan_responsibilities r
         set membership_id = v_placeholder_mid
       where r.kind = v_binding.kind and r.definition_id = v_binding.definition_id
         and r.owner_id = v_binding.owner_user_id
         and r.membership_id in (select id from public.household_members where user_id = p_user_id);
      delete from public.household_plan_receipts
       where binding_id = p_unit_id
         and (actor_id = p_user_id
              or membership_id in (select id from public.household_members where user_id = p_user_id));
      v_used := true;

      -- A read-only archive the person still owns (shared debt plans, Lucas,
      -- Oct 2) moves to this placeholder together with its debt account.
      if v_binding.owner_user_id = p_user_id then
        if v_binding.kind = 'debt' then
          select m.new_id into v_debt_copy
            from public.financial_debt_plans d
            join pg_temp.deletion_id_map m
              on m.placeholder_id = p_placeholder_id and m.old_id = d.debt_account_id
           where d.id = v_binding.definition_id and d.user_id = p_user_id;
        end if;
        perform argus_private.deletion_rekey_binding(
          p_unit_id, p_user_id, p_placeholder_id, v_placeholder_mid, v_debt_copy
        );
      end if;
    end if;
  end if;

  set constraints all immediate;
  return v_used;
end;
$$;

revoke all on function argus_private.deletion_place_unit(uuid, text, uuid, uuid)
  from public, anon, authenticated;

-- M10: the 20260928200000 function with a trailing space. The default keeps
-- the ten-argument callers working, as Personal. A Business create folds the
-- space into the stored identity, so a key replayed across spaces conflicts;
-- a Personal identity stays byte-identical to the one stored before.
drop function if exists public.create_financial_account(
    uuid, text, text, text, text, text, integer, bigint, timestamptz, text
);

create function public.create_financial_account(
    p_user_id uuid,
    p_idempotency_key text,
    p_identity_hash text,
    p_type text,
    p_currency text,
    p_nickname text,
    p_ownership_share_bps integer,
    p_opening_amount_minor bigint,
    p_opening_as_of timestamptz,
    p_opening_zone text,
    p_owner_space_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_reserved public.financial_account_idempotency%rowtype;
    v_account_id uuid;
    v_record_id uuid;
    v_now timestamptz := now();
    v_identity_hash text := p_identity_hash
        || coalesce(':space:' || p_owner_space_id::text, '');
begin
    if not exists (
        select 1 from auth.users u
        where u.id = p_user_id and coalesce(u.is_anonymous, false) = false
    ) then
        return jsonb_build_object('decision', 'registered_required');
    end if;

    select * into v_reserved
    from public.financial_account_idempotency
    where user_id = p_user_id
      and operation_scope = 'financial_accounts.create'
      and idempotency_key = p_idempotency_key
    for update;
    if found then
        if v_reserved.identity_hash = v_identity_hash then
            return jsonb_build_object('decision', 'replay', 'account_id', v_reserved.account_id);
        end if;
        return jsonb_build_object('decision', 'conflict');
    end if;

    begin
        insert into public.financial_accounts (
            user_id, owner_space_id, type, currency, nickname, ownership_share_bps,
            created_at, updated_at
        )
        values (
            p_user_id, p_owner_space_id, p_type, p_currency, p_nickname,
            p_ownership_share_bps, v_now, v_now
        )
        returning id into v_account_id;

        if p_opening_amount_minor is not null then
            insert into public.financial_records (account_id, user_id, record_kind, created_at)
            values (v_account_id, p_user_id, 'opening_balance', v_now)
            returning id into v_record_id;
            insert into public.financial_record_revisions (
                record_id, user_id, revision, amount_minor, as_of, as_of_zone,
                reason, recorded_by, recorded_at
            )
            values (
                v_record_id, p_user_id, 1, p_opening_amount_minor, p_opening_as_of,
                p_opening_zone, null, p_user_id, v_now
            );
        end if;

        insert into public.financial_account_idempotency (
            user_id, operation_scope, idempotency_key, identity_hash, account_id, created_at
        )
        values (
            p_user_id, 'financial_accounts.create', p_idempotency_key,
            v_identity_hash, v_account_id, v_now
        );
    exception when unique_violation then
        -- A concurrent request with the same key committed first. Decide from
        -- its committed row; this transaction's account insert rolls back.
        select * into v_reserved
        from public.financial_account_idempotency
        where user_id = p_user_id
          and operation_scope = 'financial_accounts.create'
          and idempotency_key = p_idempotency_key;
        if v_reserved.identity_hash = v_identity_hash then
            return jsonb_build_object('decision', 'replay', 'account_id', v_reserved.account_id);
        end if;
        return jsonb_build_object('decision', 'conflict');
    end;

    return jsonb_build_object('decision', 'created', 'account_id', v_account_id);
end;
$$;

revoke all on function public.create_financial_account(
    uuid, text, text, text, text, text, integer, bigint, timestamptz, text, uuid
) from public, anon, authenticated;
grant execute on function public.create_financial_account(
    uuid, text, text, text, text, text, integer, bigint, timestamptz, text, uuid
) to service_role;

-- M11. No client policies: row level security with none denies every client
-- role. owner_space_id stays out of the connections column grant.
alter table public.spaces enable row level security;
revoke all on public.spaces from public, anon, authenticated;
grant all on public.spaces to service_role;

revoke all on function public.business_space_of(uuid) from public, anon, authenticated;
grant execute on function public.business_space_of(uuid) to service_role;

-- M12
comment on table public.spaces is
    'A Business space, owned by created_by. One open Business space per person. '
    'Rows that belong to it carry owner_space_id; null means Personal. #819 may '
    'add a Personal space per person and space_memberships backfilled from '
    'created_by, without re-keying any record.';
comment on function public.business_space_of(uuid) is
    'The one SQL owner of person to space: the open Business space of p_owner, '
    'or null.';
comment on column public.financial_accounts.owner_space_id is
    'The Business space this account belongs to; null means Personal. Pinned to '
    'user_id by financial_accounts_owner_space_fkey. Unrelated to the free-text '
    'space_id.';
comment on column public.financial_source_connections.owner_space_id is
    'The Business space this connection belongs to; null means Personal. Pinned '
    'to user_id. Not client-readable.';
comment on column public.conversations.owner_space_id is
    'The Business space this conversation belongs to; null means Personal. '
    'Pinned to user_id.';
comment on column public.financial_import_events.owner_space_id is
    'Copy of the space of every observation''s connection, set when the event '
    'is created; null means Personal. import_observation_same_space keeps the '
    'copies equal.';
comment on trigger import_observation_same_space on public.financial_import_observations is
    'Raises import_observation_space_mismatch unless the connection and the '
    'event have the same owner_space_id (null meaning Personal).';
comment on table public.whatsapp_sender_links is
    'A verified link from one sending WhatsApp number to one Business space. '
    'destination_owner_id is the person who owns that space, not a business '
    'principal; destination_space_id is the space captured receipts land in. '
    'Link codes and inbound messages keep only destination_owner_id.';
comment on column public.whatsapp_sender_links.destination_space_id is
    'The Business space captures land in. Filled from business_space_of '
    '(destination_owner_id) when the insert leaves it null; pinned to '
    'destination_owner_id.';
comment on trigger fill_sender_link_space on public.whatsapp_sender_links is
    'Fills destination_space_id from business_space_of, and raises '
    'business_space_missing when the owner has no open Business space.';
comment on trigger whatsapp_capture_same_space on public.whatsapp_inbound_messages is
    'Raises whatsapp_capture_space_mismatch unless connection_id belongs to '
    'destination_owner_id and to the space of that owner''s active sender link.';
comment on trigger refuse_business_account_grant on public.household_account_grants is
    'Raises business_account_not_shareable: a Business account is never granted '
    'to a household.';
