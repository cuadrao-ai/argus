set local lock_timeout = '5s';
set local statement_timeout = '60s';

-- Existing rows remain unchanged until a person submits the new consent form.
-- created_at is the canonical signup time; no second signup timestamp is stored.
alter table public.cuadrao_early_access_signups
    add column if not exists expense_method text,
    add column if not exists wish text,
    add column if not exists confirmed_at timestamptz,
    add column if not exists privacy_policy_version text,
    add column if not exists last_confirmation_sent_at timestamptz,
    add column if not exists reminder_sent_at timestamptz,
    add column if not exists verification_id text;

alter table public.cuadrao_early_access_signups
    add constraint cuadrao_waitlist_expense_method check (expense_method in (
        'No los llevo', 'En una libreta o notas', 'En Excel o Google Sheets',
        'En otra app', 'Otra forma')),
    add constraint cuadrao_waitlist_wish_length check (char_length(wish) <= 280),
    add constraint cuadrao_waitlist_verification_id check (verification_id ~ '^[0-9a-f]{64}$'),
    add constraint cuadrao_waitlist_privacy_version check (char_length(privacy_policy_version) between 1 and 64),
    add constraint cuadrao_waitlist_confirmation_order check (confirmed_at >= created_at),
    add constraint cuadrao_waitlist_verification_unique unique (verification_id);

comment on column public.cuadrao_early_access_signups.created_at is
    'Canonical signup time. Unconfirmed personal waitlist rows expire after 7 days; confirmed rows after 12 months. Leave removes the whole row immediately.';
comment on column public.cuadrao_early_access_signups.last_confirmation_sent_at is
    'Atomic delivery reservation used for the rolling 10-minute email limit and 48-hour confirmation expiry. A definite provider refusal releases it; unknown delivery keeps the reservation.';
comment on column public.cuadrao_early_access_signups.verification_id is
    'Opaque 256-bit email capability. Never logged. Leave remains usable until the row is deleted; repeated leave is successful without retaining a suppression digest.';

-- These invoker functions remain service-role only. Public clients never see rows.
create or replace function public.cuadrao_waitlist_register(
    p_email text, p_expense_method text, p_wish text, p_verification_id text,
    p_privacy_policy_version text
) returns setof public.cuadrao_early_access_signups
language plpgsql security invoker set search_path = '' as $$
declare
    v_row public.cuadrao_early_access_signups%rowtype;
    v_digest text := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_email, 'UTF8')), 'hex');
begin
    insert into public.cuadrao_early_access_signups (
        email_digest, email, language, consent_version, source, expense_method, wish,
        privacy_policy_version, verification_id
    ) values (v_digest, p_email, 'es', p_privacy_policy_version, 'personal-page',
        p_expense_method, p_wish, p_privacy_policy_version, p_verification_id)
    on conflict (email_digest) do nothing;
    select * into v_row from public.cuadrao_early_access_signups
        where email_digest = v_digest for update;
    if v_row.source not in ('personal-page', 'operator-removal') then return; end if;
    if v_row.privacy_policy_version is null then
        update public.cuadrao_early_access_signups set
            email = p_email, removed_at = null, created_at = now(), language = 'es',
            consent_version = p_privacy_policy_version, source = 'personal-page',
            expense_method = p_expense_method, wish = p_wish,
            privacy_policy_version = p_privacy_policy_version, verification_id = p_verification_id
        where email_digest = v_digest returning * into v_row;
    end if;
    if v_row.confirmed_at is not null or v_row.created_at + interval '7 days' <= now()
        or v_row.last_confirmation_sent_at > now() - interval '10 minutes' then return; end if;
    return query update public.cuadrao_early_access_signups
        set last_confirmation_sent_at = now()
        where email_digest = v_digest returning *;
end;
$$;

create or replace function public.cuadrao_waitlist_confirm(p_verification_id text, p_issued_at timestamptz)
returns setof public.cuadrao_early_access_signups
language plpgsql security invoker set search_path = '' as $$
begin
    return query update public.cuadrao_early_access_signups
        set confirmed_at = coalesce(confirmed_at, now())
        where verification_id = p_verification_id and removed_at is null
            and privacy_policy_version is not null
            and p_issued_at > now() - interval '48 hours' and p_issued_at <= now()
            and p_issued_at >= created_at - interval '1 second'
            and created_at > now() - interval '7 days'
        returning *;
end;
$$;

create or replace function public.cuadrao_waitlist_reminders(p_limit integer default 100)
returns setof public.cuadrao_early_access_signups
language sql security invoker set search_path = '' as $$
    update public.cuadrao_early_access_signups as signup
    set reminder_sent_at = now(), last_confirmation_sent_at = now()
    where email_digest in (
        select email_digest from public.cuadrao_early_access_signups
        where privacy_policy_version is not null and removed_at is null
            and confirmed_at is null and reminder_sent_at is null
            and created_at <= now() - interval '24 hours'
            and created_at > now() - interval '7 days'
            and (last_confirmation_sent_at is null or last_confirmation_sent_at <= now() - interval '10 minutes')
        order by created_at limit greatest(1, least(p_limit, 100)) for update skip locked
    ) returning signup.*;
$$;

create or replace function public.cuadrao_waitlist_release(
    p_verification_id text, p_reserved_at timestamptz, p_reminder boolean
) returns void language sql security invoker set search_path = '' as $$
    update public.cuadrao_early_access_signups
    set last_confirmation_sent_at = null,
        reminder_sent_at = case when p_reminder then null else reminder_sent_at end
    where verification_id = p_verification_id and confirmed_at is null
        and last_confirmation_sent_at = p_reserved_at;
$$;

create or replace function public.cuadrao_waitlist_leave(p_verification_id text)
returns void language sql security invoker set search_path = '' as $$
    delete from public.cuadrao_early_access_signups
    where verification_id = p_verification_id and privacy_policy_version is not null;
$$;

create or replace function public.cuadrao_waitlist_purge(p_limit integer default 100)
returns integer language plpgsql security invoker set search_path = '' as $$
declare v_count integer;
begin
    delete from public.cuadrao_early_access_signups where email_digest in (
        select email_digest from public.cuadrao_early_access_signups
        where privacy_policy_version is not null and (
            (confirmed_at is null and created_at <= now() - interval '7 days')
            or created_at + interval '12 months' <= now()
        ) order by created_at limit greatest(1, least(p_limit, 100)) for update skip locked
    );
    get diagnostics v_count = row_count;
    return v_count;
end;
$$;

alter table public.cuadrao_early_access_signups enable row level security;
revoke all on table public.cuadrao_early_access_signups from public, anon, authenticated;
grant select, insert, update, delete on table public.cuadrao_early_access_signups to service_role;
revoke all on function public.cuadrao_waitlist_register(text,text,text,text,text),
    public.cuadrao_waitlist_confirm(text,timestamptz), public.cuadrao_waitlist_reminders(integer),
    public.cuadrao_waitlist_leave(text), public.cuadrao_waitlist_purge(integer),
    public.cuadrao_waitlist_release(text,timestamptz,boolean)
    from public, anon, authenticated;
grant execute on function public.cuadrao_waitlist_register(text,text,text,text,text),
    public.cuadrao_waitlist_confirm(text,timestamptz), public.cuadrao_waitlist_reminders(integer),
    public.cuadrao_waitlist_leave(text), public.cuadrao_waitlist_purge(integer),
    public.cuadrao_waitlist_release(text,timestamptz,boolean) to service_role;
