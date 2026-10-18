begin;

-- The SQL checks run inside a rollback, including all synthetic rows.
do $$
declare
    relation text;
    client_role text;
    operation text;
    actual bigint;
begin
    select count(*) into actual from argus_private.retention_policies;
    if actual <> 5 then raise exception 'Expected exactly five retention rules'; end if;
    if exists (select 1 from argus_private.retention_policies where table_name not in (
        'public.business_sales',
        'public.guest_workspaces', 'public.visitor_usage_counters',
        'public.guest_funnel_milestones', 'public.cuadrao_early_access_signups'
    )) then raise exception 'An unapproved retention rule was seeded'; end if;
    select count(*) into actual from argus_private.retention_sweeps;
    if actual <> 0 then raise exception 'Migration must not claim sweeps ran'; end if;
    foreach relation in array array['retention_policies', 'retention_sweeps'] loop
        if not (select relrowsecurity from pg_class where oid =
            ('argus_private.' || relation)::regclass) then
            raise exception 'RLS is off for %', relation;
        end if;
        if exists (select 1 from pg_policy where polrelid =
            ('argus_private.' || relation)::regclass) then
            raise exception 'Unexpected RLS policy on %', relation;
        end if;
        foreach client_role in array array['anon', 'authenticated'] loop
            foreach operation in array array['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] loop
                if has_table_privilege(client_role, 'argus_private.' || relation, operation) then
                    raise exception 'Unexpected % grant for % on %', operation, client_role, relation;
                end if;
            end loop;
        end loop;
    end loop;
    if has_table_privilege('service_role', 'argus_private.retention_sweeps', 'UPDATE,DELETE,TRUNCATE') then
        raise exception 'Sweep evidence must be append-only for service_role';
    end if;
end;
$$;

set local role service_role;
insert into argus_private.retention_sweeps
    (id, table_name, started_at, finished_at, outcome, rows_affected, rule, basis)
select '00000000-0000-4000-8000-000000000001', table_name,
    now(), now(), 'succeeded', 3, rule, basis
from argus_private.retention_policies where table_name = 'public.visitor_usage_counters';

update argus_private.retention_policies set rule = 'Synthetic later rule'
    where table_name = 'public.visitor_usage_counters';

do $$
begin
    if (select rule from argus_private.retention_sweeps
        where id = '00000000-0000-4000-8000-000000000001') = 'Synthetic later rule' then
        raise exception 'Historical rule changed with policy';
    end if;
    begin
        insert into argus_private.retention_sweeps select * from argus_private.retention_sweeps;
        raise exception 'Duplicate run ID accepted';
    exception when unique_violation then null;
    end;
    begin
        update argus_private.retention_sweeps set rows_affected = 100;
        raise exception 'Sweep update allowed';
    exception when insufficient_privilege then null;
    end;
    begin
        delete from argus_private.retention_sweeps;
        raise exception 'Sweep delete allowed';
    exception when insufficient_privilege then null;
    end;
end;
$$;

insert into argus_private.retention_sweeps
    (table_name, started_at, finished_at, outcome, rows_affected, rule, basis)
values ('public.visitor_usage_counters', now(), now(), 'failed', null, 'test rule', 'test owner'),
       ('public.visitor_usage_counters', now(), now(), 'dry_run', 0, 'test rule', 'test owner');

do $$
declare
    invalid_case record;
begin
    for invalid_case in select * from (values
        ('unknown.table', now(), 'succeeded', 0::bigint, 'rule', 'owner'),
        ('public.visitor_usage_counters', now() - interval '1 second', 'succeeded', 0, 'rule', 'owner'),
        ('public.visitor_usage_counters', now(), 'running', 0, 'rule', 'owner'),
        ('public.visitor_usage_counters', now(), 'succeeded', -1, 'rule', 'owner'),
        ('public.visitor_usage_counters', now(), 'succeeded', null, 'rule', 'owner'),
        ('public.visitor_usage_counters', now(), 'dry_run', 1, 'rule', 'owner'),
        ('public.visitor_usage_counters', now(), 'succeeded', 0, ' ', 'owner'),
        ('public.visitor_usage_counters', now(), 'succeeded', 0, 'rule', ' ')
    ) as cases(table_name, finished_at, outcome, rows_affected, rule, basis) loop
        begin
            insert into argus_private.retention_sweeps
                (table_name, started_at, finished_at, outcome, rows_affected, rule, basis)
            values (invalid_case.table_name, now(), invalid_case.finished_at,
                invalid_case.outcome, invalid_case.rows_affected, invalid_case.rule, invalid_case.basis);
            raise exception 'Invalid sweep accepted: %', invalid_case;
        exception when check_violation or foreign_key_violation then null;
        end;
    end loop;
    begin
        insert into argus_private.retention_policies values ('not qualified', 'rule', 'owner');
        raise exception 'Unqualified table accepted';
    exception when check_violation then null;
    end;
end;
$$;
reset role;
rollback;
