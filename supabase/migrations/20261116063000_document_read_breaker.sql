begin;

-- The read breaker: one row that every document worker and every new deploy
-- reads, so they agree on whether receipt reads are being sent. `failures`
-- are the recent failed provider calls while it is closed. `opened_at` is set
-- while sends are stopped. `probe_at` is when the one probing read was sent,
-- and `probe_id` names it: only the call that carries that id closes the
-- breaker or starts its cooldown again.
create table public.document_read_breaker (
    singleton boolean primary key default true,
    failures timestamptz[] not null default '{}',
    opened_at timestamptz,
    probe_at timestamptz,
    probe_id text,
    constraint document_read_breaker_singleton_check check (singleton),
    constraint document_read_breaker_probe_needs_open check (
        probe_at is null or opened_at is not null
    ),
    constraint document_read_breaker_probe_is_named check (
        (probe_at is null) = (probe_id is null)
    )
);

-- Server-only: row security with no policy, and no client grant.
alter table public.document_read_breaker enable row level security;
revoke all on table public.document_read_breaker from public, anon, authenticated;
grant all on table public.document_read_breaker to service_role;

insert into public.document_read_breaker default values;

commit;
