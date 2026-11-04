create table public.business_notifications (
    id uuid primary key default gen_random_uuid(),
    business_id uuid not null references public.spaces(id) on delete cascade,
    recipient_user_id uuid not null references auth.users(id) on delete cascade,
    kind text not null check (kind in ('invitation_received', 'new_sender_waiting')),
    subject_id uuid not null,
    created_at timestamptz not null default clock_timestamp(),
    read_at timestamptz,
    resolved_at timestamptz
);

create unique index business_notifications_unresolved_key
    on public.business_notifications (business_id, recipient_user_id, kind, subject_id)
    where resolved_at is null;
create index business_notifications_recipient_created_idx
    on public.business_notifications (recipient_user_id, business_id, created_at desc, id desc);

alter table public.business_notifications enable row level security;
revoke all on public.business_notifications from anon, authenticated;
grant select, update(read_at) on public.business_notifications to authenticated;
grant all on public.business_notifications to service_role;

create policy business_notifications_read_own on public.business_notifications
    for select to authenticated using (recipient_user_id = auth.uid());
create policy business_notifications_update_own on public.business_notifications
    for update to authenticated
    using (recipient_user_id = auth.uid())
    with check (recipient_user_id = auth.uid());
