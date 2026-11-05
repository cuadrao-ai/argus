begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

-- This private in-flight map is erased only after verified Auth deletion.
alter table argus_private.business_custody_reservations add column moved_at timestamptz;
alter table argus_private.business_custody_objects drop constraint business_custody_objects_pkey;
alter table argus_private.business_custody_objects add column id uuid not null default gen_random_uuid();
alter table argus_private.business_custody_objects add primary key(id);
alter table argus_private.business_custody_objects alter column source_path drop not null;
alter table argus_private.business_custody_objects add unique(space_id,source_path);

create table argus_private.business_custody_moves (
    space_id uuid primary key references public.spaces(id) on delete restrict,
    departing_user_id uuid,
    deletion_run_id uuid not null references argus_private.account_deletion_runs(id),
    claim_id uuid,
    started_at timestamptz not null default clock_timestamp(),
    identity_cleaned_at timestamptz
);
create table argus_private.business_custody_changes (
    space_id uuid not null references public.spaces(id) on delete restrict,
    table_name text not null,
    old_row jsonb not null,
    new_row jsonb not null
);
alter table argus_private.business_custody_moves enable row level security;
alter table argus_private.business_custody_changes enable row level security;
revoke all on argus_private.business_custody_moves,argus_private.business_custody_changes from public,anon,authenticated,service_role;

alter table public.business_client_grants add column historical_issuer_id uuid;
alter table public.business_access_invites add column historical_issuer_id uuid;
create function argus_private.business_custody_asset_actor(p_custodian uuid,p_actor uuid)
returns boolean language sql stable security definer set search_path='' as $$
    select p_custodian=p_actor or exists(select 1 from argus_private.business_custody_reservations
        where custodian_id=p_custodian and deleted_actor_id=p_actor);
$$;
revoke all on function argus_private.business_custody_asset_actor(uuid,uuid) from public,anon,authenticated;
grant execute on function argus_private.business_custody_asset_actor(uuid,uuid) to service_role;
alter table public.financial_asset_changes drop constraint financial_asset_changes_check;
alter table public.financial_asset_changes add constraint financial_asset_changes_actor check
    (argus_private.business_custody_asset_actor(user_id,recorded_by));
alter table public.business_whatsapp_ai_consents drop constraint business_whatsapp_ai_consents_check,
    drop constraint business_whatsapp_ai_consents_check2;
alter table public.business_whatsapp_ai_consents add constraint business_whatsapp_historical_actor check
    (argus_private.business_custody_asset_actor(owner_id,consenting_actor_id));
alter table public.business_whatsapp_ai_consents add constraint business_whatsapp_historical_revoker check
    (revoked_by is null or argus_private.business_custody_asset_actor(owner_id,revoked_by));
comment on column public.business_client_grants.historical_issuer_id is 'Anonymous former issuer. Operational issuer alone supplies present authority.';
comment on column public.business_access_invites.historical_issuer_id is 'Anonymous former issuer. Does not grant access or link to a departed person.';

-- A historical actor alias is scoped to its Business and has no Auth account.
alter table public.business_turns drop constraint business_turns_actor_id_fkey;
alter table public.business_action_receipts drop constraint business_action_receipts_actor_id_fkey;
create function argus_private.business_historical_actor() returns trigger
language plpgsql set search_path='' as $$
begin
    if not exists(select 1 from auth.users where id=new.actor_id)
       and not exists(select 1 from argus_private.business_custody_reservations
           where space_id=new.space_id and deleted_actor_id=new.actor_id) then
        raise exception 'business_actor_not_found' using errcode='23503';
    end if;
    return new;
end;
$$;
create constraint trigger business_turn_actor after insert or update on public.business_turns
    deferrable initially immediate for each row execute function argus_private.business_historical_actor();
create constraint trigger business_receipt_actor after insert or update on public.business_action_receipts
    deferrable initially immediate for each row execute function argus_private.business_historical_actor();
alter table public.business_receipt_reading_consents drop constraint business_receipt_reading_consents_owner_id_fkey;
alter table public.business_receipt_consent_commands drop constraint business_receipt_consent_commands_owner_id_fkey;
create function argus_private.business_historical_owner() returns trigger
language plpgsql set search_path='' as $$
begin
    if not exists(select 1 from auth.users where id=new.owner_id)
       and not exists(select 1 from argus_private.business_custody_reservations
           where space_id=new.space_id and deleted_actor_id=new.owner_id) then
        raise exception 'business_historical_owner_not_found' using errcode='23503';
    end if;
    return new;
end;
$$;
create constraint trigger business_reading_historical_owner after insert or update on public.business_receipt_reading_consents
    deferrable initially immediate for each row execute function argus_private.business_historical_owner();
