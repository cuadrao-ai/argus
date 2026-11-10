create table public.business_guide_dismissals (
    user_id uuid not null references auth.users (id) on delete cascade,
    card_id text not null check (card_id ~ '^[a-z0-9-]{1,64}$'),
    dismissed_at timestamptz not null default now(),
    primary key (user_id, card_id)
);

alter table public.business_guide_dismissals enable row level security;

revoke all on public.business_guide_dismissals
    from public, anon, authenticated, service_role;
grant select on public.business_guide_dismissals to authenticated, service_role;
grant insert (user_id, card_id) on public.business_guide_dismissals
    to authenticated, service_role;

create policy business_guide_dismissals_select
    on public.business_guide_dismissals
    for select to authenticated
    using (
        user_id = (select auth.uid())
        and (select auth.jwt() ->> 'is_anonymous') = 'false'
    );

create policy business_guide_dismissals_insert
    on public.business_guide_dismissals
    for insert to authenticated
    with check (
        user_id = (select auth.uid())
        and (select auth.jwt() ->> 'is_anonymous') = 'false'
    );

