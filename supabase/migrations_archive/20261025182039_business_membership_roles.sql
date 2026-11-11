begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.business_client_grants add column business_role text;
alter table public.business_client_grants add column membership_version bigint not null default 0;
alter table public.business_access_invites add column requested_role text not null default 'editor'
    check (requested_role in ('owner','admin','editor','viewer'));
alter table public.business_access_invites add column recipient_id uuid;
create index business_invite_recipient on public.business_access_invites(recipient_id) where recipient_id is not null;
update public.business_access_invites i set recipient_id=u.id from auth.users u where lower(u.email)=i.email;
alter table public.business_access_invites add column target_grant_id uuid;
alter table public.business_access_invites add column target_version bigint;
alter table public.business_access_invites add column supersedes_id uuid unique references public.business_access_invites(id) on delete set null;
alter table public.business_access_invites add constraint business_invite_target_version check ((target_grant_id is null)=(target_version is null));
alter table public.spaces add column membership_revision bigint not null default 0;

update public.business_client_grants g set business_role = case
    when g.grantee_id=s.current_owner_id and 'approve'=any(g.capabilities) then 'owner'
    when 'prepare'=any(g.capabilities) then 'editor'
    else 'viewer' end
from public.spaces s where s.id=g.space_id;
do $$
begin
    if exists(select 1 from public.business_client_grants where business_role='owner' and revoked_at is null and expires_at is not null) then
        raise exception 'business_expiring_owner_requires_review' using errcode='23514';
    end if;
end;
$$;
insert into public.business_client_grants(space_id,grantee_id,issuer_id,business_role,capabilities)
select s.id,s.current_owner_id,s.current_owner_id,'owner',array['read','prepare','approve']
from public.spaces s join auth.users u on u.id=s.current_owner_id
where s.kind='business' and s.closed_at is null and not coalesce(u.is_anonymous,false)
    and (u.banned_until is null or u.banned_until<=clock_timestamp())
    and not exists(select 1 from argus_private.account_deletion_runs d where d.user_id=u.id)
    and not exists(select 1 from public.business_client_grants g where g.space_id=s.id);
do $$
begin
    if exists(select 1 from public.spaces s where s.kind='business' and s.closed_at is null
        and not exists(select 1 from public.business_client_grants g where g.space_id=s.id
            and g.business_role='owner' and g.revoked_at is null and g.expires_at is null)) then
        raise exception 'business_owner_history_requires_review' using errcode='23514';
    end if;
end;
$$;
alter table public.business_client_grants add constraint business_membership_role
    check (business_role in ('owner','admin','editor','viewer'));

create or replace function argus_private.business_grant_approve_owner_only() returns trigger
language plpgsql set search_path='' as $$
begin
    if new.business_role is null then
        new.business_role := case
            when 'approve'=any(new.capabilities) and exists (
                select 1 from public.spaces where id=new.space_id and current_owner_id=new.grantee_id
            ) then 'owner'
            when 'approve'=any(new.capabilities) then null
            when 'prepare'=any(new.capabilities) then 'editor'
            else 'viewer' end;
    end if;
    if new.business_role is null then
        raise exception 'business_grant_approve_owner_only' using errcode='23514';
    end if;
    new.capabilities := case new.business_role
        when 'owner' then array['read','prepare','approve']
        when 'viewer' then array['read']
        else array['read','prepare'] end;
    if new.business_role='owner' and new.revoked_at is null and new.expires_at is not null then
        raise exception 'business_owner_cannot_expire' using errcode='23514';
    end if;
    if tg_op='UPDATE' then
        new.membership_version := old.membership_version + case
            when (new.business_role,new.revoked_at,new.expires_at) is distinct from (old.business_role,old.revoked_at,old.expires_at) then 1 else 0 end;
    end if;
    if tg_op='UPDATE' and old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at then
        raise exception 'business_membership_revocation_final' using errcode='23514';
    end if;
    return new;
end;
$$;
alter table public.business_client_grants alter column business_role set not null;

