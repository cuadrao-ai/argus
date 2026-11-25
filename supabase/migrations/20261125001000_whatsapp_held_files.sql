begin;

create table public.whatsapp_held_files (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    sender_link_id uuid not null,
    provider_message_key bytea not null unique check (octet_length(provider_message_key)=32),
    connection_id uuid not null,
    reason text not null check (reason in ('no_buyer_rnc','no_match','two_matches','no_eligible_business','held_read_cap','read_failed')),
    state text not null default 'held' check (state in ('held','assigned','expired')),
    assigned_space_id uuid,
    assigned_connection_id uuid,
    held_at timestamptz not null,
    settled_at timestamptz,
    check ((state='held') = (settled_at is null)),
    check ((state='assigned') = (assigned_space_id is not null and assigned_connection_id is not null))
);
create index whatsapp_held_files_due_idx on public.whatsapp_held_files(held_at,id) where state='held';
create index whatsapp_held_files_connection_idx on public.whatsapp_held_files(user_id,connection_id);

create table public.whatsapp_held_read_usage (
    user_id uuid not null references auth.users(id) on delete cascade,
    day date not null,
    reads integer not null default 0 check (reads>=0),
    primary key(user_id,day)
);

alter table public.whatsapp_held_files enable row level security;
alter table public.whatsapp_held_read_usage enable row level security;
revoke all on public.whatsapp_held_files, public.whatsapp_held_read_usage from public, anon, authenticated;
grant select on public.whatsapp_held_files, public.whatsapp_held_read_usage to authenticated;
grant all on public.whatsapp_held_files, public.whatsapp_held_read_usage to service_role;
create policy whatsapp_held_files_own on public.whatsapp_held_files for select to authenticated using (user_id=auth.uid());
create policy whatsapp_held_read_usage_own on public.whatsapp_held_read_usage for select to authenticated using (user_id=auth.uid());

-- Capture identifiers survive expiry; account deletion removes the tombstones.
comment on table public.whatsapp_held_files is 'Private held Personal uploads, one row per sender message digest. State and reason live here. Connection identifiers survive erasure; they are not foreign keys.';
comment on table public.whatsapp_held_read_usage is 'Unassigned provider reads by sender and Santo Domingo day.';

drop index public.financial_document_extractions_refused_idx;
create index financial_document_extractions_refused_idx
    on public.financial_document_extractions(created_at,connection_id)
    where (draft->>'status')='saved' and (draft->>'error_code') in
    ('business_read_budget_day','business_read_budget_month','whatsapp_held_read_budget_day');
commit;
