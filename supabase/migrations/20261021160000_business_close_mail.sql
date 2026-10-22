begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

create table public.business_close_mail_outbox (
    id uuid primary key default gen_random_uuid(),
    kind text not null check(kind in ('member_closed','owner_closed','purge_reminder','member_reopened')),
    space_id uuid not null references public.spaces(id) on delete cascade,
    closed_at timestamptz not null,
    owner_id uuid not null,
    recipient_id uuid not null references auth.users(id) on delete cascade,
    recipient_email text not null,
    context jsonb not null check(jsonb_typeof(context)='object'),
    created_at timestamptz not null default clock_timestamp(),
    first_attempt_at timestamptz,
    payload jsonb,
    sent_at timestamptz,
    suppressed_at timestamptz,
    uncertain_at timestamptz,
    provider_receipt text,
    unique(space_id,closed_at,recipient_id,kind),
    check((first_attempt_at is null)=(payload is null)),
    check(sent_at is null or first_attempt_at is not null)
);
alter table public.business_close_mail_outbox enable row level security;
revoke all on public.business_close_mail_outbox from public,anon,authenticated,service_role;
grant select,insert,update,delete on public.business_close_mail_outbox to service_role;
create index business_close_mail_pending_idx on public.business_close_mail_outbox(created_at)
    where sent_at is null and suppressed_at is null and uncertain_at is null;
comment on table public.business_close_mail_outbox is 'Personal close-notification transport, atomically queued with closure, reopening or the day-23 sweep. One event per close instant, recipient and kind. Delete on person departure or custody detachment; Business purge cascades. Never retained Business history.';
comment on column public.business_close_mail_outbox.kind is 'member_closed: approved member notice. owner_closed, purge_reminder (day 23, with the reopen path) and member_reopened wait unsent, with no payload, until their copy is approved.';
commit;
