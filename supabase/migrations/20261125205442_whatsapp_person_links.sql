begin;

set local lock_timeout = '5s';
set local statement_timeout = '60s';

drop trigger whatsapp_inbound_clear_settled_envelope on public.whatsapp_inbound_messages;
drop function public.whatsapp_inbound_clear_settled_envelope();
drop trigger whatsapp_capture_same_space on public.whatsapp_inbound_messages;
drop function argus_private.require_whatsapp_capture_same_space();
drop trigger fill_sender_link_space on public.whatsapp_sender_links;
drop function argus_private.fill_sender_link_space();

alter table public.whatsapp_inbound_messages
    drop constraint whatsapp_inbound_original_link_fkey,
    drop constraint whatsapp_inbound_envelope_shape,
    drop constraint whatsapp_inbound_messages_check1,
    drop column claim_envelope,
    drop column recovery_attempts,
    alter column sender_hash drop not null,
    add constraint whatsapp_inbound_original_link_fkey
        foreign key (sender_link_id) references public.whatsapp_sender_links(id) on delete cascade,
    add constraint whatsapp_inbound_envelope_shape check (
        (transport_envelope is null and transport_key_id is null and destination_space_id is null
            and sent_at is null and (sender_link_id is null or (status='captured' and connection_id is not null)))
        or (transport_envelope is not null and octet_length(transport_envelope)>29
            and get_byte(transport_envelope,0)=1 and transport_key_id is not null
            and transport_key_id ~ '^[0-9a-f]{32}$' and sender_link_id is not null
            and destination_space_id is not null and destination_owner_id is not null
            and sent_at is not null and connection_id is null and status='captured')
    ),
    add constraint whatsapp_inbound_sender_shape check (
        (sender_hash is not null and (status not in ('captured','linked') or destination_owner_id is not null))
        or (sender_hash is null and destination_owner_id is null and status='captured'
            and connection_id is not null and sender_link_id is not null)
    );

alter table public.business_whatsapp_ai_consents
    alter column issuer_id drop not null,
    drop constraint business_whatsapp_consent_original_link_fkey,
    add constraint business_whatsapp_consent_original_link_fkey
        foreign key (sender_link_id) references public.whatsapp_sender_links(id) on delete cascade;

delete from argus_private.business_custody_deferred_keys
where constraint_name in ('whatsapp_sender_links_destination_space_fkey','business_whatsapp_consent_original_link_fkey');

alter table public.whatsapp_sender_links
    drop constraint whatsapp_sender_links_destination_space_fkey,
    drop constraint whatsapp_sender_links_transport_identity_key,
    drop column destination_space_id,
    alter column destination_owner_id drop not null,
    alter column wa_id_hash drop not null,
    alter column linked_at drop not null,
    alter column reply_language drop not null,
    add constraint whatsapp_link_person_shape check (
        (destination_owner_id is not null and wa_id_hash is not null and linked_at is not null and reply_language is not null)
        or (destination_owner_id is null and wa_id_hash is null and linked_at is null and reply_language is null and status='revoked')
    );

-- The settlement recorded updated_at when it locked the active sender link.
-- A missing historical link cannot be reconstructed from a phone suffix.
with proven_links as (
    select m.id, (array_agg(l.id))[1] as link_id
    from public.whatsapp_inbound_messages m
    join public.whatsapp_sender_links l on l.wa_id_hash=m.sender_hash
        and l.destination_owner_id=m.destination_owner_id
        and l.linked_at<=m.updated_at and (l.revoked_at is null or m.updated_at<=l.revoked_at)
    where m.status='captured' and m.connection_id is not null and m.sender_link_id is null
    group by m.id having count(*)=1
)
update public.whatsapp_inbound_messages m set sender_link_id=p.link_id
from proven_links p where p.id=m.id;

-- Legacy captures for which the link was already deleted remain unattributed.
alter table public.whatsapp_inbound_messages add constraint whatsapp_document_has_sender
    check (status<>'captured' or connection_id is null or sender_link_id is not null) not valid;

comment on table public.whatsapp_sender_links is 'A person owns one active sender link. A retained receipt can reference a revoked link with just masked digits after the person erases their account.';

