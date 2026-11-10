-- Private observations retain questions and outcomes without classifying them.
-- Accepted turns link canonical messages; rejected requests own their raw facts.
create table public.refusal_observations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  request_id text not null check (length(request_id) > 0),
  -- Rejected requests may supply nonexistent, malformed, or foreign target ids.
  -- This field is never an ownership proof or a foreign key to that target.
  conversation_id text,
  request_message_id uuid references public.messages(id) on delete cascade,
  response_message_id uuid unique references public.messages(id) on delete cascade,
  asked text,
  action jsonb check (action is null or jsonb_typeof(action) = 'object'),
  outcome jsonb check (outcome is null or jsonb_typeof(outcome) = 'object'),
  status_code integer not null,
  created_at timestamptz not null default now(),
  constraint refusal_observations_shape_check check (
    (
      request_message_id is not null and response_message_id is not null
      and conversation_id is not null and status_code = 200
      and asked is null and action is null and outcome is null
    )
    or (
      request_message_id is null and response_message_id is null
      and asked is not null and outcome is not null
      and status_code between 400 and 599
    )
  )
);

create index refusal_observations_user_created_idx
  on public.refusal_observations (user_id, created_at desc);
create index refusal_observations_created_idx
  on public.refusal_observations (created_at desc);
create index refusal_observations_request_message_idx
  on public.refusal_observations (request_message_id)
  where request_message_id is not null;

-- Validate ownership without adding duplicate owner columns/indexes to messages.
-- Message identity, conversation, and role are immutable canonical facts.
create function public.validate_refusal_observation_pair()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if new.response_message_id is not null then
    if not exists (
      select 1
      from public.messages request_message
      join public.messages response_message
        on response_message.id = new.response_message_id
      where request_message.id = new.request_message_id
        and request_message.user_id = new.user_id
        and response_message.user_id = new.user_id
        and request_message.conversation_id::text = new.conversation_id
        and response_message.conversation_id = request_message.conversation_id
        and request_message.role = 'user'
        and response_message.role = 'assistant'
        and (
          response_message.metadata #>> '{agent_runtime_turn,turn_id}' is null
          or response_message.metadata #>> '{agent_runtime_turn,turn_id}'
            = new.request_message_id::text
        )
    ) then
      raise check_violation using message = 'Invalid refusal observation message pair';
    end if;
  end if;
  return new;
end;
$$;

create trigger refusal_observation_pair_guard
  before insert on public.refusal_observations
  for each row execute function public.validate_refusal_observation_pair();

alter table public.refusal_observations enable row level security;
revoke all on public.refusal_observations from public, anon, authenticated, service_role;
grant insert, select on public.refusal_observations to service_role;
revoke all on function public.validate_refusal_observation_pair()
  from public, anon, authenticated;
grant execute on function public.validate_refusal_observation_pair() to service_role;

-- No timestamp pairing, fallback transcript search, or write-time adjudication.
-- A linked row always reads message truth; a rejected row never joins a target.
create view public.refusal_log
with (security_invoker = true)
as
select
  observation.id,
  observation.created_at,
  observation.user_id,
  observation.request_id,
  observation.conversation_id,
  observation.request_message_id,
  observation.response_message_id,
  observation.status_code,
  case when observation.response_message_id is not null
    then request_message.content else observation.asked end as asked,
  case when observation.response_message_id is not null
    then request_message.metadata -> 'chat_action' else observation.action end as action,
  case when observation.response_message_id is not null
    then response_message.metadata else observation.outcome end as outcome,
  response_message.content as response
from public.refusal_observations observation
left join public.messages request_message
  on request_message.id = observation.request_message_id
  and request_message.user_id = observation.user_id
  and request_message.conversation_id::text = observation.conversation_id
left join public.messages response_message
  on response_message.id = observation.response_message_id
  and response_message.user_id = observation.user_id
  and response_message.conversation_id::text = observation.conversation_id;

revoke all on public.refusal_log from public, anon, authenticated, service_role;
grant select on public.refusal_log to service_role;

comment on table public.refusal_observations is
  'Private unclassified terminal chat observations and rejected action requests.';
comment on view public.refusal_log is
  'Service-only questions and exact outcomes, with semantic judgment left to readers.';
