alter table public.financial_import_events
    add constraint financial_import_events_id_space_key unique (id, owner_space_id),
    add constraint financial_import_events_business_resolution_check check (
        not (resolution ? 'business') or (
            owner_space_id is not null
            and jsonb_typeof(resolution->'business') = 'object'
            and resolution->'business'->>'schema_version' = '1'
            and jsonb_typeof(resolution->'business'->'facts') = 'object'
        ) is true
    );

alter table public.financial_source_connections
    add constraint financial_source_connections_id_space_key unique (id, owner_space_id);

drop policy financial_import_events_owner_select on public.financial_import_events;
create policy financial_import_events_owner_select on public.financial_import_events
    for select to authenticated
    using (
        (select auth.uid()) = user_id and owner_space_id is null
        and ((select auth.jwt())->>'is_anonymous') is distinct from 'true'
    );

drop policy financial_import_observations_owner_select
    on public.financial_import_observations;
create policy financial_import_observations_owner_select
    on public.financial_import_observations for select to authenticated
    using (
        (select auth.uid()) = user_id
        and ((select auth.jwt())->>'is_anonymous') is distinct from 'true'
        and exists (
            select 1 from public.financial_import_events e
            where e.id = event_id and e.owner_space_id is null
        )
    );

create table public.business_client_grants (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    grantee_id uuid not null references auth.users(id) on delete cascade,
    issuer_id uuid not null references auth.users(id) on delete cascade,
    capabilities text[] not null check (
        cardinality(capabilities) > 0
        and capabilities <@ array['read', 'prepare', 'approve']::text[]
        and array_position(capabilities, null) is null
    ),
    created_at timestamptz not null default now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    unique (id, space_id),
    check (expires_at is null or expires_at > created_at),
    check (revoked_at is null or revoked_at >= created_at)
);
create index business_client_grants_lookup_idx
    on public.business_client_grants (space_id, grantee_id) where revoked_at is null;
create index business_client_grants_grantee_idx on public.business_client_grants(grantee_id);
create index business_client_grants_issuer_idx on public.business_client_grants(issuer_id);

create table public.business_sources (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    kind text not null check (kind in ('message', 'attachment', 'agent_proposal', 'web_action')),
    channel text not null check (channel in ('web', 'whatsapp')),
    check (kind <> 'web_action' or channel = 'web'),
    source_key text not null check (char_length(source_key) between 1 and 200),
    text_content text,
    connection_id uuid,
    received_at timestamptz not null,
    unique (id, space_id),
    unique (space_id, source_key),
    foreign key (connection_id, space_id)
        references public.financial_source_connections(id, owner_space_id) on delete cascade,
    check (
        (kind = 'attachment' and connection_id is not null and text_content is null)
        or (kind in ('message', 'agent_proposal', 'web_action') and connection_id is null
            and char_length(text_content) between 1 and 20000) is true
    )
);
create index business_sources_connection_idx on public.business_sources(connection_id);

create table public.business_draft_sources (
    space_id uuid not null,
    draft_id uuid not null,
    source_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (draft_id, source_id),
    foreign key (draft_id, space_id)
        references public.financial_import_events(id, owner_space_id) on delete cascade,
    foreign key (source_id, space_id)
        references public.business_sources(id, space_id) on delete cascade
);
create index business_draft_sources_source_idx on public.business_draft_sources(source_id);

create table public.business_draft_revisions (
    space_id uuid not null,
    draft_id uuid not null,
    version integer not null check (version >= 1),
    actor jsonb not null check (
        jsonb_typeof(actor) = 'object'
        and actor ?& array['actor_id', 'actor_kind', 'display_name', 'grant_id',
                          'issuer_id', 'issuer_display_name']
    ),
    before_facts jsonb check (jsonb_typeof(before_facts) = 'object'),
    after_facts jsonb not null check (jsonb_typeof(after_facts) = 'object'),
    source_ids uuid[] not null default '{}',
    turn_key text,
    created_at timestamptz not null default now(),
    primary key (draft_id, version),
    foreign key (draft_id, space_id)
        references public.financial_import_events(id, owner_space_id) on delete cascade
);