create or replace function argus_private.business_whatsapp_consent_immutable() returns trigger
language plpgsql set search_path='' as $$
begin
    if tg_op='DELETE' then
        if exists(select 1 from public.whatsapp_sender_links where id=old.sender_link_id and destination_owner_id is not null) then
            raise exception 'whatsapp_consent_original_immutable' using errcode='23514';
        end if;
        return old;
    elsif tg_op='UPDATE' then
        -- Only Auth erasure may replace another member's grant issuer. Use the
        -- existing deletion claim's alias; a purged Business has no alias left.
        if current_user='postgres' and pg_trigger_depth()>1 and old.issuer_id<>old.owner_id
           and new.issuer_id is null and not exists(select from auth.users where id=old.issuer_id)
           and to_jsonb(old)-'issuer_id'=to_jsonb(new)-'issuer_id' then
            select aliases.actor_id into new.issuer_id
            from (
                select a.actor_id,a.space_id,a.departing_user_id,a.deletion_run_id,a.claim_id
                from argus_private.business_departure_aliases a
                union all
                select r.deleted_actor_id,m.space_id,m.departing_user_id,m.deletion_run_id,m.claim_id
                from argus_private.business_custody_moves m
                join argus_private.business_custody_reservations r on r.space_id=m.space_id
            ) aliases
            join argus_private.account_deletion_runs d on d.id=aliases.deletion_run_id
                and d.claim_id=aliases.claim_id and d.user_id=aliases.departing_user_id
            where aliases.space_id=old.space_id and aliases.departing_user_id=old.issuer_id
                and d.status<>'done' and d.claimed_until>clock_timestamp();
            return new;
        end if;
        if (to_jsonb(new)-'revoked_at'-'revoked_by') is distinct from (to_jsonb(old)-'revoked_at'-'revoked_by')
           or (old.revoked_at is not null and (new.revoked_at,new.revoked_by) is distinct from (old.revoked_at,old.revoked_by)) then
            raise exception 'whatsapp_consent_original_immutable' using errcode='23514';
        end if;
    else
        perform 1 from public.whatsapp_sender_links l
        join auth.users u on u.id=l.destination_owner_id
        join public.business_client_grants g on g.id=new.grant_id and g.grantee_id=u.id
        join public.spaces s on s.id=g.space_id
        where l.id=new.sender_link_id and l.status='active'
            and l.destination_owner_id=new.owner_id and l.wa_id_hash=new.sender_hash
            and new.consenting_actor_id=new.owner_id
            and s.id=new.space_id and s.kind='business' and s.closed_at is null
            and g.issuer_id=new.issuer_id and g.revoked_at is null
            and (g.expires_at is null or g.expires_at>clock_timestamp())
            and 'prepare'=any(g.capabilities) and not coalesce(u.is_anonymous,false)
        for share of l,s,g;
        if not found or new.revoked_at is not null then
            raise exception 'whatsapp_consent_owner_required' using errcode='23514';
        end if;
        if new.scope_version<>2 then
            raise exception 'whatsapp_consent_scope_retired' using errcode='23514';
        end if;
        new.consented_at:=clock_timestamp();
    end if;
    return new;
end;
$$;

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

-- Erase contact and permission data while preserving the channel and masked
-- attribution of documents that another member can still open.
create function argus_private.erase_whatsapp_receipt_sender() returns trigger
language plpgsql security definer set search_path='' as $$
declare
    retained_link uuid;
begin
    -- A settlement takes a shared lock on the link before publishing its receipt.
    -- Wait for it before testing whether that receipt needs a masked sender.
    perform 1 from public.whatsapp_sender_links where destination_owner_id=old.id for update;
    for retained_link in
        update public.whatsapp_sender_links l
        set destination_owner_id=null, wa_id_hash=null, status='revoked',
            linked_at=null, revoked_at=coalesce(revoked_at,clock_timestamp()), reply_language=null
        where l.destination_owner_id=old.id and exists (
            select 1 from public.whatsapp_inbound_messages m
            where m.sender_link_id=l.id and m.connection_id is not null and m.status='captured'
        ) returning l.id
    loop
        update public.whatsapp_inbound_messages
        set destination_owner_id=null, sender_hash=null
        where sender_link_id=retained_link and connection_id is not null and status='captured';
        delete from public.business_whatsapp_ai_consents where sender_link_id=retained_link;
        -- The last receipt may have been purged while erasure waited on it.
        delete from public.whatsapp_sender_links l where l.id=retained_link
            and not exists(select 1 from public.whatsapp_inbound_messages m
                           where m.sender_link_id=l.id and m.connection_id is not null);
    end loop;
    return old;
end;
$$;
revoke all on function argus_private.erase_whatsapp_receipt_sender() from public,anon,authenticated;
create trigger erase_whatsapp_receipt_sender before delete on auth.users
for each row execute function argus_private.erase_whatsapp_receipt_sender();

create index whatsapp_consent_other_issuer_idx on public.business_whatsapp_ai_consents(issuer_id)
    where issuer_id<>owner_id;

create function argus_private.erase_whatsapp_consent_issuer() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    update public.business_whatsapp_ai_consents set issuer_id=null
    where issuer_id=old.id and issuer_id<>owner_id;
    return old;
end;
$$;
revoke all on function argus_private.erase_whatsapp_consent_issuer() from public,anon,authenticated;
create trigger erase_whatsapp_consent_issuer after delete on auth.users
for each row execute function argus_private.erase_whatsapp_consent_issuer();

create function argus_private.forget_erased_whatsapp_sender() returns trigger
language plpgsql set search_path='' as $$
begin
    -- Serialize final-receipt deletion when two documents disappear together.
    perform 1 from public.whatsapp_sender_links
    where id=old.sender_link_id and destination_owner_id is null for update;
    delete from public.whatsapp_sender_links l
    where l.id=old.sender_link_id and l.destination_owner_id is null and not exists (
        select 1 from public.whatsapp_inbound_messages m where m.sender_link_id=l.id
    );
    return old;
end;
$$;
revoke all on function argus_private.forget_erased_whatsapp_sender() from public,anon,authenticated;
create trigger forget_erased_whatsapp_sender after delete on public.whatsapp_inbound_messages
for each row when (old.destination_owner_id is null and old.sender_link_id is not null)
execute function argus_private.forget_erased_whatsapp_sender();

commit;
