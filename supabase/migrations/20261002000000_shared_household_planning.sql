-- Coordinated service/schema cutover. Public sharing derives from canonical history.
begin;

create table public.financial_plan_definition_revisions (
 kind text not null check(kind in ('budget','bill','goal','debt')),
 definition_id uuid not null, owner_id uuid not null references auth.users(id) on delete restrict,
 revision integer not null check(revision>0), body jsonb not null,
 actor_id uuid references auth.users(id) on delete restrict,
 recorded_at timestamptz not null default now(),
 primary key(kind,definition_id,owner_id,revision)
);
create function public.record_plan_definition_revision() returns trigger language plpgsql
 set search_path='' as $$
begin
 if TG_OP='UPDATE' and OLD.body=NEW.body then return NEW; end if;
 if TG_OP='UPDATE' and (NEW.body->>'version')::integer <= (OLD.body->>'version')::integer then
  raise exception 'canonical definition revision must advance' using errcode='23514';
 end if;
 insert into public.financial_plan_definition_revisions(kind,definition_id,owner_id,revision,body,actor_id)
 values(TG_ARGV[0],NEW.id,NEW.user_id,(NEW.body->>'version')::integer,NEW.body,
 nullif(current_setting('argus.plan_actor',true),'')::uuid);
 return NEW;
end $$;
insert into public.financial_plan_definition_revisions(kind,definition_id,owner_id,revision,body)
 select 'budget',id,user_id,(body->>'version')::integer,body from public.financial_budgets
 union all select 'bill',id,user_id,(body->>'version')::integer,body from public.financial_expectations
 union all select 'goal',id,user_id,(body->>'version')::integer,body from public.financial_goals
 union all select 'debt',id,user_id,(body->>'version')::integer,body from public.financial_debt_plans;
create trigger budget_revision after insert or update on public.financial_budgets
 for each row execute function public.record_plan_definition_revision('budget');
create trigger bill_revision after insert or update on public.financial_expectations
 for each row execute function public.record_plan_definition_revision('bill');
create trigger goal_revision after insert or update on public.financial_goals
 for each row execute function public.record_plan_definition_revision('goal');
create trigger debt_revision after insert or update on public.financial_debt_plans
 for each row execute function public.record_plan_definition_revision('debt');

