alter table public.whatsapp_sender_links
    add constraint whatsapp_sender_links_transport_identity_key
    unique (id, destination_space_id, destination_owner_id, wa_id_hash);

alter table public.whatsapp_inbound_messages
    add column arrival_sequence bigint generated always as identity,
    add column sender_link_id uuid,
    add column destination_space_id uuid,
    add column sent_at timestamptz,
    add column transport_envelope bytea,
    add column transport_key_id text,
    add column composition_state text not null default 'not_started'
        check (composition_state in ('not_started', 'started', 'completed', 'unknown')),
    add constraint whatsapp_inbound_original_link_fkey
        foreign key (sender_link_id, destination_space_id, destination_owner_id, sender_hash)
        references public.whatsapp_sender_links
            (id, destination_space_id, destination_owner_id, wa_id_hash) on delete cascade,
    add constraint whatsapp_inbound_envelope_shape check (
        (transport_envelope is null and transport_key_id is null
            and sender_link_id is null and destination_space_id is null and sent_at is null)
        or (transport_envelope is not null and octet_length(transport_envelope) > 29
            and get_byte(transport_envelope, 0) = 1
            and transport_key_id is not null and transport_key_id ~ '^[0-9a-f]{32}$'
            and sender_link_id is not null and destination_space_id is not null
            and destination_owner_id is not null and sent_at is not null
            and connection_id is null and status = 'captured')
    ),
    drop constraint whatsapp_inbound_messages_check,
    add constraint whatsapp_inbound_capture_shape
        check (status <> 'captured' or connection_id is not null or transport_envelope is not null);

create index whatsapp_inbound_original_link_idx
    on public.whatsapp_inbound_messages(sender_link_id);
create index whatsapp_inbound_sender_arrival_idx
    on public.whatsapp_inbound_messages(destination_space_id, sender_hash, arrival_sequence)
    where transport_envelope is not null;

create function argus_private.whatsapp_transport_original()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'UPDATE' and old.transport_envelope is not null then
        if (new.id, new.provider_message_key, new.sender_hash, new.destination_owner_id,
            new.sender_link_id, new.destination_space_id, new.sent_at, new.transport_envelope,
            new.transport_key_id, new.received_at, new.arrival_sequence)
            is distinct from
           (old.id, old.provider_message_key, old.sender_hash, old.destination_owner_id,
            old.sender_link_id, old.destination_space_id, old.sent_at, old.transport_envelope,
            old.transport_key_id, old.received_at, old.arrival_sequence) then
            raise exception 'whatsapp_transport_original_immutable' using errcode = '23514';
        end if;
        if old.composition_state in ('completed', 'unknown')
            and new.composition_state is distinct from old.composition_state then
            raise exception 'whatsapp_composition_settled' using errcode = '23514';
        end if;
        if old.composition_state = 'started' and new.composition_state = 'not_started' then
            raise exception 'whatsapp_composition_no_retry' using errcode = '23514';
        end if;
    elsif new.transport_envelope is not null then
        perform 1 from public.whatsapp_sender_links l
         where l.id = new.sender_link_id and l.status = 'active'
           and l.destination_space_id = new.destination_space_id
           and l.destination_owner_id = new.destination_owner_id
           and l.wa_id_hash = new.sender_hash for share;
        if not found then
            raise exception 'whatsapp_sender_link_inactive' using errcode = '23514';
        end if;
    end if;
    return new;
end;
$$;
create trigger whatsapp_transport_original before insert or update
    on public.whatsapp_inbound_messages for each row
    execute function argus_private.whatsapp_transport_original();

create table public.whatsapp_outbox (
    provider_message_key bytea not null
        references public.whatsapp_inbound_messages(provider_message_key) on delete cascade,
    reply_index integer not null check (reply_index >= 0),
    body text not null check (char_length(body) between 1 and 4096),
    state text not null default 'pending'
        check (state in ('pending', 'sending', 'sent', 'unknown', 'waiting_for_window', 'suppressed')),
    created_at timestamptz not null default clock_timestamp(),
    attempted_at timestamptz,
    sent_at timestamptz,
    error_code text check (error_code is null or char_length(error_code) <= 64),
    primary key (provider_message_key, reply_index),
    check ((state = 'sent') = (sent_at is not null)),
    check (state not in ('sending', 'sent', 'unknown') or attempted_at is not null)
);
create index whatsapp_outbox_pending_idx on public.whatsapp_outbox(created_at)
    where state in ('pending', 'sending');

create function argus_private.whatsapp_outbox_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'INSERT' then
        if new.state <> 'pending' or not exists (
            select 1 from public.whatsapp_inbound_messages i
             where i.provider_message_key = new.provider_message_key
               and i.transport_envelope is not null and i.composition_state = 'completed'
        ) then
            raise exception 'whatsapp_outbox_reply_not_persisted' using errcode = '23514';
        end if;
        return new;
    end if;
    if tg_op = 'DELETE' then
        if exists (select 1 from public.whatsapp_inbound_messages i
                    where i.provider_message_key = old.provider_message_key) then
            raise exception 'whatsapp_outbox_parent_required' using errcode = '23514';
        end if;
        return old;
    end if;
    if (new.provider_message_key, new.reply_index, new.body, new.created_at)
        is distinct from (old.provider_message_key, old.reply_index, old.body, old.created_at) then
        raise exception 'whatsapp_outbox_identity_immutable' using errcode = '23514';
    end if;
    if old.state in ('sent', 'unknown', 'waiting_for_window', 'suppressed')
        and new is distinct from old then
        raise exception 'whatsapp_outbox_settled' using errcode = '23514';
    end if;
    if old.state = 'sending' and new.state not in ('sending', 'sent', 'unknown') then
        raise exception 'whatsapp_outbox_no_retry' using errcode = '23514';
    end if;
    return new;
end;
$$;
create trigger whatsapp_outbox_immutable before insert or update or delete
    on public.whatsapp_outbox for each row
    execute function argus_private.whatsapp_outbox_immutable();

alter table public.whatsapp_outbox enable row level security;
revoke all on public.whatsapp_outbox from public, anon, authenticated;
grant select, insert, update, delete on public.whatsapp_outbox to service_role;
revoke truncate on public.whatsapp_outbox, public.whatsapp_inbound_messages from service_role;
revoke all on sequence public.whatsapp_inbound_messages_arrival_sequence_seq
    from public, anon, authenticated;
grant usage, select on sequence public.whatsapp_inbound_messages_arrival_sequence_seq to service_role;
revoke all on function argus_private.whatsapp_transport_original(),
    argus_private.whatsapp_outbox_immutable() from public, anon, authenticated;
