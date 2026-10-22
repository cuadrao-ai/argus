begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

create table argus_private.business_departure_aliases (
    space_id uuid not null references public.spaces(id) on delete cascade,
    actor_id uuid not null unique,
    departing_user_id uuid,
    deletion_run_id uuid not null references argus_private.account_deletion_runs(id),
    claim_id uuid,
    started_at timestamptz not null default clock_timestamp(),
    identity_cleaned_at timestamptz,
    primary key(space_id,actor_id),
    check((departing_user_id is null)=(identity_cleaned_at is not null)),
    check((claim_id is null)=(identity_cleaned_at is not null))
);
create index business_departure_run_idx on argus_private.business_departure_aliases(deletion_run_id);
alter table argus_private.business_departure_aliases enable row level security;
revoke all on argus_private.business_departure_aliases from public,anon,authenticated,service_role;
comment on table argus_private.business_departure_aliases is 'Scoped anonymous historical actors with no Auth or access grant. Departed identity and claim exist only until verified Auth absence; aliases expire with Business purge.';

create or replace function argus_private.business_historical_actor() returns trigger
language plpgsql set search_path='' as $$
begin
    if not exists(select 1 from auth.users where id=new.actor_id)
       and not exists(select 1 from argus_private.business_custody_reservations
           where space_id=new.space_id and deleted_actor_id=new.actor_id)
       and not exists(select 1 from argus_private.business_departure_aliases
           where space_id=new.space_id and actor_id=new.actor_id) then
        raise exception 'business_actor_not_found' using errcode='23503';
    end if;
    return new;
end;
$$;
create or replace function argus_private.business_historical_owner() returns trigger
language plpgsql set search_path='' as $$
begin
    if not exists(select 1 from auth.users where id=new.owner_id)
       and not exists(select 1 from argus_private.business_custody_reservations
           where space_id=new.space_id and deleted_actor_id=new.owner_id)
       and not exists(select 1 from argus_private.business_departure_aliases
           where space_id=new.space_id and actor_id=new.owner_id) then
        raise exception 'business_historical_owner_not_found' using errcode='23503';
    end if;
    return new;
end;
$$;

alter function argus_private.business_custody_identity_change(text,jsonb,jsonb)
    rename to business_custody_graph_identity_change;
create function argus_private.business_custody_identity_change(p_table text,p_old jsonb,p_new jsonb)
returns boolean language plpgsql set search_path='' as $$
declare m record; expected jsonb; k text; v_actor uuid; v_issuer uuid;
begin
    if argus_private.business_custody_graph_identity_change(p_table,p_old,p_new) then return true; end if;
    if current_user<>'postgres' or coalesce(current_setting('argus.business_departure_actor',true),'')='' then
        return false;
    end if;
    v_actor:=current_setting('argus.business_departure_actor')::uuid;
    select a.*,s.created_by,s.current_owner_id into m
        from argus_private.business_departure_aliases a
        join public.spaces s on s.id=a.space_id
        join argus_private.account_deletion_runs d on d.id=a.deletion_run_id
        where a.actor_id=v_actor and a.departing_user_id=d.user_id and a.claim_id=d.claim_id
            and d.claimed_until>clock_timestamp() and d.status<>'done';
    if not found or p_old->>'space_id' is distinct from m.space_id::text
        or p_table<>all(array['business_sources','business_draft_revisions','business_draft_sources',
            'business_questions','business_turns','business_action_receipts','business_client_grants',
            'business_access_invites','business_receipt_reading_consents','business_receipt_consent_commands',
            'business_ai_consents','business_lifecycle_commands','business_ownership_transfers',
            'business_whatsapp_ai_consents']) then return false; end if;
    expected:=argus_private.business_custody_identity_json(p_old,m.departing_user_id::text,m.departing_user_id::text,m.actor_id::text);
    foreach k in array array['owner_id','target_id','historical_issuer_id'] loop
        if p_old->>k=m.departing_user_id::text then
            expected:=expected||jsonb_build_object(k,m.actor_id);
        end if;
    end loop;
    if p_table=any(array['business_client_grants','business_access_invites']) and p_old->>'issuer_id'=m.departing_user_id::text then
        v_issuer:=coalesce(m.current_owner_id,m.created_by);
        expected:=expected||jsonb_build_object('issuer_id',v_issuer,'historical_issuer_id',m.actor_id);
    elsif p_table='business_turns' and p_old->>'actor_id'=m.departing_user_id::text then
        expected:=expected||jsonb_build_object('sender_hash',encode(extensions.digest(m.actor_id::text,'sha256'),'hex'));
    elsif p_table='business_sources' and starts_with(p_old->>'source_key','web:'||m.departing_user_id::text||':') then
        expected:=expected||jsonb_build_object('source_key','web:'||m.actor_id::text||':'||substr(p_old->>'source_key',42));
    end if;
    if p_table='business_action_receipts' and p_old->'command' is distinct from expected->'command' then
        expected:=expected||jsonb_build_object('input_hash',p_new->'input_hash');
    end if;
    return expected=p_new and exists(select 1 from argus_private.business_custody_changes
        where space_id=m.space_id and table_name=p_table and old_row=p_old and new_row=p_new);
end;
$$;
revoke all on function argus_private.business_custody_identity_change(text,jsonb,jsonb),
    argus_private.business_custody_graph_identity_change(text,jsonb,jsonb) from public,anon,authenticated,service_role;

-- Keep the existing graph and transfer-outbox checks on every Auth delete.
do $$
declare body text;
begin
    body:=pg_get_functiondef('argus_private.business_auth_retention_guard()'::regprocedure);
    body:=regexp_replace(body,'\mbegin\M','begin
    if exists(select 1 from public.spaces where kind=''business'' and (created_by=old.id or current_owner_id=old.id)) then
        raise exception ''business_custody_identity_detachment_required'' using errcode=''23514'';
    end if;', 'i');
    execute body;
end;
$$;
commit;
