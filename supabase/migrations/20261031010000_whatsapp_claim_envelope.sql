-- WhatsApp loss recovery: the message itself, sealed, next to its claim.
--
-- The webhook answers 200 before the photo is read. If the process dies in
-- between, the claim row held only digests, so nothing could fetch the photo
-- again or answer the sender. claim_envelope holds the message (media id,
-- type, caption, sender number) sealed with the ingestion SecretBox, written
-- in the same statement as the claim. A sweep re-runs lapsed claims from it.
--
-- Retention: the envelope exists only while the message is unsettled. Every
-- settlement (captured, linked, rejected, failed) clears it. The check below
-- allows an envelope only on the two unsettled statuses a claim can hold
-- (received, and failed while a redelivery holds a new claim). recovery_attempts bounds how often the sweep retakes one claim.
--
-- Existing rows carry no envelope, so the check holds for them as written.
-- Grants and row level security are unchanged: the table stays service-role
-- only, with no client policies.
--
-- Rollback: drop the constraint, then the two columns. Droppable: nothing
-- references them, no view or function reads them, and their data is only
-- recovery state for messages still in flight.
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

create index whatsapp_inbound_lapsed_claim_idx
    on public.whatsapp_inbound_messages (claim_until)
    where status in ('received', 'failed') and claim_until is not null;

commit;
