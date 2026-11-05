create table public.financial_budgets (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  body jsonb not null,
  unique(id,user_id),
  check(body->>'id'=id::text),
  check((body->>'version')::integer > 0),
  check((body->>'limit_minor')::bigint > 0),
  check(jsonb_array_length(body->'account_ids') > 0)
);
create unique index financial_budgets_active_scope on public.financial_budgets
(user_id, (body->>'month'), (body->>'currency'), (body->'account_ids'),
 (body->'category_ids'), ((body->>'include_uncategorized')::boolean))
where (body->>'archived')::boolean = false;
alter table public.financial_budgets enable row level security;
revoke all on public.financial_budgets from anon,authenticated;
grant select on public.financial_budgets to authenticated;
grant all on public.financial_budgets to service_role;
create policy owner_read on public.financial_budgets for select to authenticated
using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');
