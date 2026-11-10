-- activity, start_date and regime come from the publisher's CSV.
-- Each one is null when the file leaves it blank or the date does not parse.
-- The lookup changes its return type, so it is dropped and created again.

alter table public.dgii_rnc
    add column activity text check (activity is null or length(btrim(activity)) > 0),
    add column start_date date,
    add column regime text check (regime is null or length(btrim(regime)) > 0);

alter table public.dgii_rnc_load
    add column activity text check (activity is null or length(btrim(activity)) > 0),
    add column start_date date,
    add column regime text check (regime is null or length(btrim(regime)) > 0);

create or replace function public.dgii_rnc_swap(min_rows int)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
    load_rows bigint;
    duplicate_rncs bigint;
    stored_rows int;
begin
    if min_rows is null or min_rows < 1 then
        raise exception 'min_rows must be at least 1';
    end if;

    lock table public.dgii_rnc_load in exclusive mode;

    select count(*) into load_rows
    from public.dgii_rnc_load;
    if load_rows < min_rows then
        raise exception
            'dgii_rnc_load has % rows, fewer than the minimum %',
            load_rows,
            min_rows;
    end if;

    select count(*) into duplicate_rncs
    from (
        select load.rnc
        from public.dgii_rnc_load as load
        group by load.rnc
        having count(*) > 1
    ) as duplicates;
    if duplicate_rncs > 0 then
        raise exception 'dgii_rnc_load duplicate rnc count %', duplicate_rncs;
    end if;

    lock table public.dgii_rnc in access exclusive mode;
    truncate table public.dgii_rnc;
    insert into public.dgii_rnc (
        rnc, name, trade_name, status, file_date, activity, start_date, regime
    )
    select
        load.rnc,
        load.name,
        load.trade_name,
        load.status,
        load.file_date,
        load.activity,
        load.start_date,
        load.regime
    from public.dgii_rnc_load as load;
    truncate table public.dgii_rnc_load;

    select count(*)::int into stored_rows
    from public.dgii_rnc;
    return stored_rows;
end;
$$;

drop function public.dgii_rnc_lookup(text);

create function public.dgii_rnc_lookup(p_rnc text)
returns table (
    rnc text,
    name text,
    trade_name text,
    status text,
    file_date date,
    verification text,
    activity text,
    start_date date,
    regime text
)
language sql
volatile
set search_path = ''
as $$
    select
        registry.rnc,
        registry.name,
        registry.trade_name,
        registry.status,
        registry.file_date,
        case
            when pg_catalog.upper(pg_catalog.btrim(registry.status)) = 'ACTIVO'
                then 'verificado'
            else 'no_activo'
        end,
        registry.activity,
        registry.start_date,
        registry.regime
    from public.dgii_rnc as registry
    where registry.rnc = nullif(
        pg_catalog.regexp_replace(coalesce(p_rnc, ''::text), '[^0-9]', '', 'g'),
        ''::text
    );
$$;

revoke all on function public.dgii_rnc_lookup(text) from public, anon, authenticated;
grant execute on function public.dgii_rnc_lookup(text) to service_role;
