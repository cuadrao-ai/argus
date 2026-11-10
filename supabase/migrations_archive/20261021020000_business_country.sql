-- Plan: docs/specs/business-country.md
set lock_timeout = '5s';
set statement_timeout = '60s';

alter table public.spaces
    add column country text not null default 'DO',
    add column currency text not null default 'DOP',
    add constraint business_country_known check (
        kind <> 'business' or country in ('DO', 'US', 'CA')
    ),
    add constraint business_currency_shape check (
        kind <> 'business' or currency ~ '^[A-Z]{3}$'
    );

-- A Business's country selects the regime its approved records were checked
-- under, so it is set once.
create or replace function argus_private.business_country_immutable()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if old.kind = 'business' and old.country is distinct from new.country then
    raise exception 'business_country_immutable' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function argus_private.business_country_immutable()
  from public, anon, authenticated;

create trigger business_country_immutable
before update on public.spaces
for each row execute function argus_private.business_country_immutable();

reset lock_timeout;
reset statement_timeout;