create function argus_private.business_membership_serialize() returns trigger
language plpgsql set search_path='' as $$
declare v_space uuid;
begin
    v_space := case when tg_op='DELETE' then old.space_id else new.space_id end;
    -- A write, not just a lock, aborts stale repeatable-read mutations.
    update public.spaces set membership_revision=membership_revision+1 where id=v_space;
    if tg_op='UPDATE' and old.space_id<>new.space_id then
        raise exception 'business_membership_scope_immutable' using errcode='23514';
    end if;
    return case when tg_op='DELETE' then old else new end;
end;
$$;
revoke all on function argus_private.business_membership_serialize() from public,anon,authenticated;
create trigger business_membership_serialize before insert or update or delete on public.business_client_grants
    for each row execute function argus_private.business_membership_serialize();

create function argus_private.business_membership_owner_required() returns trigger
language plpgsql set search_path='' as $$
declare v_space uuid;
begin
    v_space := coalesce(to_jsonb(new)->>'space_id',to_jsonb(old)->>'space_id',to_jsonb(new)->>'id')::uuid;
    if exists (select 1 from public.spaces where id=v_space and kind='business' and closed_at is null)
        and not exists (select 1 from public.business_client_grants where space_id=v_space
            and business_role='owner' and revoked_at is null and expires_at is null) then
        raise exception 'business_last_owner_required' using errcode='23514';
    end if;
    return null;
end;
$$;
revoke all on function argus_private.business_membership_owner_required() from public,anon,authenticated;
create constraint trigger business_membership_owner_required after insert or update or delete
    on public.business_client_grants deferrable initially deferred
    for each row execute function argus_private.business_membership_owner_required();
create constraint trigger business_reopen_owner_required after update on public.spaces
    deferrable initially deferred for each row when (old.closed_at is not null and new.closed_at is null)
    execute function argus_private.business_membership_owner_required();

alter table public.business_access_invites add column delivery_state text not null default 'pending'
    check (delivery_state in ('pending','accepted','failed','not_configured','sending','uncertain'));
create table argus_private.business_invitation_commands (
    space_id uuid not null references public.spaces(id) on delete cascade,
    actor_id uuid not null references auth.users(id) on delete cascade,
    command_key text not null check(length(command_key) between 1 and 200),
    email text not null,
    requested_role text not null,
    invite_id uuid references public.business_access_invites(id) on delete cascade,
    primary key(space_id,actor_id,command_key)
);
alter table argus_private.business_invitation_commands enable row level security;
revoke all on argus_private.business_invitation_commands from public,anon,authenticated;
grant select,insert,update,delete on argus_private.business_invitation_commands to service_role;

create function argus_private.business_owner_consent_revoked() returns trigger
language plpgsql set search_path='' as $$
begin
    if old.business_role='owner' and old.revoked_at is null
        and (tg_op='DELETE' or new.business_role<>'owner' or new.revoked_at is not null) then
        update public.business_receipt_reading_consents set revoked_at=clock_timestamp()
            where space_id=old.space_id and owner_id=old.grantee_id and revoked_at is null;
        update public.business_ai_consents set revoked_at=clock_timestamp()
            where space_id=old.space_id and owner_id=old.grantee_id and revoked_at is null;
    end if;
    if tg_op='DELETE' then return old; end if;
    return new;
end;
$$;
revoke all on function argus_private.business_owner_consent_revoked() from public,anon,authenticated;
create trigger business_owner_consent_revoked after update or delete on public.business_client_grants
    for each row execute function argus_private.business_owner_consent_revoked();

