create table public.financial_asset_details (
 account_id uuid primary key,
 user_id uuid not null references auth.users(id) on delete cascade,
 related_debt_account_id uuid,
 foreign key(account_id,user_id) references public.financial_accounts(id,user_id) on delete cascade,
 foreign key(related_debt_account_id,user_id) references public.financial_accounts(id,user_id),
 check(account_id <> related_debt_account_id)
);
create index financial_asset_debt_owner on public.financial_asset_details(user_id,related_debt_account_id);
create table public.financial_asset_changes (
 account_id uuid not null,
 user_id uuid not null references auth.users(id) on delete cascade,
 account_version integer not null check(account_version > 1),
 previous_share_bps integer not null check(previous_share_bps between 1 and 10000),
 ownership_share_bps integer not null check(ownership_share_bps between 1 and 10000),
 previous_debt_account_id uuid,
 related_debt_account_id uuid,
 recorded_by uuid not null,
 recorded_at timestamptz not null default now(),
 idempotency_key text not null,
 identity_hash text not null,
 primary key(account_id,account_version),
 unique(user_id,account_id,idempotency_key),
 foreign key(account_id,user_id) references public.financial_accounts(id,user_id) on delete cascade,
 foreign key(previous_debt_account_id,user_id) references public.financial_accounts(id,user_id),
 foreign key(related_debt_account_id,user_id) references public.financial_accounts(id,user_id),
 check(recorded_by=user_id)
);
alter table public.financial_asset_details enable row level security;
alter table public.financial_asset_changes enable row level security;
revoke all on public.financial_asset_details,public.financial_asset_changes from public,anon,authenticated;
grant select on public.financial_asset_details,public.financial_asset_changes to authenticated;
grant all on public.financial_asset_details to service_role;
grant select,insert on public.financial_asset_changes to service_role;
create policy owner_read on public.financial_asset_details for select to authenticated
using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');
create policy owner_read on public.financial_asset_changes for select to authenticated
using(user_id=(select auth.uid()) and coalesce((select auth.jwt())->>'is_anonymous','false')='false');

create function public.validate_financial_asset_types() returns trigger
language plpgsql set search_path=public as $$
begin
 if TG_TABLE_NAME='financial_asset_details' then
  if not exists(select 1 from financial_accounts where id=new.account_id and user_id=new.user_id and type in ('property','vehicle','other_asset'))
   or (new.related_debt_account_id is not null and not exists(select 1 from financial_accounts where id=new.related_debt_account_id and user_id=new.user_id and type in ('credit_card','other_debt'))) then
   raise exception 'invalid asset or liability type' using errcode='23514';
  end if;
 elsif new.type<>old.type and (
  (new.type not in ('property','vehicle','other_asset') and exists(select 1 from financial_asset_details where account_id=new.id))
  or (new.type not in ('credit_card','other_debt') and exists(select 1 from financial_asset_details where related_debt_account_id=new.id))
 ) then
  raise exception 'linked account type is retained' using errcode='23514';
 end if;
 return new;
end $$;
revoke all on function public.validate_financial_asset_types() from public,anon,authenticated;
create trigger financial_asset_types before insert or update on public.financial_asset_details
 for each row execute function public.validate_financial_asset_types();
create trigger financial_asset_account_types before update of type on public.financial_accounts
 for each row execute function public.validate_financial_asset_types();