create table public.household_plan_bindings (
 id uuid primary key default gen_random_uuid(), household_id uuid not null references public.households(id) on delete restrict,
 owner_membership_id uuid not null, owner_user_id uuid not null,
 kind text not null check(kind in ('budget','bill','goal','debt')),
 budget_id uuid, expectation_id uuid, goal_id uuid, debt_plan_id uuid,
 definition_id uuid generated always as (coalesce(budget_id,expectation_id,goal_id,debt_plan_id)) stored,
 publish_budget_scope boolean not null default false,
 revoked_at timestamptz, departed_at timestamptz, retained_revision integer,
 foreign key(owner_membership_id,household_id,owner_user_id) references public.household_members(id,household_id,user_id) on delete restrict,
 foreign key(budget_id,owner_user_id) references public.financial_budgets(id,user_id) on delete restrict,
 foreign key(expectation_id,owner_user_id) references public.financial_expectations(id,user_id) on delete restrict,
 foreign key(goal_id,owner_user_id) references public.financial_goals(id,user_id) on delete restrict,
 foreign key(debt_plan_id,owner_user_id) references public.financial_debt_plans(id,user_id) on delete restrict,
 foreign key(kind,definition_id,owner_user_id,retained_revision) references public.financial_plan_definition_revisions(kind,definition_id,owner_id,revision) on delete restrict,
 check(num_nonnulls(budget_id,expectation_id,goal_id,debt_plan_id)=1),
 check((kind='budget')=(budget_id is not null) and (kind='bill')=(expectation_id is not null)
   and (kind='goal')=(goal_id is not null) and (kind='debt')=(debt_plan_id is not null)),
 check((departed_at is null)=(retained_revision is null)),
 unique(id,household_id), unique(id,owner_user_id)
);
create unique index household_plan_current_definition on public.household_plan_bindings(kind,definition_id) where revoked_at is null;
create table public.household_plan_participants (
 binding_id uuid not null, household_id uuid not null, membership_id uuid not null,
 permission text not null check(permission in ('view','edit')), revoked_at timestamptz,
 primary key(binding_id,membership_id),
 foreign key(binding_id,household_id) references public.household_plan_bindings(id,household_id) on delete restrict,
 foreign key(membership_id,household_id) references public.household_members(id,household_id) on delete restrict
);
create table public.financial_plan_responsibilities (
 kind text not null, definition_id uuid not null, owner_id uuid not null, revision integer not null,
 membership_id uuid not null references public.household_members(id) on delete restrict,
 amount_minor bigint check(amount_minor>=0), period text, occurrence_id uuid, schedule_id uuid, agreed_date date,
 foreign key(kind,definition_id,owner_id,revision) references public.financial_plan_definition_revisions(kind,definition_id,owner_id,revision) on delete restrict,
 check(num_nonnulls(period,occurrence_id,schedule_id,agreed_date)=1),
 check(period is null or period ~ '^\d{4}-\d{2}$'),
 unique nulls not distinct(kind,definition_id,owner_id,revision,membership_id,period,occurrence_id,schedule_id,agreed_date)
);
create table public.household_plan_receipts (
 actor_id uuid not null references auth.users(id) on delete restrict,
 membership_id uuid not null references public.household_members(id) on delete restrict,
 operation text not null, idempotency_key text not null, identity_hash text not null,
 binding_id uuid not null references public.household_plan_bindings(id) on delete restrict,
 claim_id uuid, primary key(actor_id,membership_id,operation,idempotency_key)
);

alter table public.financial_plan_links add column activity_owner_id uuid;
update public.financial_plan_links set activity_owner_id=user_id;
alter table public.financial_plan_links alter column activity_owner_id set not null;
alter table public.financial_plan_links add column binding_id uuid;
alter table public.financial_plan_links add column contributor_membership_id uuid references public.household_members(id) on delete restrict;
alter table public.financial_plan_links add column purpose text check(purpose in ('funding','spending','bill_payment','goal_saving','debt_payment'));
alter table public.financial_plan_links add column released_at timestamptz;
alter table public.financial_plan_links add column budget_id uuid;
alter table public.financial_plan_links add foreign key(budget_id,user_id) references public.financial_budgets(id,user_id) on delete restrict;
alter table public.financial_plan_links add foreign key(binding_id,user_id) references public.household_plan_bindings(id,owner_user_id) on delete restrict;
alter table public.financial_plan_links drop constraint financial_plan_links_activity_id_activity_revision_user_id_fkey;
alter table public.financial_plan_links add foreign key(activity_id,activity_revision,activity_owner_id) references public.financial_activity_revisions(activity_id,revision,user_id) on delete restrict;
alter table public.financial_plan_links drop constraint financial_plan_links_user_id_activity_id_key;
alter table public.financial_plan_links add unique(activity_owner_id,activity_id);
drop index public.financial_plan_non_debt_occurrence;
create unique index financial_plan_non_debt_occurrence on public.financial_plan_links(user_id,occurrence_id) where debt_plan_id is null and binding_id is null;
alter table public.financial_plan_links drop constraint financial_plan_claim_purpose;
alter table public.financial_plan_links add constraint financial_plan_claim_purpose check (
 (binding_id is null and contributor_membership_id is null and purpose is null and budget_id is null and activity_owner_id=user_id and (
  (expectation_id is not null and goal_id is null and debt_plan_id is null and occurrence_id is not null and attribution is null)
  or (expectation_id is null and goal_id is not null and debt_plan_id is null and attribution is not null and (coalesce((attribution->>'counting')::boolean,false) or occurrence_id is not null))
  or (expectation_id is null and goal_id is null and debt_plan_id is not null and attribution is not null)))
 or (binding_id is not null and contributor_membership_id is not null and purpose is not null and attribution is not null
  and num_nonnulls(budget_id,expectation_id,goal_id,debt_plan_id)=1)
);
create function public.default_plan_activity_owner() returns trigger language plpgsql set search_path='' as $$
begin NEW.activity_owner_id=coalesce(NEW.activity_owner_id,NEW.user_id); return NEW; end $$;
create trigger plan_activity_owner before insert on public.financial_plan_links for each row execute function public.default_plan_activity_owner();
create function public.validate_shared_claim_binding() returns trigger language plpgsql set search_path='' as $$
begin
 if NEW.binding_id is not null and not exists (
  select 1 from public.household_plan_bindings b join public.household_members m
  on m.id=NEW.contributor_membership_id and m.household_id=b.household_id
  where b.id=NEW.binding_id and b.owner_user_id=NEW.user_id
  and (b.budget_id,b.expectation_id,b.goal_id,b.debt_plan_id) is not distinct from
      (NEW.budget_id,NEW.expectation_id,NEW.goal_id,NEW.debt_plan_id)) then
  raise exception 'shared claim must retain its canonical binding' using errcode='23514';
 end if;
 return NEW;
