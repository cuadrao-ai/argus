begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.spaces add column current_owner_id uuid references auth.users(id) on delete set null;
update public.spaces set current_owner_id=created_by;
alter table public.spaces add constraint business_open_owner_required check (closed_at is not null or current_owner_id is not null);
drop index public.spaces_one_open_business_idx;
create unique index spaces_one_open_business_idx on public.spaces(current_owner_id)
    where kind='business' and closed_at is null;
create index spaces_current_owner_idx on public.spaces(current_owner_id);
create or replace function public.business_space_of(p_owner uuid) returns uuid
language sql stable set search_path='' as $$
    select id from public.spaces where current_owner_id=p_owner and kind='business' and closed_at is null;
$$;
create function argus_private.business_initial_owner() returns trigger
language plpgsql set search_path='' as $$
begin
    if new.current_owner_id is null and new.closed_at is null then
        new.current_owner_id := new.created_by;
    end if;
    return new;
end;
$$;
revoke all on function argus_private.business_initial_owner() from public,anon,authenticated;
create trigger business_initial_owner before insert on public.spaces for each row
    execute function argus_private.business_initial_owner();

alter table public.business_lifecycle_commands drop constraint business_lifecycle_owner_fkey;
alter table public.business_lifecycle_commands add constraint business_lifecycle_space_fkey
    foreign key(space_id) references public.spaces(id) on delete cascade;

create table public.business_ownership_transfers (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    owner_id uuid not null,
    target_id uuid not null,
    target_grant_id uuid not null,
    idempotency_key text not null check(char_length(idempotency_key) between 1 and 200 and char_length(btrim(idempotency_key))>0),
    confirmation text not null check(char_length(confirmation) between 1 and 80),
    status text not null default 'pending' check(status in ('pending','accepted','cancelled')),
    created_at timestamptz not null default clock_timestamp(),
    resolved_at timestamptz,
    unique(space_id,owner_id,idempotency_key),
    check(owner_id<>target_id),
    check((status='pending')=(resolved_at is null))
);
create unique index business_one_pending_transfer_idx on public.business_ownership_transfers(space_id) where status='pending';
create index business_transfer_target_idx on public.business_ownership_transfers(target_id) where status='pending';
alter table public.business_ownership_transfers enable row level security;
revoke all on public.business_ownership_transfers from public,anon,authenticated,service_role;
grant select,insert,update on public.business_ownership_transfers to service_role;

create or replace function argus_private.business_grant_approve_owner_only() returns trigger
language plpgsql set search_path='' as $$
begin
    if 'approve'=any(new.capabilities) and not exists (
        select 1 from public.spaces where id=new.space_id and current_owner_id=new.grantee_id
    ) then
        raise exception 'business_grant_approve_owner_only' using errcode='23514';
    end if;
    return new;
end;
$$;

create or replace function public.check_business_receipt_reading_consent() returns trigger
language plpgsql set search_path='' as $$
begin
    if tg_op='INSERT' and not exists (
        select 1 from public.spaces where id=new.space_id and kind='business'
            and current_owner_id=new.owner_id and closed_at is null
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

alter table public.business_ai_consents drop constraint business_ai_consents_space_fkey;
alter table public.business_ai_consents add constraint business_ai_consents_space_fkey
    foreign key(space_id) references public.spaces(id) on delete cascade;

create or replace function argus_private.business_ai_consent_immutable()
returns trigger language plpgsql set search_path = '' as $$
begin
    if tg_op = 'DELETE' then
        if exists (select 1 from public.spaces where id = old.space_id) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
        return old;
    elsif tg_op = 'UPDATE' then
        if (to_jsonb(new) - 'revoked_at' - 'revoked_by')
            is distinct from (to_jsonb(old) - 'revoked_at' - 'revoked_by')
            or (old.revoked_at is not null and
                (new.revoked_at, new.revoked_by) is distinct from (old.revoked_at, old.revoked_by)) then
            raise exception 'business_ai_consent_original_immutable' using errcode = '23514';
        end if;
    else
        perform 1 from public.spaces s
        join auth.users u on u.id = s.current_owner_id
        join public.business_client_grants g on g.id = new.grant_id
            and g.space_id = s.id and g.grantee_id = u.id and g.issuer_id = new.issuer_id
        where s.id = new.space_id and s.current_owner_id = new.owner_id
            and s.kind = 'business' and s.closed_at is null
            and coalesce(u.is_anonymous, false) = false
            and g.revoked_at is null and (g.expires_at is null or g.expires_at > clock_timestamp())
            and 'read' = any(g.capabilities) and 'prepare' = any(g.capabilities)
        for share of s, g;
        if not found or new.revoked_at is not null then
            raise exception 'business_ai_consent_owner_required' using errcode = '23514';
        end if;
        new.consented_at := clock_timestamp();
    end if;
    return new;
end;
$$;

create function argus_private.business_transfer_immutable() returns trigger
language plpgsql set search_path='' as $$
begin
    if (to_jsonb(new)-'status'-'resolved_at') is distinct from (to_jsonb(old)-'status'-'resolved_at')
        or old.status<>'pending' or new.status not in ('accepted','cancelled') then
        raise exception 'business_transfer_history_immutable' using errcode='23514';
    end if;
    return new;
end;
$$;
revoke all on function argus_private.business_transfer_immutable() from public,anon,authenticated;
create trigger business_transfer_immutable before update on public.business_ownership_transfers
    for each row execute function argus_private.business_transfer_immutable();

comment on column public.spaces.current_owner_id is 'Current Business authority. Null only for closed ownerless retention. Distinct from created_by custody.';
comment on column public.spaces.created_by is 'Stable Business record custodian. Ownership transfer does not rekey financial records or originals.';
comment on table public.business_ownership_transfers is 'Server-only pending and terminal ownership commands. Historical actor IDs require deletion anonymization before account deletion can be enabled.';
commit;
