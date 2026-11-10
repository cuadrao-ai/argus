begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.spaces
    add column business_legacy_default boolean not null default true,
    add column business_workspace_revision bigint not null default 0
        check (business_workspace_revision >= 0),
    add column business_provided_details jsonb not null default '{}'
        check (jsonb_typeof(business_provided_details) = 'object'),
    add column business_appearance jsonb not null default '{"kind":"default"}'
        check (jsonb_typeof(business_appearance) = 'object');

drop index public.spaces_one_open_business_idx;
create unique index spaces_one_open_business_idx on public.spaces(current_owner_id)
    where kind='business' and closed_at is null and business_legacy_default;

create or replace function public.business_space_of(p_owner uuid) returns uuid
language sql stable set search_path='' as $$
    select s.id from public.spaces s
    where s.current_owner_id=p_owner and s.kind='business'
        and s.closed_at is null and s.business_legacy_default
        and exists (
            select 1 from public.business_client_grants g
            where g.space_id=s.id and g.grantee_id=p_owner
                and g.revoked_at is null
                and (g.expires_at is null or g.expires_at>clock_timestamp())
        );
$$;

create function argus_private.business_workspace_revision() returns trigger
language plpgsql set search_path='' as $$
begin
    if (new.name,new.business_provided_details,new.business_appearance) is distinct from
        (old.name,old.business_provided_details,old.business_appearance) then
        new.business_workspace_revision := old.business_workspace_revision + 1;
    else
        new.business_workspace_revision := old.business_workspace_revision;
    end if;
    return new;
end;
$$;
revoke all on function argus_private.business_workspace_revision() from public,anon,authenticated;
create trigger business_workspace_revision before update on public.spaces
    for each row execute function argus_private.business_workspace_revision();

create table argus_private.business_workspace_commands (
    actor_id uuid not null references auth.users(id) on delete cascade,
    operation text not null check(operation in ('create','save','upload')),
    command_key text not null check(char_length(command_key) between 1 and 200 and char_length(btrim(command_key))>0),
    payload jsonb not null check(jsonb_typeof(payload)='object'),
    space_id uuid not null references public.spaces(id) on delete cascade,
    created_at timestamptz not null default clock_timestamp(),
    primary key(actor_id,operation,command_key)
);
alter table argus_private.business_workspace_commands enable row level security;
revoke all on argus_private.business_workspace_commands from public,anon,authenticated,service_role;
grant select,insert on argus_private.business_workspace_commands to service_role;

create table argus_private.business_workspace_assets (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
    width integer not null check(width between 1 and 1280),
    height integer not null check(height between 1 and 1280),
    created_at timestamptz not null default clock_timestamp(),
    unique(space_id,sha256)
);
alter table argus_private.business_workspace_assets enable row level security;
revoke all on argus_private.business_workspace_assets from public,anon,authenticated,service_role;
grant select,insert on argus_private.business_workspace_assets to service_role;

comment on column public.spaces.business_legacy_default is
    'Legacy bootstrap and default resolver slot. Additional Businesses do not acquire this slot on read, sign-in or closure.';
comment on column public.spaces.business_provided_details is
    'Business-provided contact and presence fields. No verification or fiscal activation is implied.';
comment on table argus_private.business_workspace_commands is
    'Private atomic create/save replay records. Current membership is rechecked before replay; account deletion removes command metadata, not Business custody.';
commit;
