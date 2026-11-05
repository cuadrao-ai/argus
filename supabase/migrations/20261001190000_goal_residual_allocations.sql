-- Run in one transaction with the matching Plan storage adapter. Legacy JSON writers fail
-- closed after this transactional cutover instead of creating two authorities.
begin;

lock table public.financial_goals in access exclusive mode;

create table public.financial_goal_allocations (
    goal_id uuid not null,
    goal_owner_id uuid not null,
    account_id uuid not null,
    account_owner_id uuid not null,
    unlinked_minor bigint not null check (unlinked_minor >= 0),
    ordinal integer not null check (ordinal >= 0),
    primary key (goal_id, account_id),
    unique (goal_id, ordinal),
    foreign key (goal_id, goal_owner_id)
        references public.financial_goals (id, user_id) on delete cascade,
    foreign key (account_id, account_owner_id)
        references public.financial_accounts (id, user_id) on delete cascade,
    constraint financial_goal_allocations_same_owner
        check (goal_owner_id = account_owner_id)
);
create index financial_goal_allocations_owner_order
    on public.financial_goal_allocations (goal_owner_id, goal_id, ordinal);
create index financial_goal_allocations_account_owner
    on public.financial_goal_allocations (account_id, account_owner_id);

-- Reject unknown/fractional residuals before casting. Never round, substitute
-- zero, sum duplicate accounts, or relabel another account's true owner.
do $$
begin
    if exists (
        select 1 from public.financial_goals
        where jsonb_typeof(body->'allocations') is distinct from 'array'
    ) then
        raise check_violation using message = 'Goal allocations must be an array';
    end if;
    if exists (
        select 1 from public.financial_goals g
        cross join lateral jsonb_array_elements(g.body->'allocations') a
        where jsonb_typeof(a) is distinct from 'object'
           or jsonb_typeof(a->'account_id') is distinct from 'string'
           or jsonb_typeof(a->'unlinked_minor') is distinct from 'number'
           or (a->>'unlinked_minor') !~ '^(0|[1-9][0-9]*)$'
    ) then
        raise check_violation using message = 'Goal residuals must be exact nonnegative minor units';
    end if;
end;
$$;

insert into public.financial_goal_allocations (
    goal_id, goal_owner_id, account_id, account_owner_id, unlinked_minor, ordinal
)
select g.id, g.user_id, (a.entry->>'account_id')::uuid, g.user_id,
       (a.entry->>'unlinked_minor')::bigint, a.ordinality - 1
from public.financial_goals g
cross join lateral jsonb_array_elements(g.body->'allocations')
    with ordinality as a(entry, ordinality);

-- Compare the complete row multiset in both directions before removing JSON.
-- Owners, exact amounts, explicit zero, order and count must all survive.
do $$
begin
    if exists (
        with expected as (
            select g.id as goal_id, g.user_id as goal_owner_id,
                   (a.entry->>'account_id')::uuid as account_id,
                   g.user_id as account_owner_id,
                   (a.entry->>'unlinked_minor')::bigint as unlinked_minor,
                   a.ordinality - 1 as ordinal
            from public.financial_goals g
            cross join lateral jsonb_array_elements(g.body->'allocations')
                with ordinality as a(entry, ordinality)
        )
        (select * from expected
         except all
         select goal_id, goal_owner_id, account_id, account_owner_id,
                unlinked_minor, ordinal from public.financial_goal_allocations)
        union all
        (select goal_id, goal_owner_id, account_id, account_owner_id,
                unlinked_minor, ordinal from public.financial_goal_allocations
         except all
         select * from expected)
    ) then
        raise check_violation using message = 'Goal allocation backfill is incomplete';
    end if;
end;
$$;

update public.financial_goals set body = body - 'allocations'
where body ? 'allocations';
alter table public.financial_goals add constraint financial_goals_no_json_allocations
    check (not (body ? 'allocations'));

alter table public.financial_goal_allocations enable row level security;
revoke all on public.financial_goal_allocations from public, anon, authenticated;
grant select on public.financial_goal_allocations to authenticated;
grant all on public.financial_goal_allocations to service_role;
create policy owner_read on public.financial_goal_allocations
for select to authenticated using (
    goal_owner_id = (select auth.uid())
    and account_owner_id = (select auth.uid())
    and coalesce((select auth.jwt())->>'is_anonymous', 'false') = 'false'
);

commit;
