create table public.financial_expectations (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  body jsonb not null,
  unique(id,user_id),
  check(body->>'id'=id::text),
  check((body->>'version')::integer > 0)
);
create table public.financial_plan_selections (
  user_id uuid primary key references auth.users(id) on delete cascade,
  body jsonb not null
);
create table public.financial_plan_links (
  user_id uuid not null references auth.users(id) on delete cascade,
  occurrence_id uuid not null,
  expectation_id uuid not null,
  activity_id uuid not null,
  activity_revision integer not null,
  snapshot jsonb not null,
  primary key(user_id,occurrence_id),
  unique(user_id,activity_id),
  foreign key(expectation_id,user_id) references public.financial_expectations(id,user_id) on delete cascade,
  foreign key(activity_id,activity_revision,user_id) references public.financial_activity_revisions(activity_id,revision,user_id)
);
create table public.financial_plan_receipts (
  user_id uuid not null references auth.users(id) on delete cascade,
  scope text not null,
  idempotency_key text not null,
  identity_hash text not null,
  result jsonb not null,
  primary key(user_id,scope,idempotency_key)
);
alter table public.financial_expectations enable row level security;
alter table public.financial_plan_selections enable row level security;
alter table public.financial_plan_links enable row level security;
alter table public.financial_plan_receipts enable row level security;
revoke all on public.financial_expectations,public.financial_plan_selections,public.financial_plan_links,public.financial_plan_receipts from anon,authenticated;
grant select on public.financial_expectations,public.financial_plan_selections,public.financial_plan_links to authenticated;
grant all on public.financial_expectations,public.financial_plan_selections,public.financial_plan_links,public.financial_plan_receipts to service_role;
create policy owner_read on public.financial_expectations for select to authenticated using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');
create policy owner_read on public.financial_plan_selections for select to authenticated using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');
create policy owner_read on public.financial_plan_links for select to authenticated using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');