create constraint trigger business_command_historical_owner after insert or update on public.business_receipt_consent_commands
    deferrable initially immediate for each row execute function argus_private.business_historical_owner();

-- Replacing the four Auth cascade keys must not permit dangling real identities
-- when an Admin deletion bypasses orchestration. This read-only definer owns
-- the invariant for every Auth writer, including GoTrue's restricted DB role.
create function argus_private.business_auth_retention_guard() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if exists(select 1 from public.business_turns where actor_id=old.id)
        or exists(select 1 from public.business_action_receipts where actor_id=old.id)
        or exists(select 1 from public.business_receipt_reading_consents where owner_id=old.id)
        or exists(select 1 from public.business_receipt_consent_commands where owner_id=old.id)
        or exists(select 1 from public.business_ai_consents where owner_id=old.id
            or consenting_actor_id=old.id or issuer_id=old.id or revoked_by=old.id) then
        raise exception 'business_custody_identity_detachment_required' using errcode='23514';
    end if;
    return old;
end;
$$;
revoke all on function argus_private.business_auth_retention_guard() from public,anon,authenticated,service_role;
create trigger business_auth_retention_guard before delete on auth.users
    for each row execute function argus_private.business_auth_retention_guard();

-- Exact keys moved by this writer. No update cascade or trigger is disabled.
create table argus_private.business_custody_deferred_keys(constraint_name text primary key);
insert into argus_private.business_custody_deferred_keys values
('financial_accounts_owner_space_fkey'),
('financial_source_connections_owner_space_fkey'),
('financial_import_events_owner_space_fkey'),
('financial_records_owner_funded_scope_fk'),
('conversations_owner_space_fkey'),
('financial_import_observations_event_id_user_id_fkey'),
('financial_import_account_links_account_id_user_id_fkey'),
('financial_asset_details_account_id_user_id_fkey'),
('financial_asset_details_related_debt_account_id_user_id_fkey'),
('financial_asset_changes_account_id_user_id_fkey'),
('financial_asset_changes_related_debt_account_id_user_id_fkey'),
('financial_asset_changes_previous_debt_account_id_user_id_fkey'),
('financial_activity_receipts_activity_id_user_id_fkey'),
('financial_activity_receipt_revision_fk'),
('financial_operation_receipts_record_id_account_id_user_id_fkey'),
('financial_operation_receipts_record_id_revision_user_id_fkey'),
('financial_observation_coverag_activity_id_account_id_user__fkey'),
('financial_observation_coverag_activity_id_activity_revisio_fkey'),
('financial_observation_coverag_observation_id_account_id_us_fkey'),
('financial_observation_coverag_observation_id_observation_r_fkey'),
('business_action_receipts_turn_key_space_id_actor_id_fkey'),
('financial_records_account_id_user_id_fkey'),
('financial_record_revisions_record_id_user_id_fkey'),
('financial_activity_current_revision_fk'),
('financial_activity_membership_revision_fk'),
('financial_activity_memberships_activity_id_user_id_fkey'),
('financial_activity_original_record_revision'),
('financial_activity_revisions_activity_id_user_id_fkey'),
('financial_payment_return_original_owner_fk'),
('financial_purchase_revision_owner_fk');
insert into argus_private.business_custody_deferred_keys values
('whatsapp_sender_links_destination_space_fkey'),('business_whatsapp_consent_original_link_fkey');
-- Month-close settlements follow their space and activity owner.
insert into argus_private.business_custody_deferred_keys values
('business_document_settlements_space_id_owner_id_fkey'),
('business_document_settlements_activity_id_owner_id_fkey');
do $$
declare k record;
begin
    for k in select c.conrelid::regclass as relation,c.conname,c.condeferred
        from pg_constraint c join argus_private.business_custody_deferred_keys names on names.constraint_name=c.conname
    loop
        execute format('alter table %s alter constraint %I deferrable initially %s',k.relation,k.conname,
            case when k.condeferred then 'deferred' else 'immediate' end);
    end loop;
    if exists(select 1 from argus_private.business_custody_deferred_keys names
        where not exists(select 1 from pg_constraint c where c.conname=names.constraint_name)) then
        raise exception 'business_custody_constraint_missing';
    end if;
end;
$$;
alter table argus_private.business_custody_deferred_keys enable row level security;
revoke all on argus_private.business_custody_deferred_keys from public,anon,authenticated,service_role;

