-- Retain departed consent and released extra claims without reserving a live slot.
begin;
lock table public.household_plan_bindings,public.financial_plan_links in share row exclusive mode;
drop index public.household_plan_current_definition;
create unique index household_plan_current_definition
 on public.household_plan_bindings(kind,definition_id)
 where revoked_at is null and departed_at is null;
alter table public.financial_plan_links drop constraint financial_plan_links_activity_owner_id_activity_id_key;
create unique index financial_plan_current_activity_claim
 on public.financial_plan_links(activity_owner_id,activity_id)
 where released_at is null or occurrence_id is not null;
commit;