end $$;
create trigger shared_claim_binding before insert or update on public.financial_plan_links
 for each row execute function public.validate_shared_claim_binding();
drop policy owner_read on public.financial_plan_links;
create policy owner_read on public.financial_plan_links for select to authenticated using(
 binding_id is null and user_id=(select auth.uid()) and activity_owner_id=(select auth.uid())
 and coalesce((select auth.jwt())->>'is_anonymous','false')='false');

alter table public.financial_goal_allocations add column id uuid not null default gen_random_uuid() unique;
alter table public.financial_goal_allocations add column revision integer not null default 1 check(revision>0);
alter table public.financial_goal_allocations add column binding_id uuid;
alter table public.financial_goal_allocations add column contributor_membership_id uuid references public.household_members(id) on delete restrict;
alter table public.financial_goal_allocations drop constraint financial_goal_allocations_same_owner;
alter table public.financial_goal_allocations drop constraint financial_goal_allocations_goal_id_ordinal_key;
alter table public.financial_goal_allocations add unique(goal_id,account_owner_id,ordinal) deferrable initially deferred;
alter table public.financial_goal_allocations add foreign key(binding_id,goal_owner_id) references public.household_plan_bindings(id,owner_user_id) on delete restrict;
alter table public.financial_goal_allocations add constraint allocation_owner_consent check(
 (binding_id is null and contributor_membership_id is null and goal_owner_id=account_owner_id)
 or (binding_id is not null and contributor_membership_id is not null));
drop policy owner_read on public.financial_goal_allocations;
create policy owner_read on public.financial_goal_allocations for select to authenticated using(
 goal_owner_id=(select auth.uid()) and account_owner_id=(select auth.uid())
 and coalesce((select auth.jwt())->>'is_anonymous','false')='false');
create function public.validate_shared_allocation_binding() returns trigger language plpgsql set search_path='' as $$
begin
 if NEW.binding_id is not null and not exists (
  select 1 from public.household_plan_bindings b join public.household_members m
  on m.id=NEW.contributor_membership_id and m.household_id=b.household_id and m.user_id=NEW.account_owner_id
  where b.id=NEW.binding_id and b.goal_id=NEW.goal_id and b.owner_user_id=NEW.goal_owner_id) then
  raise exception 'shared allocation must retain true owner and consent' using errcode='23514';
 end if;
 return NEW;
end $$;
create trigger shared_allocation_binding before insert or update on public.financial_goal_allocations
 for each row execute function public.validate_shared_allocation_binding();

