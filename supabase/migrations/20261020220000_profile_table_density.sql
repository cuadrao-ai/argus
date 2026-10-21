-- A person's row height for dense tables (Transacciones first). Normal for
-- everyone until they choose. The API reads and writes it through PATCH /me;
-- no client grant is added.

set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.profiles
    add column table_density text not null default 'normal'
    constraint profiles_table_density_check
        check (table_density in ('compacto', 'normal', 'amplio'));

comment on column public.profiles.table_density is
    'Row height for dense tables: compacto 40px, normal 48px, amplio 56px. Type size does not change.';
