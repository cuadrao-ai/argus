-- Keep pre-deployment handoffs claimable while allowing the neutral guest
-- simulation-limit reason introduced with the two-simulation policy.
create or replace function argus_private.valid_guest_pending_action(
  p_action jsonb,
  p_conversation_id uuid
)
returns boolean
language plpgsql
immutable
strict
set search_path = ''
as $$
declare
  v_key text;
  v_reason text;
begin
  if jsonb_typeof(p_action) <> 'object' then
    return false;
  end if;
  for v_key in select jsonb_object_keys(p_action)
  loop
    if v_key not in ('reason', 'conversation_id', 'action_id', 'artifact_id') then
      return false;
    end if;
  end loop;

  v_reason := p_action ->> 'reason';
  if v_reason not in (
    'second_simulation',
    'simulation_limit',
    'message_limit',
    'save_decision',
    'new_conversation',
    'keep_history'
  ) then
    return false;
  end if;
  if nullif(p_action ->> 'conversation_id', '') is distinct from p_conversation_id::text
     or nullif(p_action ->> 'action_id', '') is null then
    return false;
  end if;
  if v_reason = 'save_decision' then
    return nullif(p_action ->> 'artifact_id', '') is not null;
  end if;
  return not (p_action ? 'artifact_id');
end;
$$;

revoke all on function argus_private.valid_guest_pending_action(jsonb, uuid)
  from public, anon, authenticated;
grant execute on function argus_private.valid_guest_pending_action(jsonb, uuid)
  to service_role;
