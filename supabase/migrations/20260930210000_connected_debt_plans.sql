alter table public.financial_records drop constraint financial_records_record_kind_check;
alter table public.financial_records add constraint financial_records_record_kind_check
check(record_kind in ('opening_balance','balance_check','expense','income','transfer','card_payment','refund','debt_payment','payment_reversal'));
alter table public.financial_activity_groups drop constraint financial_activity_groups_kind_check;
alter table public.financial_activity_groups add constraint financial_activity_groups_kind_check
check(kind in ('expense','income','transfer','card_payment','refund','debt_payment','payment_reversal'));
alter table public.financial_record_revisions
 add column reversal_of_activity_id uuid generated always as ((details->>'reversal_of_activity_id')::uuid) stored,
 add column reversal_of_revision integer generated always as ((details->>'reversal_of_revision')::integer) stored,
 add constraint financial_payment_return_revision_pair check((reversal_of_activity_id is null) = (reversal_of_revision is null)),
 add constraint financial_payment_return_owner_fk foreign key(reversal_of_activity_id,reversal_of_revision,user_id)
 references public.financial_activity_revisions(activity_id,revision,user_id) on delete cascade;

create table public.financial_debt_plans (
 id uuid primary key,
 user_id uuid not null references auth.users(id) on delete cascade,
 debt_account_id uuid not null,
 body jsonb not null,
 unique(id,user_id),
 foreign key(debt_account_id,user_id) references public.financial_accounts(id,user_id) on delete cascade,
 check(body->>'id'=id::text),
 check(body->>'debt_account_id'=debt_account_id::text),
 check((body->>'version')::integer > 0)
);
create unique index financial_debt_plan_active_account on public.financial_debt_plans(user_id,debt_account_id)
 where (body->>'archived')::boolean=false;
alter table public.financial_debt_plans enable row level security;
revoke all on public.financial_debt_plans from public,anon,authenticated;
grant select on public.financial_debt_plans to authenticated;
grant all on public.financial_debt_plans to service_role;
create policy owner_read on public.financial_debt_plans for select to authenticated
using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');

alter table public.financial_plan_links add column debt_plan_id uuid;
alter table public.financial_plan_links add foreign key(debt_plan_id,user_id)
 references public.financial_debt_plans(id,user_id) on delete cascade;
alter table public.financial_plan_links drop constraint financial_plan_links_user_id_occurrence_id_key;
create unique index financial_plan_non_debt_occurrence on public.financial_plan_links(user_id,occurrence_id) where debt_plan_id is null;
alter table public.financial_plan_links drop constraint financial_plan_claim_purpose;
alter table public.financial_plan_links add constraint financial_plan_claim_purpose check (
 (expectation_id is not null and goal_id is null and debt_plan_id is null and occurrence_id is not null and attribution is null)
 or (expectation_id is null and goal_id is not null and debt_plan_id is null and attribution is not null
     and (coalesce((attribution->>'counting')::boolean,false) or occurrence_id is not null))
 or (expectation_id is null and goal_id is null and debt_plan_id is not null and attribution is not null)
);
