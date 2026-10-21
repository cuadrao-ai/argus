create table public.business_whatsapp_ai_consents (
    id uuid primary key default gen_random_uuid(),
    sender_link_id uuid not null,
    space_id uuid not null,
    owner_id uuid not null,
    sender_hash bytea not null check (octet_length(sender_hash) = 32),
    consenting_actor_id uuid not null check (consenting_actor_id = owner_id),
    grant_id uuid not null,
    issuer_id uuid not null,
    scope_version integer not null check (scope_version = 1),
    purpose text not null check (purpose = 'business_whatsapp_draft_assistance'),
    disclosure text not null check (char_length(disclosure) between 1 and 4000),
    route jsonb not null check (jsonb_typeof(route) = 'object' and route <> '{}'::jsonb),
    route_hash text not null check (route_hash ~ '^[0-9a-f]{64}$'),
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 80),
    input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
    consented_at timestamptz not null default clock_timestamp(),
    revoked_at timestamptz,
    revoked_by uuid,
    constraint business_whatsapp_consent_original_link_fkey
        foreign key (sender_link_id, space_id, owner_id, sender_hash)
        references public.whatsapp_sender_links
            (id, destination_space_id, destination_owner_id, wa_id_hash) on delete cascade,
    unique (owner_id, idempotency_key),
    unique (id, sender_link_id, space_id, owner_id, sender_hash),
    check ((revoked_at is null) = (revoked_by is null)),
    check (revoked_by is null or revoked_by = owner_id),
    check (revoked_at is null or revoked_at >= consented_at)
);
create index business_whatsapp_consent_link_idx
    on public.business_whatsapp_ai_consents(sender_link_id);
create unique index business_whatsapp_consent_active_idx
    on public.business_whatsapp_ai_consents(sender_link_id) where revoked_at is null;

create function argus_private.business_whatsapp_consent_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'DELETE' then
        if exists (select 1 from public.whatsapp_sender_links where id = old.sender_link_id) then
            raise exception 'whatsapp_consent_original_immutable' using errcode = '23514';
        end if;
        return old;
    elsif tg_op = 'UPDATE' then
        if (to_jsonb(new) - 'revoked_at' - 'revoked_by')
            is distinct from (to_jsonb(old) - 'revoked_at' - 'revoked_by')
            or (old.revoked_at is not null and
                (new.revoked_at, new.revoked_by) is distinct from (old.revoked_at, old.revoked_by)) then
            raise exception 'whatsapp_consent_original_immutable' using errcode = '23514';
        end if;
    else
        perform 1 from public.whatsapp_sender_links l
        join public.spaces s on s.id = l.destination_space_id and s.created_by = l.destination_owner_id
        join auth.users u on u.id = l.destination_owner_id
        join public.business_client_grants g on g.id = new.grant_id
            and g.space_id = s.id and g.grantee_id = u.id and g.issuer_id = new.issuer_id
        where l.id = new.sender_link_id and l.status = 'active'
            and s.kind = 'business' and s.closed_at is null
            and coalesce(u.is_anonymous, false) = false
            and g.revoked_at is null and (g.expires_at is null or g.expires_at > clock_timestamp())
            and 'read' = any(g.capabilities) and 'prepare' = any(g.capabilities)
        for share of l, s, g;
        if not found or new.revoked_at is not null then
            raise exception 'whatsapp_consent_owner_required' using errcode = '23514';
        end if;
        new.consented_at := clock_timestamp();
    end if;
    return new;
end;
$$;
create trigger business_whatsapp_consent_immutable before insert or update or delete
    on public.business_whatsapp_ai_consents for each row
    execute function argus_private.business_whatsapp_consent_immutable();

alter table public.whatsapp_inbound_messages
    add column ai_consent_id uuid,
    add constraint whatsapp_inbound_ai_consent_fkey
        foreign key (ai_consent_id, sender_link_id, destination_space_id, destination_owner_id, sender_hash)
        references public.business_whatsapp_ai_consents
            (id, sender_link_id, space_id, owner_id, sender_hash) on delete cascade,
    add constraint whatsapp_inbound_ai_consent_shape
        check (ai_consent_id is null or transport_envelope is not null);
create index whatsapp_inbound_ai_consent_idx on public.whatsapp_inbound_messages(ai_consent_id);

create function argus_private.whatsapp_capture_consent_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'UPDATE' and new.ai_consent_id is distinct from old.ai_consent_id then
        raise exception 'whatsapp_capture_consent_immutable' using errcode = '23514';
    elsif tg_op = 'INSERT' and new.ai_consent_id is not null then
        perform 1 from public.business_whatsapp_ai_consents
            where id = new.ai_consent_id and revoked_at is null for share;
        if not found then
            raise exception 'whatsapp_capture_consent_revoked' using errcode = '23514';
        end if;
    end if;
    return new;
end;
$$;
create trigger whatsapp_capture_consent_immutable before insert or update
    on public.whatsapp_inbound_messages for each row
    execute function argus_private.whatsapp_capture_consent_immutable();

alter table public.business_whatsapp_ai_consents enable row level security;
revoke all on public.business_whatsapp_ai_consents from public, anon, authenticated;
grant select, insert, update, delete on public.business_whatsapp_ai_consents to service_role;
revoke truncate on public.business_whatsapp_ai_consents from service_role;
revoke all on function argus_private.business_whatsapp_consent_immutable() from public, anon, authenticated;
revoke all on function argus_private.whatsapp_capture_consent_immutable() from public, anon, authenticated;
