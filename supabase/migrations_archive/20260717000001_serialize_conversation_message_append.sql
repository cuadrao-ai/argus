-- Serialize every durable conversation-message append on the owned
-- conversation row. Response-option admission validates the exact latest
-- assistant option and inserts the accepted user request in this transaction.

create or replace function public.append_conversation_message(
  p_user_id uuid,
  p_conversation_id uuid,
  p_message_id uuid,
  p_role text,
  p_content text,
  p_metadata jsonb,
  p_created_at timestamptz,
  p_preview text,
  p_expected_source_assistant_id uuid,
  p_expected_source_metadata jsonb,
  p_option_id text,
  p_replacement_values jsonb
)
returns table (
  message jsonb,
  source_message jsonb,
  replayed boolean
)
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_conversation_id uuid;
  v_existing public.messages%rowtype;
  v_source public.messages%rowtype;
  v_latest public.messages%rowtype;
  v_message public.messages%rowtype;
  v_latest_created_at timestamptz;
  v_created_at timestamptz;
begin
  select c.id
    into v_conversation_id
    from public.conversations as c
   where c.id = p_conversation_id
     and c.user_id = p_user_id
   for update;

  if not found then
    raise exception 'Conversation not found or not owned by user.'
      using errcode = 'P0002';
  end if;

  select m.*
    into v_existing
    from public.messages as m
   where m.id = p_message_id;

  if found then
    if v_existing.user_id is distinct from p_user_id
      or v_existing.conversation_id is distinct from p_conversation_id
      or v_existing.role is distinct from p_role
      or v_existing.content is distinct from p_content
      or v_existing.metadata is distinct from coalesce(p_metadata, '{}'::jsonb) then
      raise exception 'Message identity collided with different immutable payload.'
        using errcode = '23505';
    end if;

    if p_expected_source_assistant_id is not null then
      select m.*
        into v_source
        from public.messages as m
       where m.user_id = p_user_id
         and m.conversation_id = p_conversation_id
         and (
           m.created_at < v_existing.created_at
           or (
             m.created_at = v_existing.created_at
             and m.id < v_existing.id
           )
         )
       order by m.created_at desc, m.id desc
       limit 1;

      if not found
        or v_source.id is distinct from p_expected_source_assistant_id
        or v_source.role is distinct from 'assistant'
        or (
          p_expected_source_metadata is not null
          and v_source.metadata is distinct from p_expected_source_metadata
        )
        or jsonb_typeof(p_replacement_values) is distinct from 'object'
        or not exists (
          select 1
            from jsonb_array_elements(
              case
                when jsonb_typeof(
                  v_source.metadata -> 'clarification' -> 'options'
                ) = 'array'
                then v_source.metadata -> 'clarification' -> 'options'
                else '[]'::jsonb
              end
            ) as response_option
           where response_option ->> 'id' = p_option_id
             and response_option -> 'replacement_values'
               = p_replacement_values
        ) then
        return;
      end if;
    end if;

    return query select
      to_jsonb(v_existing),
      case
        when p_expected_source_assistant_id is null then null::jsonb
        else to_jsonb(v_source)
      end,
      true;
    return;
  end if;

  if p_expected_source_assistant_id is not null then
    select m.*
      into v_latest
      from public.messages as m
     where m.user_id = p_user_id
       and m.conversation_id = p_conversation_id
     order by m.created_at desc, m.id desc
     limit 1;

    if not found
      or v_latest.id is distinct from p_expected_source_assistant_id
      or v_latest.role is distinct from 'assistant'
      or (
        p_expected_source_metadata is not null
        and v_latest.metadata is distinct from p_expected_source_metadata
      )
      or nullif(btrim(p_option_id), '') is null
      or jsonb_typeof(p_replacement_values) is distinct from 'object'
      or not exists (
        select 1
          from jsonb_array_elements(
            case
              when jsonb_typeof(
                v_latest.metadata -> 'clarification' -> 'options'
              ) = 'array'
              then v_latest.metadata -> 'clarification' -> 'options'
              else '[]'::jsonb
            end
          ) as response_option
         where response_option ->> 'id' = p_option_id
           and response_option -> 'replacement_values' = p_replacement_values
      ) then
      return;
    end if;
    v_source := v_latest;
  end if;

  if p_created_at is null then
    raise exception 'Message created_at must not be null.'
      using errcode = '22023';
  end if;

  select max(m.created_at)
    into v_latest_created_at
    from public.messages as m
   where m.user_id = p_user_id
     and m.conversation_id = p_conversation_id;

  v_created_at := p_created_at;
  if v_latest_created_at is not null then
    v_created_at := greatest(
      v_created_at,
      v_latest_created_at + interval '1 microsecond'
    );
  end if;

  insert into public.messages (
    id,
    user_id,
    conversation_id,
    role,
    content,
    metadata,
    created_at
  )
  values (
    p_message_id,
    p_user_id,
    p_conversation_id,
    p_role,
    p_content,
    coalesce(p_metadata, '{}'::jsonb),
    v_created_at
  )
  returning * into v_message;

  if nullif(btrim(p_preview), '') is not null then
    update public.conversations as c
       set last_message_preview = p_preview,
           updated_at = now()
     where c.id = p_conversation_id
       and c.user_id = p_user_id;
  end if;

  return query select
    to_jsonb(v_message),
    case
      when p_expected_source_assistant_id is null then null::jsonb
      else to_jsonb(v_source)
    end,
    false;
end;
$$;

-- Browser/authenticated clients must not bypass the serialized writer.
revoke insert, update, delete on public.messages from anon, authenticated;

revoke all on function public.append_conversation_message(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, uuid, jsonb, text, jsonb
) from public;
revoke all on function public.append_conversation_message(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, uuid, jsonb, text, jsonb
) from anon;
revoke all on function public.append_conversation_message(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, uuid, jsonb, text, jsonb
) from authenticated;
grant execute on function public.append_conversation_message(
  uuid, uuid, uuid, text, text, jsonb, timestamptz, text, uuid, jsonb, text, jsonb
) to service_role;

-- Backfill legacy degraded clarification previews. These rows predate
-- prompt_source provenance, so their English compatibility content may have
-- replaced a safe preview. Keep message content durable for reload, but clear
-- only a preview that still mirrors the latest degraded message. A later safe
-- append will repopulate it. Do not touch updated_at or reorder the conversation.
with latest_messages as (
  select distinct on (m.conversation_id)
    m.conversation_id,
    m.role,
    m.content,
    m.metadata
  from public.messages as m
  order by m.conversation_id, m.created_at desc, m.id desc
)
update public.conversations as c
set last_message_preview = null
from latest_messages as latest
where latest.conversation_id = c.id
  and latest.role = 'assistant'
  and jsonb_typeof(latest.metadata -> 'clarification') = 'object'
  and (
    latest.metadata -> 'clarification' ->> 'prompt_source'
  ) is distinct from 'llm_generated'
  and c.last_message_preview = left(
    regexp_replace(btrim(latest.content), '\s+', ' ', 'g'),
    180
  );
