begin;

create table public.business_receipt_reading_consents (
  id uuid primary key default gen_random_uuid(),
  space_id uuid not null references public.spaces(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  scope_version integer not null check (scope_version = 1),
  route jsonb not null,
  idempotency_key text not null check (length(idempotency_key) between 1 and 80),
  request_hash text not null check (length(request_hash)=64),
  unique (space_id,owner_id,idempotency_key),
  disclosure text not null check (length(disclosure) between 1 and 2000),
  consented_at timestamptz not null default clock_timestamp(),
  revoked_at timestamptz,
  check (revoked_at is null or revoked_at >= consented_at)
);
create unique index business_receipt_reading_one_active on public.business_receipt_reading_consents(space_id) where revoked_at is null;
create index business_receipt_reading_owner_history on public.business_receipt_reading_consents(space_id, owner_id, consented_at desc);
alter table public.business_receipt_reading_consents enable row level security;
revoke all on public.business_receipt_reading_consents from public, anon, authenticated;
grant select, insert, update, delete on public.business_receipt_reading_consents to service_role;

create table public.business_receipt_consent_commands (
  space_id uuid not null references public.spaces(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  idempotency_key text not null check (length(idempotency_key) between 1 and 80),
  request_hash text not null check (length(request_hash)=64),
  created_at timestamptz not null default clock_timestamp(),
  primary key (space_id,owner_id,idempotency_key)
);
alter table public.business_receipt_consent_commands enable row level security;
revoke all on public.business_receipt_consent_commands from public, anon, authenticated;
grant select, insert on public.business_receipt_consent_commands to service_role;

create table public.business_receipt_read_states (
  space_id uuid not null references public.spaces(id) on delete cascade,
  person_id uuid not null references auth.users(id) on delete cascade,
  connection_id uuid not null references public.financial_source_connections(id) on delete cascade,
  completion_cursor text not null check (length(completion_cursor) = 64),
  seen_at timestamptz not null default clock_timestamp(),
  primary key (space_id, person_id, connection_id)
);
alter table public.business_receipt_read_states enable row level security;
revoke all on public.business_receipt_read_states from public, anon, authenticated;
grant select, insert, update, delete on public.business_receipt_read_states to service_role;

create table public.business_receipt_activity_baseline (
  singleton boolean primary key default true check (singleton),
  established_at timestamptz not null default clock_timestamp()
);
insert into public.business_receipt_activity_baseline(singleton) values (true);
alter table public.business_receipt_activity_baseline enable row level security;
revoke all on public.business_receipt_activity_baseline from public, anon, authenticated;
grant select on public.business_receipt_activity_baseline to service_role;

create function public.check_business_receipt_reading_consent() returns trigger
language plpgsql set search_path='' as $$
begin
  if not exists (select 1 from public.spaces s where s.id=new.space_id and s.kind='business' and s.created_by=new.owner_id and s.closed_at is null) then
    raise exception 'Business owner consent required';
  end if;
  if TG_OP='UPDATE' and (new.id,new.space_id,new.owner_id,new.scope_version,new.route,new.disclosure,new.consented_at,new.idempotency_key,new.request_hash)
    is distinct from (old.id,old.space_id,old.owner_id,old.scope_version,old.route,old.disclosure,old.consented_at,old.idempotency_key,old.request_hash) then
    raise exception 'Consent generation is immutable';
  end if;
  if TG_OP='UPDATE' and old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at then
    raise exception 'Revoked consent cannot be restored';
  end if;
  return new;
end;
$$;
revoke execute on function public.check_business_receipt_reading_consent() from public, anon, authenticated;
create trigger business_receipt_reading_consent_guard before insert or update on public.business_receipt_reading_consents
for each row execute function public.check_business_receipt_reading_consent();

commit;
