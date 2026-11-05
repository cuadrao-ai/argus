-- Reads a Business started on one Santo Domingo day, whichever channel the
-- receipt came from. The month total is the sum of its days. Server-only.
create table public.business_read_daily_usage (
    business_id uuid not null references public.spaces(id) on delete cascade,
    day date not null,
    reads integer not null default 0 check (reads >= 0),
    primary key (business_id, day)
);

alter table public.business_read_daily_usage enable row level security;
revoke all on public.business_read_daily_usage from public, anon, authenticated;
grant select, insert, update, delete on public.business_read_daily_usage to service_role;