-- Legacy immutable-history guards admit only a planned exact row mutation by
-- postgres under a live deletion claim and registered banned reserved principal.
-- The table is private and gives service_role no direct or indirect writer grant.
create function argus_private.business_custody_identity_json(v jsonb,u text,p text,a text)
returns jsonb language plpgsql immutable set search_path='' as $$
declare result jsonb; k text; item jsonb;
begin
    if jsonb_typeof(v)='array' then
        select coalesce(jsonb_agg(argus_private.business_custody_identity_json(value,u,p,a) order by ordinality),'[]'::jsonb)
            into result from jsonb_array_elements(v) with ordinality;
        return result;
    elsif jsonb_typeof(v)<>'object' or v is null then return v;
    end if;
    result:='{}'::jsonb;
    for k,item in select * from jsonb_each(v) loop
        if item=to_jsonb(u) and k=any(array['actor_id','issuer_id','consenting_actor_id','revoked_by']) then item:=to_jsonb(a);
        elsif item=to_jsonb(u) and k=any(array['user_id','owner_id','record_owner_id','reversal_of_owner_id','activity_owner_id','account_owner_id','goal_owner_id','destination_owner_id']) then item:=to_jsonb(p);
        else item:=argus_private.business_custody_identity_json(item,u,p,a);
        end if;
        result:=result||jsonb_build_object(k,item);
    end loop;
    if v->>'actor_id'=u and v?'display_name' then result:=result||'{"display_name":"Exmiembro"}'::jsonb; end if;
    if v->>'issuer_id'=u and v?'issuer_display_name' then result:=result||'{"issuer_display_name":"Exmiembro"}'::jsonb; end if;
    return result;
end;
$$;

create function argus_private.business_custody_identity_change(p_table text,p_old jsonb,p_new jsonb)
returns boolean language plpgsql set search_path='' as $$
declare v_space uuid; m record; expected jsonb; prefix text; destination text;
begin
    if current_user<>'postgres' or coalesce(current_setting('argus.business_custody_space',true),'')='' then
        return false;
    end if;
    v_space:=current_setting('argus.business_custody_space')::uuid;
    select moves.departing_user_id::text as u,r.custodian_id::text as p,r.deleted_actor_id::text as a,moves.started_at
        into m from argus_private.business_custody_moves moves
        join argus_private.business_custody_reservations r on r.space_id=moves.space_id
        where moves.space_id=v_space;
    if not found then return false; end if;
    expected:=argus_private.business_custody_identity_json(p_old,m.u,m.p,m.a);
    if p_table='financial_document_extractions' then
        foreach prefix in array array['source','rebuilt'] loop
            if p_old->>(prefix||'_path') is not null then
                select destination_path into destination from argus_private.business_custody_objects
                    where space_id=v_space and source_path=p_old->>(prefix||'_path')
                        and sha256=p_old->>(prefix||'_sha256')
                        and size_bytes=(p_old->>(prefix||'_size_bytes'))::bigint
                        and media_type=p_old->>(prefix||'_media_type') and verified_at is not null
                        and destination_path=(case when prefix='source' then 'sealed/' else 'rebuilt/' end)||m.p||'/'||(p_old->'draft'->>'sha256');
                if not found then return false; end if;
                expected:=expected||jsonb_build_object(prefix||'_path',destination);
            end if;
        end loop;
        expected:=expected||'{"preparation_job":null}'::jsonb;
    elsif p_table='financial_source_connections' then
        expected:=expected||jsonb_build_object('external_ref','retained:'||(p_old->>'id'),
            'secret_ciphertext',null,'secret_key_fingerprint',null,'sync_cursor',null,'lease_holder',null,'lease_until',null);
    elsif p_table=any(array['business_receipt_reading_consents','business_receipt_consent_commands','business_ai_consents','business_lifecycle_commands','business_ownership_transfers']) then
        if p_old->>'owner_id'=m.u then expected:=expected||jsonb_build_object('owner_id',m.a); end if;
        if p_old->>'target_id'=m.u then expected:=expected||jsonb_build_object('target_id',m.a); end if;
        if p_table=any(array['business_receipt_reading_consents','business_ai_consents'])
            and p_old->>'owner_id'=m.u and p_old->>'revoked_at' is null then
            expected:=expected||jsonb_build_object('revoked_at',m.started_at);
            if p_table='business_ai_consents' then expected:=expected||jsonb_build_object('revoked_by',m.a); end if;
        end if;
    elsif p_table='business_whatsapp_ai_consents' then
        expected:=expected||jsonb_build_object('sender_hash','\x'||encode(extensions.digest(m.a,'sha256'),'hex'));
        if p_old->>'revoked_at' is null then
            expected:=expected||jsonb_build_object('revoked_at',m.started_at,'revoked_by',m.a);
        end if;
    elsif p_table='business_sources' and starts_with(p_old->>'source_key','web:'||m.u||':') then
        expected:=expected||jsonb_build_object('source_key','web:'||m.a||':'||substr(p_old->>'source_key',42));
    elsif p_table='financial_record_revisions' and p_old->>'recorded_by'=m.u then
        expected:=expected||'{"recorded_by":null}'::jsonb;
    elsif p_table='financial_asset_changes' and p_old->>'recorded_by'=m.u then
        expected:=expected||jsonb_build_object('recorded_by',m.a);
    elsif p_table='business_turns' and p_old->>'actor_id'=m.u then
        expected:=expected||jsonb_build_object('sender_hash',encode(extensions.digest(m.a,'sha256'),'hex'));
    end if;
    -- Hash uses the typed Python contract's canonical serialization. Only the
    -- identity-rewritten command may change; no amount, outcome or source edit.
    if p_table='business_action_receipts' and p_old->'command' is distinct from expected->'command' then
        expected:=expected||jsonb_build_object('input_hash',p_new->'input_hash');
    end if;
    if expected is distinct from p_new then return false; end if;
    return exists(
        select 1 from argus_private.business_custody_changes c
        join argus_private.business_custody_moves moves on moves.space_id=c.space_id
        join argus_private.account_deletion_runs d on d.id=moves.deletion_run_id
        join argus_private.business_custody_reservations r on r.space_id=moves.space_id
        join argus_private.account_placeholders p on p.id=r.custodian_id
        join auth.users u on u.id=p.id
        where c.space_id=v_space and c.table_name=p_table and c.old_row=p_old and c.new_row=p_new
            and d.user_id=moves.departing_user_id and d.claim_id=moves.claim_id
            and d.claimed_until>clock_timestamp() and d.status<>'done'
            and u.banned_until>clock_timestamp() and u.raw_app_meta_data->>'placeholder'='true'
    );
