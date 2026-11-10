set local lock_timeout = '5s';
set local statement_timeout = '60s';

revoke all on public.business_bank_accounts, public.business_bank_imports,
    public.business_bank_lines, public.business_bank_suggestions
    from public, anon, authenticated;

create function argus_private.business_bank_account_in_space(
    target_space uuid, target_account uuid
)
returns boolean
language sql
stable
set search_path = ''
as $$
    select exists (
        select 1 from public.financial_accounts a
        join public.spaces s on s.id = a.owner_space_id
        where s.id = target_space and s.kind = 'business'
            and a.id = target_account and a.user_id = s.created_by
    );
$$;

revoke all on function argus_private.business_bank_account_in_space(uuid, uuid)
    from public, anon, authenticated;
grant execute on function argus_private.business_bank_account_in_space(uuid, uuid)
    to service_role;

create function argus_private.business_bank_account_scope_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if not argus_private.business_bank_account_in_space(new.space_id, new.account_id) then
        raise exception 'account_not_in_space' using errcode = '23514';
    end if;
    return new;
end;
$$;

revoke all on function argus_private.business_bank_account_scope_guard()
    from public, anon, authenticated;

create trigger business_bank_account_scope_guard
    before insert or update of space_id, account_id on public.business_bank_accounts
    for each row execute function argus_private.business_bank_account_scope_guard();
