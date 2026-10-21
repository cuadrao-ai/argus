-- Pre-check before applying 20261008140000_business_spaces. Read-only.
-- Apply only when ready_to_apply is true: 20261008130000 has run, no sender
-- link exists yet (destination_space_id is added NOT NULL with no backfill),
-- and the spaces table is not there yet. Run it after 20261008130000; before
-- that the sender-link table does not exist and this query errors.
select
    to_regclass('public.whatsapp_sender_links') is not null as whatsapp_intake_applied,
    (select count(*) from public.whatsapp_sender_links) as sender_links,
    to_regclass('public.spaces') is null as spaces_absent,
    to_regclass('public.whatsapp_sender_links') is not null
      and (select count(*) from public.whatsapp_sender_links) = 0
      and to_regclass('public.spaces') is null as ready_to_apply;
