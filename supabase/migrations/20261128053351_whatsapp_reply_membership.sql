-- Joining a forward once remains true after its reply group is consumed.
alter table public.whatsapp_inbound_messages add column reply_group_id uuid;
update public.whatsapp_inbound_messages m
   set reply_group_id = g.id
  from public.whatsapp_reply_groups g
 where m.provider_message_key = any(g.member_keys);
create index whatsapp_inbound_reply_members_idx
    on public.whatsapp_inbound_messages (reply_group_id) where reply_group_id is not null;
create index whatsapp_inbound_pending_sender_idx
    on public.whatsapp_inbound_messages (sender_hash, received_at) where claim_until is not null;
alter table public.whatsapp_reply_groups drop column member_keys;
