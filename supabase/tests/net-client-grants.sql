\set ON_ERROR_STOP on
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

-- Strict acceptance for the requested revocation. It currently fails on the
-- supported Supabase image because supabase_admin owns the extension grants.
do $$
declare v_exposed text;
begin
    select string_agg(object_name || ':' || grantee || ':' || privilege_type, ', ' order by object_name, grantee, privilege_type)
    into v_exposed
    from (
        select 'net' as object_name, a.grantee, a.privilege_type
        from pg_namespace n
        cross join lateral aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a
        where n.nspname = 'net'
        union all
        select p.oid::regprocedure::text, a.grantee, a.privilege_type
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
        where n.nspname = 'net'
        union all
        select c.oid::regclass::text, a.grantee, a.privilege_type
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a
        where n.nspname = 'net' and c.relkind in ('r', 'p', 'v', 'm', 'f', 'S')
    ) grants
    where grantee in (0, 'anon'::regrole::oid, 'authenticated'::regrole::oid);
    if v_exposed is not null then
        raise exception 'BLOCKED: net still grants client or PUBLIC privileges: %', v_exposed;
    end if;
    if to_regnamespace('net') is null then
        raise exception 'BLOCKED: net extension schema is missing';
    end if;
end;
$$;
rollback;