create table public.business_questions (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null,
    draft_id uuid not null,
    field text not null check (field in (
        'kind', 'amount', 'currency', 'occurred_on', 'counterparty', 'funding',
        'business_share', 'receipt_state', 'category_id'
    )),
    asked_of text not null check (asked_of in ('owner', 'accountant')),
    channel text not null check (channel in ('web', 'whatsapp')),
    state text not null check (state in (
        'open', 'answered', 'owner_does_not_know', 'waiting_for_window', 'withdrawn'
    )),
    prompt text not null check (char_length(prompt) between 1 and 500),
    allowed_answers text[] not null check (
        cardinality(allowed_answers) > 0
        and allowed_answers <@ array['known', 'owner_does_not_know']::text[]
        and array_position(allowed_answers, null) is null
    ),
    answer_source_id uuid,
    created_at timestamptz not null default now(),
    foreign key (draft_id, space_id)
        references public.financial_import_events(id, owner_space_id) on delete cascade,
    foreign key (answer_source_id, space_id)
        references public.business_sources(id, space_id) on delete cascade,
    check (state not in ('answered', 'owner_does_not_know') or answer_source_id is not null),
    check (state <> 'owner_does_not_know' or asked_of = 'accountant')
);
create index business_questions_draft_idx on public.business_questions(draft_id);
create index business_questions_source_idx on public.business_questions(answer_source_id);
create index business_questions_open_idx on public.business_questions(space_id, created_at)
    where state in ('open', 'owner_does_not_know', 'waiting_for_window');

create table public.business_sender_leases (
    space_id uuid not null references public.spaces(id) on delete cascade,
    sender_hash text not null check (sender_hash ~ '^[0-9a-f]{64}$'),
    holder uuid not null,
    fence bigint not null check (fence >= 1),
    lease_until timestamptz not null,
    primary key (space_id, sender_hash)
);

create table public.business_turns (
    turn_key text primary key check (char_length(turn_key) between 1 and 200),
    space_id uuid not null references public.spaces(id) on delete cascade,
    sender_hash text not null check (sender_hash ~ '^[0-9a-f]{64}$'),
    actor_id uuid not null references auth.users(id) on delete cascade,
    arrival_sequence bigint generated always as identity,
    phase text not null default 'captured' check (phase in (
        'captured', 'turn_running', 'turn_done', 'reply_pending', 'reply_sent', 'reply_unknown'
    )),
    model_state text not null default 'not_started'
        check (model_state in ('not_started', 'running', 'completed', 'unknown')),
    plan jsonb,
    plan_actor jsonb,
    lease_fence bigint check (lease_fence >= 1),
    reply_text text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (turn_key, space_id, actor_id),
    check ((model_state = 'completed') = (plan is not null)),
    check ((plan is null) = (plan_actor is null)),
    check (plan_actor is null or (
        jsonb_typeof(plan_actor) = 'object'
        and plan_actor->>'actor_id' = actor_id::text
        and plan_actor->>'actor_kind' in ('owner_via_agent', 'member', 'extractor')
        and jsonb_typeof(plan_actor->'display_name') = 'string'
        and jsonb_typeof(plan_actor->'grant_id') = 'string'
        and jsonb_typeof(plan_actor->'issuer_id') = 'string'
        and jsonb_typeof(plan_actor->'issuer_display_name') = 'string'
    ) is true),
    check (plan is null or (
        jsonb_typeof(plan) = 'object' and plan->>'schema_version' = '1'
        and jsonb_typeof(plan->'actions') = 'array'
        and jsonb_array_length(plan->'actions') <= 8
    ) is true),
    check (phase not in ('turn_done', 'reply_pending', 'reply_sent', 'reply_unknown')
        or plan is not null)
);
create index business_turns_sender_order_idx
    on public.business_turns(space_id, sender_hash, arrival_sequence);
create index business_turns_actor_idx on public.business_turns(actor_id);

create table public.business_action_receipts (
    space_id uuid not null references public.spaces(id) on delete cascade,
    actor_id uuid not null references auth.users(id) on delete cascade,
    actor jsonb not null check ((
        jsonb_typeof(actor) = 'object'
        and actor->>'actor_id' = actor_id::text
        and actor->>'actor_kind' in ('owner_via_agent', 'member', 'extractor')
        and jsonb_typeof(actor->'display_name') = 'string'
        and jsonb_typeof(actor->'grant_id') = 'string'
        and jsonb_typeof(actor->'issuer_id') = 'string'
        and jsonb_typeof(actor->'issuer_display_name') = 'string'
    ) is true),
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 80),
    input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
    command jsonb not null check (jsonb_typeof(command) = 'object'),
    turn_key text,
    action_index integer check (action_index >= 0),
    outcome jsonb check (outcome is null or (jsonb_typeof(outcome) = 'object' and outcome->>'outcome' in (
        'applied', 'replayed', 'stale_version', 'not_found', 'permission_denied',
        'invalid_input', 'idempotency_conflict', 'outcome_unknown'
    )) is true),
    created_at timestamptz not null default now(),
    primary key (space_id, actor_id, idempotency_key),
    unique (turn_key, action_index),
    foreign key (turn_key, space_id, actor_id)
        references public.business_turns(turn_key, space_id, actor_id) on delete cascade,
    check ((turn_key is null) = (action_index is null)),
    check (turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense')) is true)
);
create index business_action_receipts_actor_idx on public.business_action_receipts(actor_id);

