-- The swap publishes the load table by renaming it, so a reload holds two copies
-- of the registry at its peak instead of three.
-- Both tables share their check constraint names, so a swap changes no name.
-- Grants stay with a table through a rename, so the swap sets each table's own.

alter table public.dgii_rnc_load rename constraint dgii_rnc_load_rnc_check to dgii_rnc_rnc_check;
alter table public.dgii_rnc_load rename constraint dgii_rnc_load_name_check to dgii_rnc_name_check;
alter table public.dgii_rnc_load rename constraint dgii_rnc_load_trade_name_check to dgii_rnc_trade_name_check;
alter table public.dgii_rnc_load rename constraint dgii_rnc_load_activity_check to dgii_rnc_activity_check;
alter table public.dgii_rnc_load rename constraint dgii_rnc_load_regime_check to dgii_rnc_regime_check;

create or replace function public.dgii_rnc_swap(min_rows int)
returns int
language plpgsql
security definer
set search_path = ''
as $$
declare
    load_rows bigint;
    duplicate_rncs bigint;
begin
    if min_rows is null or min_rows < 1 then
        raise exception 'min_rows must be at least 1';
    end if;

    lock table public.dgii_rnc_load in access exclusive mode;

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

    -- Built before the registry lock, so lookups keep running while the key builds.
    alter table public.dgii_rnc_load add constraint dgii_rnc_load_pkey primary key (rnc);

    lock table public.dgii_rnc in access exclusive mode;
    alter table public.dgii_rnc drop constraint dgii_rnc_pkey;
    alter table public.dgii_rnc rename to dgii_rnc_previous;
    alter table public.dgii_rnc_load rename to dgii_rnc;
    alter table public.dgii_rnc_previous rename to dgii_rnc_load;
    alter table public.dgii_rnc rename constraint dgii_rnc_load_pkey to dgii_rnc_pkey;
    truncate table public.dgii_rnc_load;

    revoke all on table public.dgii_rnc from public, anon, authenticated, service_role;
    revoke all on table public.dgii_rnc_load from public, anon, authenticated, service_role;
    grant select on table public.dgii_rnc to service_role;
    grant select, insert, update, delete, truncate on table public.dgii_rnc_load to service_role;

    return load_rows;
end;
$$;
