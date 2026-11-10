-- Business email receiving: one address per Business bound through a live
-- client grant, a durable delivery queue, and one row per attachment part.
-- Service role only; the API resolves the Business through the route, never
-- through message content.

create table public.business_email_routes (
    id uuid primary key default gen_random_uuid(),
    recipient text not null unique
        check (recipient = lower(recipient) and length(recipient) <= 254),
    space_id uuid not null,
    principal_id uuid not null references auth.users(id) on delete cascade,
    granted_by uuid not null references auth.users(id) on delete cascade,
    grant_id uuid not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    -- The principal owns the captured documents, so it is the Business owner:
    -- source connections pin (owner_space_id, user_id) to spaces (id, created_by).
    foreign key (space_id, principal_id) references public.spaces(id, created_by) on delete cascade,
    -- The grant checked before each capture belongs to the same Business.
    foreign key (grant_id, space_id) references public.business_client_grants(id, space_id) on delete cascade
);
-- One live address per Business: a concurrent create returns the same route.
create unique index business_email_routes_one_active on public.business_email_routes(space_id) where active;

create table public.business_email_deliveries (
    id uuid primary key default gen_random_uuid(),
    provider text not null check (provider in ('resend')),
    external_id text not null,
    recipients jsonb not null default '[]'::jsonb,
    route_id uuid references public.business_email_routes(id) on delete cascade,
    space_id uuid references public.spaces(id) on delete cascade,
    principal_id uuid references auth.users(id) on delete cascade,
    state text not null default 'received'
        check (state in ('received','processing','partial','captured','rejected')),
    original_document_id uuid references public.financial_source_connections(id) on delete set null,
    received_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    available_at timestamptz not null default now(),
    lease_until timestamptz,
    lease_token uuid,
    attempts integer not null default 0,
    error_code text,
    subject text,
    sender text,
    sent_at text,
    text_body text,
    unique (provider, external_id),
    check ((space_id is null) = (principal_id is null)),
    check ((route_id is null) or (space_id is not null))
);
create index business_email_delivery_queue on public.business_email_deliveries(available_at)
    where state in ('received','processing','partial');
create index business_email_delivery_scope on public.business_email_deliveries(space_id, received_at desc);

create table public.business_email_parts (
    delivery_id uuid not null references public.business_email_deliveries(id) on delete cascade,
    id text not null,
    filename text not null,
    media_type text not null,
    state text not null default 'pending' check (state in ('pending','captured','rejected')),
    document_id uuid references public.financial_source_connections(id) on delete set null,
    error_code text,
    primary key (delivery_id, id)
);

alter table public.business_email_routes enable row level security;
alter table public.business_email_deliveries enable row level security;
alter table public.business_email_parts enable row level security;
revoke all on public.business_email_routes, public.business_email_deliveries, public.business_email_parts
    from public, anon, authenticated;
grant select, insert, update, delete
    on public.business_email_routes, public.business_email_deliveries, public.business_email_parts
    to service_role;

-- A route can be switched off, never pointed at another Business or person.
create function argus_private.freeze_business_email_destination()
returns trigger language plpgsql set search_path = '' as $$
begin
    if (new.recipient, new.space_id, new.principal_id, new.grant_id) is distinct from
       (old.recipient, old.space_id, old.principal_id, old.grant_id) then
        raise exception 'email_route_destination_immutable';
    end if;
    return new;
end;
$$;
create trigger freeze_business_email_destination before update on public.business_email_routes
    for each row execute function argus_private.freeze_business_email_destination();

-- Deleting or disconnecting a captured source scrubs the retained message text
-- and stops any further capture from it.
create function argus_private.tombstone_business_email_source()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
    update public.business_email_deliveries
    set state = 'rejected', error_code = 'email_source_deleted',
        subject = null, sender = null, sent_at = null, text_body = null,
        lease_token = null, lease_until = null, updated_at = now()
    where original_document_id = old.id;
    update public.business_email_parts
    set state = 'rejected', error_code = 'email_source_deleted',
        filename = 'deleted', media_type = 'application/octet-stream'
    where document_id = old.id;
    return old;
end;
$$;
create trigger tombstone_business_email_source_delete before delete on public.financial_source_connections
    for each row execute function argus_private.tombstone_business_email_source();
create trigger tombstone_business_email_source_disconnect after update of status on public.financial_source_connections
    for each row when (new.status = 'disconnected' and old.status is distinct from new.status)
    execute function argus_private.tombstone_business_email_source();
revoke all on function argus_private.freeze_business_email_destination(),
    argus_private.tombstone_business_email_source() from public, anon, authenticated;
