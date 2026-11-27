-- Each invitation email a Business sent: what the resend limits count.
create table argus_private.business_invite_sends (
    id uuid primary key default gen_random_uuid(),
    invite_id uuid not null references public.business_access_invites(id) on delete cascade,
    space_id uuid not null references public.spaces(id) on delete cascade,
    resend boolean not null,
    sent_at timestamp with time zone not null default clock_timestamp()
);

create index business_invite_sends_invite on argus_private.business_invite_sends (invite_id, sent_at);
create index business_invite_sends_space on argus_private.business_invite_sends (space_id, sent_at) where resend;

alter table argus_private.business_invite_sends enable row level security;

revoke all on table argus_private.business_invite_sends from public, anon, authenticated;
grant select, insert on table argus_private.business_invite_sends to service_role;