end;
$$;

-- Keep each original guard body and add one narrow identity branch. pg_get_functiondef
-- retains its search_path, security mode and all ordinary insert/update/delete rules.
do $$
declare f regprocedure; body text;
begin
    foreach f in array array[
        'argus_private.business_plan_immutable()'::regprocedure,
        'argus_private.business_receipt_plan_required()'::regprocedure,
        'argus_private.business_immutable_evidence()'::regprocedure,
        'argus_private.business_document_binding_guard()'::regprocedure,
        'argus_private.business_ai_consent_immutable()'::regprocedure,
        'argus_private.business_whatsapp_consent_immutable()'::regprocedure,
        'argus_private.business_transfer_immutable()'::regprocedure,
        'public.check_business_receipt_reading_consent()'::regprocedure,
        'public.set_updated_at()'::regprocedure
    ] loop
        body:=pg_get_functiondef(f);
        body:=regexp_replace(body,'\mbegin\M',
            'begin
    if current_user=''postgres'' and tg_op=''UPDATE'' then
        if argus_private.business_custody_identity_change(tg_table_name,to_jsonb(old),to_jsonb(new)) then return new; end if;
    end if;', 'i');
        execute body;
    end loop;
end;
$$;

create function argus_private.business_custody_client_allowed() returns boolean
language sql stable security definer set search_path='' as $$
    select not exists(select 1 from argus_private.account_placeholders where id=(select auth.uid()));
$$;
revoke all on function argus_private.business_custody_client_allowed() from public,anon;
grant execute on function argus_private.business_custody_client_allowed() to authenticated,service_role;
do $$
declare t text;
begin
    foreach t in array array['financial_accounts','financial_source_connections','financial_import_events',
        'financial_records','financial_record_revisions','financial_activity_groups','financial_activity_revisions',
        'financial_activity_memberships','financial_activity_receipts','financial_operation_receipts',
        'financial_observation_coverage','financial_asset_details','financial_asset_changes',
        'financial_account_idempotency','financial_import_account_links','financial_document_extractions',
        'financial_import_observations','conversations','messages','chat_turn_lifecycles',
        'conversation_read_states','spaces','profiles'] loop
        execute format('create policy business_custody_no_client on public.%I as restrictive to authenticated using (argus_private.business_custody_client_allowed()) with check (argus_private.business_custody_client_allowed())',t);
    end loop;
end;
$$;

revoke all on function argus_private.business_historical_actor(),argus_private.business_custody_identity_change(text,jsonb,jsonb) from public,anon,authenticated,service_role;
revoke all on function argus_private.business_historical_owner() from public,anon,authenticated,service_role;
revoke all on function argus_private.business_custody_identity_json(jsonb,text,text,text) from public,anon,authenticated,service_role;
comment on table argus_private.business_custody_moves is 'In-flight identity map. Clear departed ID and claim after verified Auth deletion. No client/service writer.';
comment on table argus_private.business_custody_changes is 'Transaction-local exact row rewrite proof for validated postgres deletion writer. Cleared before commit.';
comment on column argus_private.business_custody_reservations.moved_at is 'Committed full graph movement. Copy preparation alone never settles this marker.';
comment on column argus_private.business_custody_objects.id is 'Random durable copy key. Source path is nullable after identity cleanup; destination and orphan tracking remain until purge.';
commit;
