-- A forward retains references to its committed messages and at most three sealed samples.
alter table public.whatsapp_inbound_messages
    add column capture_duplicate boolean not null default false;

alter table public.whatsapp_reply_groups
    drop constraint whatsapp_reply_groups_pkey,
    add column id uuid not null default gen_random_uuid() primary key,
    add column kind text not null default 'files' check (kind in ('files', 'guidance')),
    add column member_keys bytea[] not null default '{}',
    add column last_arrival timestamptz;

update public.whatsapp_reply_groups set last_arrival = send_after - interval '2 minutes';
alter table public.whatsapp_reply_groups alter column last_arrival set not null;
alter table public.whatsapp_reply_groups rename column failed_count to member_count;
create index whatsapp_reply_groups_forward_idx
    on public.whatsapp_reply_groups (sender_hash, link_id, kind, last_arrival desc);

-- Successful file summaries require no reservation. The guidance reservation is independent.
alter table public.whatsapp_reply_attempts alter column day drop not null;
alter table public.whatsapp_reply_attempts rename column failed_count to member_count;
alter table public.whatsapp_reply_days
    add column guidance_reserved boolean not null default false;