create function argus_private.business_invite_terminal() returns trigger
language plpgsql set search_path='' as $$
declare m record; expected jsonb;
begin
    if current_user='postgres' and (old.accepted_at is not null or old.revoked_at is not null)
        and current_setting('argus.business_custody_space',true)=old.space_id::text then
        select moves.departing_user_id::text as u,r.custodian_id::text as p,
            r.deleted_actor_id::text as a,s.current_owner_id::text as owner into m
        from argus_private.business_custody_moves moves
        join argus_private.business_custody_reservations r on r.space_id=moves.space_id
        join public.spaces s on s.id=moves.space_id
        join argus_private.account_deletion_runs d on d.id=moves.deletion_run_id
        join argus_private.account_placeholders p on p.id=r.custodian_id
        join auth.users u on u.id=p.id
        where moves.space_id=old.space_id and d.user_id=moves.departing_user_id
            and d.claim_id=moves.claim_id and d.claimed_until>clock_timestamp() and d.status<>'done'
            and u.banned_until>clock_timestamp() and u.raw_app_meta_data->>'placeholder'='true';
        if found and old.issuer_id::text=m.u then
            expected:=argus_private.business_custody_identity_json(to_jsonb(old),m.u,m.p,m.a)
                ||jsonb_build_object('issuer_id',coalesce(nullif(m.owner,m.u),m.p),'historical_issuer_id',m.a);
            if expected=to_jsonb(new) and exists(
                select 1 from argus_private.business_custody_changes where space_id=old.space_id
                    and table_name=tg_table_name and old_row=to_jsonb(old) and new_row=to_jsonb(new)
            ) then return new; end if;
        end if;
    end if;
    if current_user='postgres' and (old.accepted_at is not null or old.revoked_at is not null)
        and argus_private.business_custody_identity_change(tg_table_name,to_jsonb(old),to_jsonb(new)) then
        return new;
    end if;
    if (old.accepted_at is not null or old.revoked_at is not null)
        and (to_jsonb(new)-'accepted_grant_id')
            is distinct from (to_jsonb(old)-'accepted_grant_id') then
        raise exception 'business_invite_terminal' using errcode='23514';
    end if;
    if old.expires_at<=clock_timestamp() and new.expires_at>old.expires_at then
        raise exception 'business_invite_expired' using errcode='23514';
    end if;
    if (new.space_id,new.email,new.requested_role,new.recipient_id,new.target_grant_id,new.target_version,new.issuer_id,new.historical_issuer_id) is distinct from (old.space_id,old.email,old.requested_role,old.recipient_id,old.target_grant_id,old.target_version,old.issuer_id,old.historical_issuer_id) then
        raise exception 'business_invite_recipient_immutable' using errcode='23514';
    end if;
    return new;
end;
$$;
revoke all on function argus_private.business_invite_terminal() from public,anon,authenticated;
create trigger business_invite_terminal before update on public.business_access_invites
    for each row execute function argus_private.business_invite_terminal();

create or replace function public.business_space_of(p_owner uuid) returns uuid
language sql stable set search_path='' as $$
    select s.id from public.spaces s where s.current_owner_id=p_owner and s.kind='business'
        and s.closed_at is null and exists (
            select 1 from public.business_client_grants g where g.space_id=s.id and g.grantee_id=p_owner
                and g.revoked_at is null and (g.expires_at is null or g.expires_at>clock_timestamp())
        );
$$;

comment on column public.spaces.current_owner_id is 'Legacy default Business and transfer anchor; not membership authority. Record custody remains created_by.';
comment on column public.business_client_grants.business_role is 'Canonical accepted membership role. Capabilities are its legacy wire projection.';
comment on column public.spaces.membership_revision is 'Serialization version for membership changes, including repeatable-read transactions.';

create or replace function public.check_business_receipt_reading_consent() returns trigger
language plpgsql set search_path='' as $$
begin
    if current_user='postgres' and tg_op='UPDATE' then
        if argus_private.business_custody_identity_change(tg_table_name,to_jsonb(old),to_jsonb(new)) then return new; end if;
    end if;
    if tg_op='INSERT' and not exists (
        select 1 from public.spaces s join public.business_client_grants g on g.space_id=s.id
        where s.id=new.space_id and s.kind='business' and s.closed_at is null
            and g.grantee_id=new.owner_id and g.business_role='owner'
            and g.revoked_at is null and g.expires_at is null
    ) then
        raise exception 'Business owner consent required';
    end if;
    if tg_op='UPDATE' and (to_jsonb(new)-'revoked_at') is distinct from (to_jsonb(old)-'revoked_at') then
        raise exception 'Consent generation is immutable';
    end if;
    if tg_op='UPDATE' and old.revoked_at is not null and new.revoked_at is distinct from old.revoked_at then
        raise exception 'Revoked consent cannot be restored';
    end if;
    return new;