create table public.financial_goal_allocation_revisions (
 allocation_id uuid not null, revision integer not null, goal_id uuid not null, goal_owner_id uuid not null,
 account_id uuid not null, account_owner_id uuid not null, unlinked_minor bigint not null check(unlinked_minor>=0),
 contributor_membership_id uuid references public.household_members(id) on delete restrict,
 binding_id uuid references public.household_plan_bindings(id) on delete restrict,
 primary key(allocation_id,revision),
 foreign key(goal_id,goal_owner_id) references public.financial_goals(id,user_id) on delete restrict,
 foreign key(account_id,account_owner_id) references public.financial_accounts(id,user_id) on delete restrict
);
insert into public.financial_goal_allocation_revisions
 select id,revision,goal_id,goal_owner_id,account_id,account_owner_id,unlinked_minor,contributor_membership_id,binding_id
 from public.financial_goal_allocations;
create function public.record_goal_allocation_revision() returns trigger language plpgsql set search_path='' as $$
begin
 if TG_OP='UPDATE' then
  if (OLD.unlinked_minor,OLD.binding_id,OLD.contributor_membership_id) is not distinct from
     (NEW.unlinked_minor,NEW.binding_id,NEW.contributor_membership_id) then return NEW; end if;
  NEW.revision=OLD.revision+1;
 end if;
 insert into public.financial_goal_allocation_revisions values
 (NEW.id,NEW.revision,NEW.goal_id,NEW.goal_owner_id,NEW.account_id,NEW.account_owner_id,
  NEW.unlinked_minor,NEW.contributor_membership_id,NEW.binding_id);
 return NEW;
end $$;
create trigger goal_allocation_revision before insert or update on public.financial_goal_allocations
 for each row execute function public.record_goal_allocation_revision();

create table public.household_plan_archived_claims (
 binding_id uuid not null references public.household_plan_bindings(id) on delete restrict,
 claim_id uuid not null, activity_id uuid not null, activity_owner_id uuid not null, activity_revision integer not null,
 released boolean not null, primary key(binding_id,claim_id),
 foreign key(activity_id,activity_revision,activity_owner_id) references public.financial_activity_revisions(activity_id,revision,user_id) on delete restrict
);
create table public.household_plan_archived_allocations (
 binding_id uuid not null references public.household_plan_bindings(id) on delete restrict,
 allocation_id uuid not null, revision integer not null,
 primary key(binding_id,allocation_id),
 foreign key(allocation_id,revision) references public.financial_goal_allocation_revisions(allocation_id,revision) on delete restrict
);

alter table public.financial_plan_definition_revisions enable row level security;
alter table public.household_plan_bindings enable row level security;
alter table public.household_plan_participants enable row level security;
alter table public.financial_plan_responsibilities enable row level security;
alter table public.household_plan_receipts enable row level security;
alter table public.household_plan_archived_claims enable row level security;
alter table public.financial_goal_allocation_revisions enable row level security;
alter table public.household_plan_archived_allocations enable row level security;
revoke all on public.financial_plan_definition_revisions,public.household_plan_bindings,public.household_plan_participants,
 public.financial_plan_responsibilities,public.household_plan_receipts,public.household_plan_archived_claims,
 public.financial_goal_allocation_revisions,public.household_plan_archived_allocations from public,anon,authenticated;
grant all on public.financial_plan_definition_revisions,public.household_plan_bindings,public.household_plan_participants,
 public.financial_plan_responsibilities,public.household_plan_receipts,public.household_plan_archived_claims,
 public.financial_goal_allocation_revisions,public.household_plan_archived_allocations to service_role;
revoke all on function public.record_plan_definition_revision(),public.default_plan_activity_owner(),public.record_goal_allocation_revision(),
 public.validate_shared_claim_binding(),public.validate_shared_allocation_binding() from public,anon,authenticated;
commit;
