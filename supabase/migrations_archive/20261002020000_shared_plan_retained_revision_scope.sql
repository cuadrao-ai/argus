-- Consent bounds history; departure pins authorized canonical activity revisions.
begin;
alter table public.household_plan_bindings add column first_shared_revision integer;
update public.household_plan_bindings b set first_shared_revision=(r.body->>'version')::integer
 from public.financial_plan_definition_revisions r where r.kind=b.kind and r.definition_id=b.definition_id
 and r.owner_id=b.owner_user_id and r.revision=(select max(v.revision) from public.financial_plan_definition_revisions v
 where v.kind=b.kind and v.definition_id=b.definition_id and v.owner_id=b.owner_user_id);
alter table public.household_plan_bindings alter column first_shared_revision set not null;
alter table public.household_plan_bindings add foreign key(kind,definition_id,owner_user_id,first_shared_revision)
 references public.financial_plan_definition_revisions(kind,definition_id,owner_id,revision) on delete restrict;
alter table public.household_plan_participants add column granted_revision integer;
update public.household_plan_participants p set granted_revision=b.first_shared_revision
 from public.household_plan_bindings b where b.id=p.binding_id;
alter table public.household_plan_participants alter column granted_revision set not null;
alter table public.household_plan_participants add check(granted_revision>0);
create table public.household_plan_archived_activities (
 binding_id uuid not null references public.household_plan_bindings(id) on delete restrict,
 activity_id uuid not null, activity_owner_id uuid not null, activity_revision integer not null,
 primary key(binding_id,activity_id),
 foreign key(activity_id,activity_revision,activity_owner_id)
 references public.financial_activity_revisions(activity_id,revision,user_id) on delete restrict
);
alter table public.household_plan_archived_activities enable row level security;
revoke all on public.household_plan_archived_activities from public,anon,authenticated;
grant all on public.household_plan_archived_activities to service_role;
commit;