end;
$$;
create or replace function argus_private.business_ai_consent_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if current_user='postgres' and tg_op='UPDATE' then
        if argus_private.business_custody_identity_change(tg_table_name,to_jsonb(old),to_jsonb(new)) then return new; end if;
    end if;
    if tg_op = 'DELETE' then
        if exists (select 1 from public.spaces where id = old.space_id) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
        return old;
    elsif tg_op = 'UPDATE' then
        if (to_jsonb(new) - 'revoked_at' - 'revoked_by' - 'invalidated_by_transfer_id')
            is distinct from (to_jsonb(old) - 'revoked_at' - 'revoked_by' - 'invalidated_by_transfer_id')
            or (old.revoked_at is not null and
                (new.revoked_at, new.revoked_by, new.invalidated_by_transfer_id) is distinct from (old.revoked_at, old.revoked_by, old.invalidated_by_transfer_id)) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
    else
        perform 1 from public.spaces s
        join auth.users u on u.id = new.owner_id
        join public.business_client_grants g on g.id = new.grant_id
            and g.space_id = s.id and g.grantee_id = u.id and g.issuer_id = new.issuer_id
        where s.id = new.space_id and g.business_role = 'owner'
            and s.kind = 'business' and s.closed_at is null
            and coalesce(u.is_anonymous, false) = false
            and g.revoked_at is null and (g.expires_at is null or g.expires_at > clock_timestamp())
            and 'read' = any(g.capabilities) and 'prepare' = any(g.capabilities)
        for share of s, g;
        if not found or new.revoked_at is not null or new.invalidated_by_transfer_id is not null then
            raise exception 'business_ai_consent_owner_required' using errcode = '23514';
        end if;
        new.consented_at := clock_timestamp();
    end if;
    return new;
end;
$$;
alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment', 'settle_remainder',
            'access_seen', 'email_ai_consent_declined', 'mark_personal', 'decide_606',
            'receipt_upload', 'receipt_review', 'receipt_confirm', 'approve_refund', 'set_business_rnc',
            'resolve_duplicate', 'change_role')) is true
    );

alter table public.business_action_receipts add constraint business_membership_role_human
    check (command->>'action' is distinct from 'change_role' or actor->>'actor_kind'='member');
create or replace function argus_private.business_custody_identity_json(v jsonb,u text,p text,a text)
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
        if item=to_jsonb(u) and k=any(array['actor_id','issuer_id','consenting_actor_id','revoked_by','recipient_id']) then item:=to_jsonb(a);
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


create function argus_private.business_invitation_recipient() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if new.recipient_id is not null and not exists(select 1 from auth.users where id=new.recipient_id)
        and not exists(select 1 from argus_private.business_custody_reservations where space_id=new.space_id and deleted_actor_id=new.recipient_id)
        and not exists(select 1 from argus_private.business_departure_aliases where space_id=new.space_id and actor_id=new.recipient_id) then
        raise exception 'business_invitation_recipient_not_found' using errcode='23503';
    end if;
    if tg_op='INSERT' and new.target_grant_id is not null and not exists(
        select 1 from public.business_client_grants where id=new.target_grant_id and space_id=new.space_id
            and grantee_id=new.recipient_id and membership_version=new.target_version
    ) then
        raise exception 'business_invitation_target_not_found' using errcode='23503';
    end if;
    return new;
end;
$$;
revoke all on function argus_private.business_invitation_recipient() from public,anon,authenticated;
create constraint trigger business_invitation_recipient after insert or update on public.business_access_invites
    deferrable initially immediate for each row execute function argus_private.business_invitation_recipient();

create function argus_private.business_invitation_auth_retention() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if exists(select 1 from public.business_access_invites where recipient_id=old.id) then
        raise exception 'business_custody_identity_detachment_required' using errcode='23514';
    end if;
    return old;
end;
$$;
revoke all on function argus_private.business_invitation_auth_retention() from public,anon,authenticated,service_role;
create trigger business_invitation_auth_retention before delete on auth.users
    for each row execute function argus_private.business_invitation_auth_retention();
commit;
