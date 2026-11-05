-- A capture must come from the sender's own active link, not any active link
-- of the same owner. Later updates to an already captured row keep the owner
-- check from 20261008140000.
create or replace function argus_private.require_whatsapp_capture_same_space()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (
    select 1
      from public.financial_source_connections c
      join public.whatsapp_sender_links l
        on l.destination_owner_id = c.user_id
       and l.destination_space_id = c.owner_space_id
       and l.status = 'active'
     where c.id = new.connection_id
       and c.user_id = new.destination_owner_id
       and (
         (tg_op = 'UPDATE' and old.connection_id is not distinct from new.connection_id)
         or l.wa_id_hash = new.sender_hash
       )
  ) then
    raise exception 'whatsapp_capture_space_mismatch' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

revoke all on function argus_private.require_whatsapp_capture_same_space()
  from public, anon, authenticated;
