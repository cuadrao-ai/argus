-- Exact accepted group revisions and purchase provenance derive from existing facts.
create table public.financial_activity_revisions (
 activity_id uuid not null, revision integer not null check(revision > 0), user_id uuid not null,
 primary key(activity_id,revision,user_id),
 foreign key(activity_id,user_id) references public.financial_activity_groups(id,user_id) on delete cascade
);
insert into public.financial_activity_revisions(activity_id,revision,user_id)
 select distinct activity_id,activity_revision,user_id from public.financial_activity_memberships;
alter table public.financial_activity_groups add constraint financial_activity_current_revision_fk
 foreign key(id,current_revision,user_id) references public.financial_activity_revisions(activity_id,revision,user_id)
 deferrable initially deferred;
alter table public.financial_activity_memberships add constraint financial_activity_membership_revision_fk
 foreign key(activity_id,activity_revision,user_id) references public.financial_activity_revisions(activity_id,revision,user_id) on delete cascade;
alter table public.financial_activity_receipts add constraint financial_activity_receipt_revision_fk
 foreign key(activity_id,revision,user_id) references public.financial_activity_revisions(activity_id,revision,user_id) on delete cascade;
alter table public.financial_record_revisions
 add column purchase_activity_id uuid generated always as ((details->>'purchase_activity_id')::uuid) stored,
 add column purchase_revision integer generated always as ((details->>'purchase_revision')::integer) stored,
 add constraint financial_purchase_revision_pair check((purchase_activity_id is null) = (purchase_revision is null)),
 add constraint financial_purchase_revision_owner_fk foreign key(purchase_activity_id,purchase_revision,user_id)
 references public.financial_activity_revisions(activity_id,revision,user_id) on delete cascade;
alter table public.financial_activity_revisions enable row level security;
create policy financial_activity_revisions_owner_select on public.financial_activity_revisions for select to authenticated
 using ((select auth.uid())=user_id and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');
revoke all on public.financial_activity_revisions from public,anon,authenticated;
grant select on public.financial_activity_revisions to authenticated;
grant all on public.financial_activity_revisions to service_role;
