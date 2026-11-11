create table public.financial_goals (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  body jsonb not null,
  unique(id,user_id),
  check(body->>'id'=id::text),
  check((body->>'version')::integer > 0),
  check((body->>'target_minor')::bigint > 0)
);
alter table public.financial_goals enable row level security;
revoke all on public.financial_goals from anon,authenticated;
grant select on public.financial_goals to authenticated;
grant all on public.financial_goals to service_role;
create policy owner_read on public.financial_goals for select to authenticated
using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');

alter table public.financial_plan_links add column claim_id uuid;
update public.financial_plan_links set claim_id=occurrence_id;
alter table public.financial_plan_links alter column claim_id set not null;
alter table public.financial_plan_links alter column claim_id set default gen_random_uuid();
alter table public.financial_plan_links drop constraint financial_plan_links_pkey;
alter table public.financial_plan_links add primary key(user_id,claim_id);
alter table public.financial_plan_links add unique(user_id,occurrence_id);
alter table public.financial_plan_links alter column occurrence_id drop not null;
alter table public.financial_plan_links alter column expectation_id drop not null;
alter table public.financial_plan_links add column goal_id uuid;
alter table public.financial_plan_links add column attribution jsonb;
alter table public.financial_plan_links add foreign key(goal_id,user_id)
  references public.financial_goals(id,user_id) on delete cascade;
alter table public.financial_plan_links add constraint financial_plan_claim_purpose check (
  (expectation_id is not null and goal_id is null and occurrence_id is not null and attribution is null)
  or (expectation_id is null and goal_id is not null and attribution is not null
      and (coalesce((attribution->>'counting')::boolean,false) or occurrence_id is not null))
);
