-- Status is the publisher's raw text. New values must not need a migration.
-- trade_name is null when the publisher sent no commercial name. Blank text is rejected.
-- Swap truncates and inserts so grants and row level security stay on these tables.

create table public.dgii_rnc (
    rnc text primary key check (rnc ~ '^([0-9]{9}|[0-9]{11})$'),
    name text not null check (length(btrim(name)) > 0),
    trade_name text check (trade_name is null or length(btrim(trade_name)) > 0),
    status text not null,
    file_date date not null
);

create table public.dgii_rnc_load (
    rnc text not null check (rnc ~ '^([0-9]{9}|[0-9]{11})$'),
    name text not null check (length(btrim(name)) > 0),
    trade_name text check (trade_name is null or length(btrim(trade_name)) > 0),
    status text not null,
    file_date date not null
);

alter table public.dgii_rnc enable row level security;
alter table public.dgii_rnc_load enable row level security;

revoke all on table public.dgii_rnc from public, anon, authenticated, service_role;
revoke all on table public.dgii_rnc_load from public, anon, authenticated, service_role;

grant select on table public.dgii_rnc to service_role;
grant select, insert, update, delete, truncate on table public.dgii_rnc_load to service_role;

create function public.dgii_rnc_swap(min_rows int)
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
    if min_rows < 1 then
        raise exception 'min_rows must be at least 1';
    end if;

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
    insert into public.dgii_rnc (rnc, name, trade_name, status, file_date)
    select load.rnc, load.name, load.trade_name, load.status, load.file_date
    from public.dgii_rnc_load as load;
    truncate table public.dgii_rnc_load;

    select count(*)::int into stored_rows
    from public.dgii_rnc;
    return stored_rows;
end;
$$;

create function public.dgii_rnc_lookup(p_rnc text)
returns table (
    rnc text,
    name text,
    trade_name text,
    status text,
    file_date date,
    verification text
)
language sql
stable
security definer
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
        end
    from public.dgii_rnc as registry
    where registry.rnc = nullif(
        pg_catalog.regexp_replace(coalesce(p_rnc, ''::text), '[^0-9]', '', 'g'),
        ''::text
    );
$$;

revoke all on function public.dgii_rnc_swap(int) from public, anon, authenticated;
revoke all on function public.dgii_rnc_lookup(text) from public, anon, authenticated;
grant execute on function public.dgii_rnc_swap(int), public.dgii_rnc_lookup(text) to service_role;
