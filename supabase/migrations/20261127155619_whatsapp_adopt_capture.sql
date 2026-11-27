begin;

set local lock_timeout = '5s';
set local statement_timeout = '60s';

create or replace function argus_private.whatsapp_transport_original() returns trigger
language plpgsql set search_path='' as $$
begin
    if tg_op='UPDATE' and old.status='captured' and old.connection_id is not null
       and old.sender_link_id is distinct from new.sender_link_id then
        raise exception 'whatsapp_capture_sender_immutable' using errcode='23514';
    end if;
    if tg_op='UPDATE' and old.transport_envelope is not null then
        if (new.id,new.provider_message_key,new.sender_hash,new.destination_owner_id,
            new.sender_link_id,new.destination_space_id,new.sent_at,new.transport_envelope,
            new.transport_key_id,new.received_at,new.arrival_sequence) is distinct from
           (old.id,old.provider_message_key,old.sender_hash,old.destination_owner_id,
            old.sender_link_id,old.destination_space_id,old.sent_at,old.transport_envelope,
            old.transport_key_id,old.received_at,old.arrival_sequence) then
            raise exception 'whatsapp_transport_original_immutable' using errcode='23514';
        end if;
        if old.composition_state in ('completed','unknown') and new.composition_state is distinct from old.composition_state then
            raise exception 'whatsapp_composition_settled' using errcode='23514';
        end if;
        if old.composition_state='started' and new.composition_state='not_started' then
            raise exception 'whatsapp_composition_no_retry' using errcode='23514';
        end if;
    elsif tg_op='UPDATE' and old.status='captured' and old.connection_id is not null
        and old.connection_id is distinct from new.connection_id then
        -- Assignment moves the original capture, including after disconnect.
        -- Every other field still describes its first delivery.
        if to_jsonb(new)-'connection_id' is distinct from to_jsonb(old)-'connection_id' then
            raise exception 'whatsapp_capture_original_immutable' using errcode='23514';
        end if;
        perform 1 from public.whatsapp_held_files h
        join public.whatsapp_sender_links l on l.id=h.sender_link_id
            and l.destination_owner_id=h.user_id and l.wa_id_hash=old.sender_hash
        join public.financial_source_connections src on src.id=h.connection_id
            and src.user_id=h.user_id and src.owner_space_id is null and src.source='statement'
        join public.financial_source_connections dst on dst.id=h.assigned_connection_id
            and dst.owner_space_id=h.assigned_space_id and dst.source='statement'
        join public.spaces s on s.id=h.assigned_space_id and s.kind='business'
            and s.created_by=dst.user_id
        where h.provider_message_key=old.provider_message_key and h.state='assigned'
            and h.user_id=old.destination_owner_id and h.sender_link_id=old.sender_link_id
            and h.connection_id=old.connection_id and h.assigned_connection_id=new.connection_id
        for share of h,l,src,dst,s;
        if not found then
            raise exception 'whatsapp_capture_assignment_mismatch' using errcode='23514';
        end if;
    elsif new.sender_link_id is not null and (tg_op='INSERT' or
        (old.sender_link_id,old.sender_hash,old.destination_owner_id,old.connection_id,old.transport_envelope)
        is distinct from
        (new.sender_link_id,new.sender_hash,new.destination_owner_id,new.connection_id,new.transport_envelope)) then
        perform 1 from public.whatsapp_sender_links l
        where l.id=new.sender_link_id and (
            (l.status='active' and l.destination_owner_id=new.destination_owner_id and l.wa_id_hash=new.sender_hash)
            or (tg_op='UPDATE' and old.sender_link_id=new.sender_link_id and old.connection_id=new.connection_id
                and l.destination_owner_id is null and new.destination_owner_id is null and new.sender_hash is null)
        ) for share;
        if not found then
            raise exception 'whatsapp_sender_link_inactive' using errcode='23514';
        end if;
    end if;
    return new;
end;
$$;

commit;
