-- Add linkage without replacing the existing records, revisions, or coverage keys.
alter table public.financial_records drop constraint financial_records_record_kind_check;
alter table public.financial_records add constraint financial_records_record_kind_check
check(record_kind in ('opening_balance','balance_check','expense','income','transfer','card_payment','refund'));
create table public.financial_activity_groups (
 id uuid primary key, user_id uuid not null references auth.users(id) on delete cascade,
 kind text not null check(kind in ('expense','income','transfer','card_payment','refund')),
 current_revision integer not null check(current_revision > 0), unique(id,user_id)
);
create table public.financial_activity_memberships (
 activity_id uuid not null, user_id uuid not null, activity_revision integer not null check(activity_revision>0),
 record_id uuid not null, record_revision integer not null,
 role text not null check(role in ('single','source','destination')),
 primary key(activity_id,activity_revision,role),
 foreign key(activity_id,user_id) references public.financial_activity_groups(id,user_id) on delete cascade,
 foreign key(record_id,record_revision,user_id) references public.financial_record_revisions(record_id,revision,user_id) on delete cascade
);
create index financial_activity_memberships_owner_idx on public.financial_activity_memberships(user_id,activity_id);
create table public.financial_activity_receipts (
 user_id uuid not null, scope text not null, idempotency_key text not null,
 identity_hash text not null, activity_id uuid not null, revision integer not null,
 affected_accounts uuid[] not null, created_at timestamptz not null default now(),
 primary key(user_id,scope,idempotency_key),
 foreign key(activity_id,user_id) references public.financial_activity_groups(id,user_id) on delete cascade
);
insert into public.financial_activity_groups(id,user_id,kind,current_revision)
 select id,user_id,record_kind,current_revision from public.financial_records where record_kind='expense';
insert into public.financial_activity_memberships(activity_id,user_id,activity_revision,record_id,record_revision,role)
 select r.id,r.user_id,v.revision,r.id,v.revision,'single' from public.financial_records r
 join public.financial_record_revisions v on v.record_id=r.id where r.record_kind='expense';
alter table public.financial_activity_groups enable row level security;
alter table public.financial_activity_memberships enable row level security;
alter table public.financial_activity_receipts enable row level security;
create policy financial_activity_groups_owner_select on public.financial_activity_groups for select to authenticated
 using ((select auth.uid())=user_id and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');
create policy financial_activity_memberships_owner_select on public.financial_activity_memberships for select to authenticated
 using ((select auth.uid())=user_id and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');
revoke all on public.financial_activity_groups, public.financial_activity_memberships, public.financial_activity_receipts from public,anon,authenticated;
grant select on public.financial_activity_groups, public.financial_activity_memberships to authenticated;
grant all on public.financial_activity_groups, public.financial_activity_memberships, public.financial_activity_receipts to service_role;
