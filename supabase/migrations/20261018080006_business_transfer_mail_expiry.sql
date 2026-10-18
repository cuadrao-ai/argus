begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

alter table public.business_ownership_transfers add column expires_at timestamptz;
alter table public.business_ownership_transfers disable trigger business_transfer_immutable;
update public.business_ownership_transfers set expires_at=created_at+interval '168 hours';
alter table public.business_ownership_transfers enable trigger business_transfer_immutable;
alter table public.business_ownership_transfers alter column expires_at set not null;
alter table public.business_ownership_transfers add constraint business_transfer_seven_days
    check(expires_at=created_at+interval '168 hours');
alter table public.business_ownership_transfers drop constraint business_ownership_transfers_status_check;
alter table public.business_ownership_transfers add constraint business_ownership_transfers_status_check
    check(status in ('pending','accepted','cancelled','declined','expired'));

create function argus_private.business_transfer_deadline() returns trigger
language plpgsql set search_path='' as $$
begin
    new.expires_at:=new.created_at+interval '168 hours';
    return new;
end;
$$;
revoke all on function argus_private.business_transfer_deadline() from public,anon,authenticated;
create trigger business_transfer_deadline before insert on public.business_ownership_transfers
    for each row execute function argus_private.business_transfer_deadline();
create or replace function argus_private.business_transfer_immutable() returns trigger
language plpgsql set search_path='' as $$
begin
    if current_user='postgres' and tg_op='UPDATE' then
        if argus_private.business_custody_identity_change(tg_table_name,to_jsonb(old),to_jsonb(new)) then return new; end if;
    end if;
    if (to_jsonb(new)-'status'-'resolved_at') is distinct from (to_jsonb(old)-'status'-'resolved_at')
        or old.status<>'pending' or new.status not in ('accepted','cancelled','declined','expired')
        or (new.status='expired' and new.resolved_at<old.expires_at)
        or (new.status in ('accepted','declined') and new.resolved_at>=old.expires_at) then
        raise exception 'business_transfer_history_immutable' using errcode='23514';
    end if;
    return new;
end;
$$;

create table public.business_transfer_mail_outbox (
    id uuid primary key default gen_random_uuid(),
    transfer_id uuid not null references public.business_ownership_transfers(id) on delete cascade,
    variant text not null check(variant in ('requested','declined','acceptedOwner','acceptedTarget','withdrawn')),
    recipient_id uuid not null,
    owner_id uuid not null,
    target_id uuid not null,
    recipient_email text not null,
    context jsonb not null check(jsonb_typeof(context)='object'),
    created_at timestamptz not null default clock_timestamp(),
    first_attempt_at timestamptz,
    payload jsonb,
    sent_at timestamptz,
    suppressed_at timestamptz,
    uncertain_at timestamptz,
    provider_receipt text,
    unique(transfer_id,variant,recipient_id),
    check((first_attempt_at is null)=(payload is null)),
    check(sent_at is null or first_attempt_at is not null)
);
create index business_transfer_mail_pending_idx on public.business_transfer_mail_outbox(created_at)
    where sent_at is null and suppressed_at is null and uncertain_at is null;
alter table public.business_transfer_mail_outbox enable row level security;
revoke all on public.business_transfer_mail_outbox from public,anon,authenticated,service_role;
grant select,insert,update,delete on public.business_transfer_mail_outbox to service_role;
comment on table public.business_transfer_mail_outbox is 'Server-only personal notification transport. Delete for outgoing actors before custody anonymization; never canonical Business history. One event per recipient. First attempt and frozen payload survive provider ambiguity.';
comment on column public.business_ownership_transfers.expires_at is 'Immutable deadline exactly 168 hours after created_at. GET computes expiry without writing. No expiry mail.';

create or replace function argus_private.business_auth_retention_guard() returns trigger
language plpgsql security definer set search_path='' as $$
begin
    if exists(select 1 from public.business_turns where actor_id=old.id)
        or exists(select 1 from public.business_action_receipts where actor_id=old.id)
        or exists(select 1 from public.business_receipt_reading_consents where owner_id=old.id)
        or exists(select 1 from public.business_receipt_consent_commands where owner_id=old.id)
        or exists(select 1 from public.business_ai_consents where owner_id=old.id
            or consenting_actor_id=old.id or issuer_id=old.id or revoked_by=old.id)
        or exists(select 1 from public.business_transfer_mail_outbox where recipient_id=old.id or owner_id=old.id or target_id=old.id) then
        raise exception 'business_custody_identity_detachment_required' using errcode='23514';
    end if;
    return old;
end;
$$;
commit;
