-- WhatsApp loss recovery: the message itself, sealed, next to its claim.
--
-- The webhook answers 200 before the photo is read. If the process dies in
-- between, the claim row held only digests, so nothing could fetch the photo
-- again or answer the sender. claim_envelope holds the message (media id,
-- type, caption, sender number) sealed with the ingestion SecretBox, written
-- in the same statement as the claim. A sweep re-runs lapsed claims from it.
--
-- Retention: the envelope exists only while the message is unsettled. A
-- trigger clears it on every settlement (any status other than received or
-- failed, or a claim that ends), whoever writes the row. Code from before this
-- migration settles without naming the column, so during a rollout or a code
-- only rollback its settlements still succeed and still drop the sealed bytes.
-- The check below then holds by construction: an envelope only on the two
-- unsettled statuses a claim can hold (received, and failed while a
-- redelivery holds a new claim). recovery_attempts bounds how often the sweep
-- retakes one claim.
--
-- Existing rows carry no envelope, so the check holds for them as written.
-- Grants and row level security are unchanged: the table stays service-role
-- only, with no client policies. The trigger function is not callable by any
-- client role.
--
-- Rollback: a plain code revert is safe with this schema in place. To remove
-- it, drop the trigger, its function and the constraint, then the two columns.
-- Droppable: nothing else references them and their data is only recovery
-- state for messages still in flight.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.whatsapp_inbound_messages
    add column claim_envelope bytea,
    add column recovery_attempts smallint not null default 0
        check (recovery_attempts between 0 and 100),
    add constraint whatsapp_inbound_claim_envelope_shape check (
        claim_envelope is null
        or (status in ('received', 'failed')
            and octet_length(claim_envelope) > 29
            and get_byte(claim_envelope, 0) = 1)
    );

create function public.whatsapp_inbound_clear_settled_envelope()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.status not in ('received', 'failed') or new.claim_until is null then
        new.claim_envelope := null;
    end if;
    return new;
end;
$$;

revoke all on function public.whatsapp_inbound_clear_settled_envelope()
    from public, anon, authenticated;

create trigger whatsapp_inbound_clear_settled_envelope
    before insert or update on public.whatsapp_inbound_messages
    for each row execute function public.whatsapp_inbound_clear_settled_envelope();

create index whatsapp_inbound_lapsed_claim_idx
    on public.whatsapp_inbound_messages (claim_until)
    where status in ('received', 'failed') and claim_until is not null;

commit;
