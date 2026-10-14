-- Each immutable receiving route owns one UTC-day allowance. Bytes include
-- outstanding reservations and conservative charges for interrupted fetches.
create table public.business_email_daily_usage (
    route_id uuid not null references public.business_email_routes(id) on delete cascade,
    day date not null,
    messages bigint not null default 0 check (messages >= 0),
    bytes_used bigint not null default 0 check (bytes_used >= 0),
    primary key (route_id, day)
);
alter table public.business_email_daily_usage enable row level security;
revoke all on public.business_email_daily_usage from public, anon, authenticated;
grant select, insert, update, delete on public.business_email_daily_usage to service_role;

-- One sequential provider fetch per lease. Old reservations stay charged when
-- a worker dies; its expired lease cannot settle a newer worker's reservation.
alter table public.business_email_deliveries
    add column budget_message_day date,
    add column budget_message_lease uuid,
    add column budget_fetch_day date,
    add column budget_fetch_token uuid;
