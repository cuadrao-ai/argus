-- One current-state recovery row for each accepted ordinary chat turn.
-- This is not a queue, transcript, semantic store, or LangGraph replacement.

create table public.chat_turn_lifecycles (
  turn_id uuid primary key references public.messages(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  conversation_id uuid not null
    references public.conversations(id) on delete cascade,
  assistant_message_id uuid unique
    references public.messages(id) on delete set null,
  request_id text not null check (nullif(btrim(request_id), '') is not null),
  status text not null default 'accepted'
    check (
      status in (
        'accepted',
        'running',
        'completed',
        'recoverable_failed',
        'abandoned',
        'reconciled'
      )
    ),
  reconciled_outcome text,
  failure_code text,
  retryable boolean not null default false,
  accepted_at timestamptz not null default now(),
  running_at timestamptz,
  terminal_at timestamptz,
  reconciled_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chat_turn_lifecycles_reconciled_outcome_check check (
    (
      status = 'reconciled'
      and reconciled_outcome in ('completed', 'recoverable_failed')
    )
    or (
      status <> 'reconciled'
      and reconciled_outcome is null
    )
  ),
  constraint chat_turn_lifecycles_timestamp_shape_check check (
    (
      status = 'accepted'
      and running_at is null
      and terminal_at is null
      and reconciled_at is null
    )
    or (
      status = 'running'
      and running_at is not null
      and terminal_at is null
      and reconciled_at is null
    )
    or (
      status in ('completed', 'recoverable_failed', 'abandoned')
      and terminal_at is not null
      and reconciled_at is null
    )
    or (
      status = 'reconciled'
      and terminal_at is not null
      and reconciled_at is not null
    )
  ),
  constraint chat_turn_lifecycles_abandoned_shape_check check (
    status <> 'abandoned'
    or (
      assistant_message_id is null
      and failure_code = 'turn_abandoned'
      and retryable = true
    )
  )
);

create index chat_turn_lifecycles_conversation_status_idx
  on public.chat_turn_lifecycles (
    conversation_id,
    status,
    updated_at
  );

create index chat_turn_lifecycles_user_status_idx
  on public.chat_turn_lifecycles (
    user_id,
    status,
    updated_at
  );

alter table public.chat_turn_lifecycles enable row level security;

create policy "chat_turn_lifecycles_owner_select"
  on public.chat_turn_lifecycles
  for select
  to authenticated
  using ((select auth.uid()) = user_id);

revoke all on public.chat_turn_lifecycles from anon, authenticated;
grant select on public.chat_turn_lifecycles to authenticated;
grant select, insert, update, delete on public.chat_turn_lifecycles
  to service_role;
revoke insert, update, delete on public.chat_turn_lifecycles
  from anon, authenticated;

create or replace function public.transition_chat_turn(
  p_turn_id uuid,
  p_to_status text,
  p_assistant_message_id uuid,
  p_reconciled_outcome text,
  p_failure_code text,
  p_retryable boolean
)
returns jsonb
language plpgsql
security invoker
set search_path = public
set timezone = 'UTC'
as $$
declare
  v_turn public.chat_turn_lifecycles%rowtype;
  v_message public.messages%rowtype;
  v_expected_message_status text;
  v_retryable boolean := coalesce(p_retryable, false);
  v_now timestamptz := clock_timestamp();
begin
  select l.*
    into v_turn
    from public.chat_turn_lifecycles as l
   where l.turn_id = p_turn_id
   for update;

  if not found then
    return jsonb_build_object('outcome', 'missing', 'row', null);
  end if;

  if p_to_status = 'running' then
    if p_assistant_message_id is not null
       or p_reconciled_outcome is not null
       or p_failure_code is not null
       or v_retryable then
      return jsonb_build_object(
        'outcome', 'invalid',
        'row', to_jsonb(v_turn)
      );
    end if;
  elsif p_to_status = 'completed' then
    if p_assistant_message_id is null
       or p_reconciled_outcome is not null
       or p_failure_code is not null
       or v_retryable then
      return jsonb_build_object(
        'outcome', 'invalid',
        'row', to_jsonb(v_turn)
      );
    end if;
  elsif p_to_status = 'recoverable_failed' then
    if p_assistant_message_id is null
       or p_reconciled_outcome is not null then
      return jsonb_build_object(
        'outcome', 'invalid',
        'row', to_jsonb(v_turn)
      );
    end if;
  elsif p_to_status = 'abandoned' then
    if p_assistant_message_id is not null
       or p_reconciled_outcome is not null
       or p_failure_code is distinct from 'turn_abandoned'
       or not v_retryable then
      return jsonb_build_object(
        'outcome', 'invalid',
        'row', to_jsonb(v_turn)
      );
    end if;
  elsif p_to_status = 'reconciled' then
    if p_assistant_message_id is null
       or p_reconciled_outcome not in ('completed', 'recoverable_failed')
       or (
         p_reconciled_outcome = 'completed'
         and (p_failure_code is not null or v_retryable)
       ) then
      return jsonb_build_object(
        'outcome', 'invalid',
        'row', to_jsonb(v_turn)
      );
    end if;
  else
    return jsonb_build_object(
      'outcome', 'invalid',
      'row', to_jsonb(v_turn)
    );
  end if;

  if v_turn.status = p_to_status then
    if v_turn.assistant_message_id is not distinct from p_assistant_message_id
       and v_turn.reconciled_outcome
         is not distinct from p_reconciled_outcome
       and v_turn.failure_code is not distinct from p_failure_code
       and v_turn.retryable is not distinct from v_retryable then
      return jsonb_build_object(
        'outcome', 'noop',
        'row', to_jsonb(v_turn)
      );
    end if;
    return jsonb_build_object(
      'outcome', 'conflict',
      'row', to_jsonb(v_turn)
    );
  end if;

  if v_turn.status in (
    'completed',
    'recoverable_failed',
    'abandoned',
    'reconciled'
  ) then
    return jsonb_build_object(
      'outcome', 'conflict',
      'row', to_jsonb(v_turn)
    );
  end if;

  if v_turn.status not in ('accepted', 'running') then
    return jsonb_build_object(
      'outcome', 'conflict',
      'row', to_jsonb(v_turn)
    );
  end if;

  if not (
    (v_turn.status = 'accepted' and p_to_status = 'running')
    or (
      v_turn.status in ('accepted', 'running')
      and p_to_status in (
        'completed',
        'recoverable_failed',
        'abandoned',
        'reconciled'
      )
    )
  ) then
    return jsonb_build_object(
      'outcome', 'conflict',
      'row', to_jsonb(v_turn)
    );
  end if;

  if p_assistant_message_id is not null then
    select m.*
      into v_message
      from public.messages as m
     where m.id = p_assistant_message_id
       and m.user_id = v_turn.user_id
       and m.conversation_id = v_turn.conversation_id
       and m.role = 'assistant';

    v_expected_message_status := case
      when p_to_status = 'reconciled' then p_reconciled_outcome
      else p_to_status
    end;

    if not found
       or v_message.metadata #>> '{agent_runtime_turn,turn_id}'
         is distinct from v_turn.turn_id::text
       or v_message.metadata #>> '{agent_runtime_turn,request_id}'
         is distinct from v_turn.request_id
       or v_message.metadata #> '{agent_runtime_turn,terminal}'
         is distinct from 'true'::jsonb
       or v_message.metadata #>> '{agent_runtime_turn,status}'
         is distinct from v_expected_message_status
       or (
         v_expected_message_status = 'recoverable_failed'
         and (
           not (
             v_message.metadata -> 'agent_runtime_turn' ? 'failure_code'
           )
           or not (
             v_message.metadata -> 'agent_runtime_turn' ? 'retryable'
           )
           or jsonb_typeof(
             v_message.metadata #> '{agent_runtime_turn,retryable}'
           ) is distinct from 'boolean'
           or not (
             jsonb_typeof(
               v_message.metadata #> '{agent_runtime_turn,failure_code}'
             ) in ('string', 'null')
           )
           or v_message.metadata
             #>> '{agent_runtime_turn,failure_code}'
             is distinct from p_failure_code
           or v_message.metadata
             #> '{agent_runtime_turn,retryable}'
             is distinct from to_jsonb(v_retryable)
         )
       )
       or exists (
         select 1
           from public.chat_turn_lifecycles as linked
          where linked.assistant_message_id = p_assistant_message_id
            and linked.turn_id <> p_turn_id
       ) then
      return jsonb_build_object(
        'outcome', 'invalid',
        'row', to_jsonb(v_turn)
      );
    end if;
  end if;

  update public.chat_turn_lifecycles as l
     set status = p_to_status,
         assistant_message_id = p_assistant_message_id,
         reconciled_outcome = p_reconciled_outcome,
         failure_code = p_failure_code,
         retryable = v_retryable,
         running_at = case
           when p_to_status = 'running' then v_now
           else l.running_at
         end,
         terminal_at = case
           when p_to_status in (
             'completed',
             'recoverable_failed',
             'abandoned',
             'reconciled'
           ) then v_now
           else null
         end,
         reconciled_at = case
           when p_to_status = 'reconciled' then v_now
           else null
         end,
         updated_at = v_now
   where l.turn_id = p_turn_id
  returning l.* into v_turn;

  return jsonb_build_object(
    'outcome', 'applied',
    'row', to_jsonb(v_turn)
  );
end;
$$;

revoke all on function public.transition_chat_turn(
  uuid, text, uuid, text, text, boolean
) from public;
revoke all on function public.transition_chat_turn(
  uuid, text, uuid, text, text, boolean
) from anon;
revoke all on function public.transition_chat_turn(
  uuid, text, uuid, text, text, boolean
) from authenticated;
grant execute on function public.transition_chat_turn(
  uuid, text, uuid, text, text, boolean
) to service_role;
