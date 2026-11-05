begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

create table public.business_fiscal_operations (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    environment text not null default 'sandbox' check(environment='sandbox'),
    document_key text not null,
    account_key text not null,
    company_id text not null,
    issuer text not null,
    kind text not null check(kind in ('E31','E32')),
    number text not null check(number ~ '^E3[12][0-9]{10}$'),
    case_data jsonb not null check(octet_length(case_data::text)<=65536),
    payload_digest text not null check(payload_digest ~ '^[a-f0-9]{64}$'),
    prepared_actor jsonb not null,
    approved_actor jsonb,
    contact_token uuid,
    contacted_at timestamptz,
    provider_id text check(length(provider_id)<=120),
    attempts integer not null default 0 check(attempts between 0 and 20),
    next_check timestamptz not null default clock_timestamp(),
    lease_token uuid,
    lease_until timestamptz,
    created_at timestamptz not null default clock_timestamp(),
    unique(id,space_id),
    unique(space_id,document_key),
    unique(environment,account_key,company_id,kind,number),
    unique(environment,account_key,issuer,kind,number),
    unique(environment,account_key,company_id,provider_id),
    check((contact_token is null)=(contacted_at is null)),
    check((contact_token is null)=(approved_actor is null)),
    check(provider_id is null or contact_token is not null)
);
create table public.business_fiscal_observations (
    id bigint generated always as identity primary key,
    space_id uuid references public.spaces(id) on delete cascade,
    operation_id uuid,
    event_digest text not null check(event_digest ~ '^[a-f0-9]{64}$'),
    source text not null check(source in ('response','callback','poll','artifact','unknown','conflict')),
    disposition text not null check(disposition in ('applied','quarantined')),
    evidence jsonb not null check(octet_length(evidence::text)<=16384),
    created_at timestamptz not null default clock_timestamp(),
    foreign key(operation_id,space_id) references public.business_fiscal_operations(id,space_id) on delete cascade,
    unique(source,event_digest),
    check((operation_id is null)=(space_id is null)),
    check((operation_id is null)=(disposition='quarantined'))
);
create index business_fiscal_recovery_idx on public.business_fiscal_operations(next_check)
    where contacted_at is not null and attempts<20;
create index business_fiscal_evidence_idx on public.business_fiscal_observations(operation_id,id);
alter table public.business_fiscal_operations enable row level security;
alter table public.business_fiscal_observations enable row level security;
revoke all on public.business_fiscal_operations,public.business_fiscal_observations from public,anon,authenticated,service_role;
grant select,insert,update on public.business_fiscal_operations to service_role;
grant select,insert on public.business_fiscal_observations to service_role;
grant usage,select on sequence public.business_fiscal_observations_id_seq to service_role;

-- Extend only the two new families in the audited identity rewrite. Existing
-- identity branches retain their original bodies and validation rules.
alter function argus_private.business_custody_identity_change(text,jsonb,jsonb)
    rename to business_custody_before_fiscal_identity_change;
create function argus_private.business_custody_identity_change(p_table text,p_old jsonb,p_new jsonb)
returns boolean language plpgsql set search_path='' as $$
declare m record; expected jsonb; actor uuid;
begin
    if p_table<>all(array['business_fiscal_operations','business_fiscal_observations']) then
        return argus_private.business_custody_before_fiscal_identity_change(p_table,p_old,p_new);
    end if;
    if current_user<>'postgres' then return false; end if;
    if coalesce(current_setting('argus.business_custody_space',true),'')<>'' then
        -- Existing custody validation is generic for typed JSON identities.
        return argus_private.business_custody_graph_identity_change(p_table,p_old,p_new);
    end if;
    if coalesce(current_setting('argus.business_departure_actor',true),'')='' then return false; end if;
    actor:=current_setting('argus.business_departure_actor')::uuid;
    select a.* into m from argus_private.business_departure_aliases a
        join argus_private.account_deletion_runs d on d.id=a.deletion_run_id
        where a.actor_id=actor and a.departing_user_id=d.user_id and a.claim_id=d.claim_id
        and d.claimed_until>clock_timestamp() and d.status<>'done';
    if not found or p_old->>'space_id' is distinct from m.space_id::text then return false; end if;
    expected:=argus_private.business_custody_identity_json(p_old,m.departing_user_id::text,m.departing_user_id::text,m.actor_id::text);
    return expected=p_new and exists(select 1 from argus_private.business_custody_changes
        where space_id=m.space_id and table_name=p_table and old_row=p_old and new_row=p_new);
end;
$$;
create function argus_private.business_fiscal_immutable() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if argus_private.business_custody_identity_change(tg_table_name,to_jsonb(old),to_jsonb(new)) then return new; end if;
    if tg_table_name='business_fiscal_observations' then
        raise exception 'fiscal_evidence_immutable' using errcode='23514';
    end if;
    if (to_jsonb(new)-array['approved_actor','contact_token','contacted_at','provider_id','attempts','next_check','lease_token','lease_until'])
       is distinct from (to_jsonb(old)-array['approved_actor','contact_token','contacted_at','provider_id','attempts','next_check','lease_token','lease_until'])
       or (old.contact_token is not null and (new.contact_token is distinct from old.contact_token or new.contacted_at is distinct from old.contacted_at or new.approved_actor is distinct from old.approved_actor))
       or (old.provider_id is not null and new.provider_id is distinct from old.provider_id)
       or new.attempts<old.attempts then
        raise exception 'fiscal_intent_immutable' using errcode='23514';
    end if;
    return new;
end;
$$;
create trigger business_fiscal_operation_immutable before update on public.business_fiscal_operations
    for each row execute function argus_private.business_fiscal_immutable();
create trigger business_fiscal_observation_immutable before update on public.business_fiscal_observations
    for each row execute function argus_private.business_fiscal_immutable();
-- Auth deletion cannot silently leave raw provenance behind. The existing graph
-- moves nested actor/issuer IDs before this check can pass.
create function argus_private.business_fiscal_actor_retained() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if exists(select 1 from public.business_fiscal_operations o where
        o.prepared_actor->>'actor_id'=old.id::text or o.prepared_actor->>'issuer_id'=old.id::text
        or o.approved_actor->>'actor_id'=old.id::text or o.approved_actor->>'issuer_id'=old.id::text) then
        raise exception 'business_custody_identity_detachment_required' using errcode='23514';
    end if;
    return old;
end;
$$;
create trigger business_fiscal_actor_retained before delete on auth.users
    for each row execute function argus_private.business_fiscal_actor_retained();
revoke all on function argus_private.business_fiscal_immutable(),argus_private.business_fiscal_actor_retained(),
    argus_private.business_custody_identity_change(text,jsonb,jsonb),
    argus_private.business_custody_before_fiscal_identity_change(text,jsonb,jsonb) from public,anon,authenticated,service_role;
comment on table public.business_fiscal_operations is 'Synthetic sandbox intent only. Committed contact is permanent; unknown never authorizes create. No financial ledger effect. Business purge cascades; actor provenance follows audited custody.';
comment on table public.business_fiscal_observations is 'Server-only bounded semantic evidence. Authenticated unmatched callbacks remain quarantined. Private artifact locators never reach API output. No raw callback or free-text diagnostic payload.';
commit;