create function argus_private.business_immutable_evidence()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'DELETE' and pg_trigger_depth() > 1 then
        return old;
    end if;
    raise exception 'business_evidence_immutable' using errcode = '23514';
end;
$$;

create trigger business_revision_immutable before update or delete
    on public.business_draft_revisions for each row
    execute function argus_private.business_immutable_evidence();
create trigger business_source_immutable before update or delete
    on public.business_sources for each row
    execute function argus_private.business_immutable_evidence();

create function argus_private.business_revision_sources_scoped()
returns trigger language plpgsql set search_path = '' as $$
declare
    source_id uuid;
begin
    for source_id in select unnest(new.source_ids) order by 1 loop
        perform 1 from public.business_sources s
         where s.id = source_id and s.space_id = new.space_id
         for key share;
        if not found then
            raise exception 'business_revision_source_not_found' using errcode = '23503';
        end if;
    end loop;
    return new;
end;
$$;
create trigger business_revision_sources_scoped before insert
    on public.business_draft_revisions for each row
    execute function argus_private.business_revision_sources_scoped();

create function argus_private.business_plan_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if old.plan is not null and (new.plan, new.plan_actor)
        is distinct from (old.plan, old.plan_actor) then
        raise exception 'business_plan_immutable' using errcode = '23514';
    end if;
    if (new.turn_key, new.space_id, new.sender_hash, new.actor_id, new.arrival_sequence)
        is distinct from
       (old.turn_key, old.space_id, old.sender_hash, old.actor_id, old.arrival_sequence) then
        raise exception 'business_turn_identity_immutable' using errcode = '23514';
    end if;
    return new;
end;
$$;
create trigger business_plan_immutable before update on public.business_turns
    for each row execute function argus_private.business_plan_immutable();

create function argus_private.business_receipt_plan_required()
returns trigger language plpgsql set search_path = '' as $$
declare
    saved_action jsonb;
    saved_actor jsonb;
begin
    if tg_op = 'UPDATE' then
        if (new.space_id, new.actor_id, new.idempotency_key, new.input_hash,
            new.command, new.turn_key, new.action_index, new.actor)
            is distinct from
           (old.space_id, old.actor_id, old.idempotency_key, old.input_hash,
            old.command, old.turn_key, old.action_index, old.actor) then
            raise exception 'business_action_identity_immutable' using errcode = '23514';
        end if;
        if old.outcome is not null and (
            new.outcome is null or (old.outcome->>'outcome' <> 'outcome_unknown'
                and new.outcome is distinct from old.outcome)
        ) then
            raise exception 'business_action_outcome_immutable' using errcode = '23514';
        end if;
    end if;
    if new.turn_key is not null then
        select t.plan->'actions'->new.action_index, t.plan_actor
          into saved_action, saved_actor
          from public.business_turns t
         where t.turn_key = new.turn_key and t.space_id = new.space_id
           and t.actor_id = new.actor_id;
        if saved_action is null or saved_action <> new.command
            or saved_actor is distinct from new.actor then
            raise exception 'business_action_plan_required' using errcode = '23514';
        end if;
    end if;
    return new;
end;
$$;
create trigger business_receipt_plan_required before insert or update
    on public.business_action_receipts for each row
    execute function argus_private.business_receipt_plan_required();

alter table public.business_client_grants enable row level security;
alter table public.business_sources enable row level security;
alter table public.business_draft_sources enable row level security;
alter table public.business_draft_revisions enable row level security;
alter table public.business_questions enable row level security;
alter table public.business_sender_leases enable row level security;
alter table public.business_turns enable row level security;
alter table public.business_action_receipts enable row level security;

revoke all on public.business_client_grants, public.business_sources,
    public.business_draft_sources, public.business_draft_revisions,
    public.business_questions, public.business_sender_leases, public.business_turns,
    public.business_action_receipts from public, anon, authenticated, service_role;
grant select, insert, update, delete on public.business_client_grants, public.business_sources,
    public.business_draft_sources, public.business_questions,
    public.business_sender_leases, public.business_turns,
    public.business_action_receipts to service_role;
grant select, insert on public.business_draft_revisions to service_role;
revoke all on sequence public.business_turns_arrival_sequence_seq
    from public, anon, authenticated, service_role;
grant usage, select on sequence public.business_turns_arrival_sequence_seq to service_role;

revoke all on function argus_private.business_immutable_evidence(),
    argus_private.business_plan_immutable(), argus_private.business_receipt_plan_required(),
    argus_private.business_revision_sources_scoped()
    from public, anon, authenticated;
