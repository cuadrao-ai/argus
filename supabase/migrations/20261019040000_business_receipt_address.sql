-- Receipt aliases, retired addresses, and authorized senders.
-- The route id stays the key for deliveries. The alias can change.
-- Service role only. No client grants.

alter table public.business_email_routes
    add column alias text,
    add column alias_normalized text,
    add column review_required boolean not null default false;

alter table public.business_email_routes
    add constraint business_email_routes_alias_shape check (
        alias is null
        or (
            alias = lower(alias)
            and alias = alias_normalized
            and alias ~ '^[a-z0-9-]{3,32}$'
        )
    );

create unique index business_email_routes_alias_normalized
    on public.business_email_routes (alias_normalized)
    where alias_normalized is not null;

create table public.business_email_retired_aliases (
    id uuid primary key default gen_random_uuid(),
    route_id uuid references public.business_email_routes (id) on delete set null,
    alias_normalized text,
    recipient text not null,
    retired_at timestamptz not null default now(),
    check (recipient = lower(recipient) and length(recipient) <= 254),
    check (
        alias_normalized is null
        or alias_normalized ~ '^[a-z0-9-]{3,32}$'
    )
);

create unique index business_email_retired_recipient
    on public.business_email_retired_aliases (recipient);
create unique index business_email_retired_alias
    on public.business_email_retired_aliases (alias_normalized)
    where alias_normalized is not null;

create table public.business_email_senders (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    kind text not null check (kind in ('address', 'domain')),
    value text not null check (value = lower(value) and length(value) between 3 and 254),
    status text not null check (status in ('authorized', 'blocked')),
    created_at timestamptz not null default now(),
    first_scan_at timestamptz,
    unique (space_id, kind, value)
);

alter table public.business_email_deliveries
    add column inbox_group text,
    add column auth_result text,
    add column review_note text,
    add column first_scan boolean not null default false,
    add column approved boolean not null default false,
    add column bounce_text text,
    add column cap_exempt boolean not null default false;

alter table public.business_email_deliveries
    add constraint business_email_deliveries_inbox_group check (
        inbox_group is null or inbox_group in ('bandeja', 'remitentes_nuevos')
    ),
    add constraint business_email_deliveries_auth_result check (
        auth_result is null or auth_result in ('aligned', 'failed', 'unknown')
    ),
    add constraint business_email_deliveries_not_approved check (approved = false);

-- Destination identity stays frozen. The alias and recipient may change together.
create or replace function argus_private.freeze_business_email_destination()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if (new.space_id, new.principal_id, new.grant_id) is distinct from
       (old.space_id, old.principal_id, old.grant_id) then
        raise exception 'email_route_destination_immutable';
    end if;
    return new;
end;
$$;

alter table public.business_email_retired_aliases enable row level security;
alter table public.business_email_senders enable row level security;
revoke all on public.business_email_retired_aliases, public.business_email_senders
    from public, anon, authenticated;
grant select, insert, update, delete
    on public.business_email_retired_aliases, public.business_email_senders
    to service_role;
revoke all on function argus_private.freeze_business_email_destination()
    from public, anon, authenticated;

-- A retired recipient or alias cannot be minted onto a route again.
create or replace function argus_private.reject_retired_recipient()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if exists (
        select 1 from public.business_email_retired_aliases
        where recipient = new.recipient
    ) then
        raise exception 'email_alias_retired';
    end if;
    if new.alias_normalized is not null and exists (
        select 1 from public.business_email_retired_aliases
        where alias_normalized = new.alias_normalized
    ) then
        raise exception 'email_alias_retired';
    end if;
    return new;
end;
$$;

create trigger business_email_routes_reject_retired
    before insert or update of recipient, alias_normalized
    on public.business_email_routes
    for each row execute function argus_private.reject_retired_recipient();

revoke all on function argus_private.reject_retired_recipient()
    from public, anon, authenticated;

create or replace function argus_private.reserve_deleted_route_alias()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    insert into public.business_email_retired_aliases (alias_normalized, recipient)
    values (old.alias_normalized, old.recipient)
    on conflict do nothing;
    return old;
end;
$$;

create trigger business_email_routes_reserve_alias
    before delete on public.business_email_routes
    for each row execute function argus_private.reserve_deleted_route_alias();

revoke all on function argus_private.reserve_deleted_route_alias()
    from public, anon, authenticated;

-- One row each time a receipt address stops or changes, or a sender is
-- authorized, removed, or blocked. The actor clears when that person is deleted.
create table public.business_email_address_events (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    actor_id uuid references auth.users (id) on delete set null,
    event_type text not null check (
        event_type in (
            'address_stopped',
            'address_changed',
            'sender_authorized',
            'sender_removed',
            'sender_blocked'
        )
    ),
    old_address text,
    new_address text,
    created_at timestamptz not null default now(),
    check (
        old_address is null
        or (old_address = lower(old_address) and length(old_address) <= 254)
    ),
    check (
        new_address is null
        or (new_address = lower(new_address) and length(new_address) <= 254)
    )
);

create index business_email_address_events_space_idx
    on public.business_email_address_events (space_id, created_at);

alter table public.business_email_address_events enable row level security;
revoke all on public.business_email_address_events from public, anon, authenticated, service_role;
grant select, insert on public.business_email_address_events to service_role;

-- Existing upload and WhatsApp writers omit this column. The default keeps
-- those rows non-email. Email capture sets 'email' in the delivery transaction.
alter table public.business_sources
    add column origin text not null default 'direct'
        check (origin in ('email', 'direct'));
