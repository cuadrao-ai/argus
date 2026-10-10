alter table public.financial_records
    alter column account_id drop not null,
    add column owner_space_id uuid,
    add column funding text,
    add column currency text,
    add constraint financial_records_owner_funded_scope_fk
        foreign key (owner_space_id, user_id)
        references public.spaces (id, created_by) on delete cascade,
    add constraint financial_records_funding_shape check (
        (account_id is not null and owner_space_id is null and funding is null and currency is null)
        or (account_id is null and owner_space_id is not null and record_kind = 'expense'
            and funding is not null and funding = 'owner_funds' and currency is not null and currency ~ '^[A-Z]{3}$')
    );

create index financial_records_owner_funded_scope_idx
    on public.financial_records (user_id, owner_space_id)
    where account_id is null;

create policy financial_records_account_read on public.financial_records
    as restrictive for select to authenticated using (account_id is not null);

create policy financial_record_revisions_account_read on public.financial_record_revisions
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_records r
        where r.id = financial_record_revisions.record_id
        and r.user_id = financial_record_revisions.user_id));

create policy financial_activity_memberships_account_read on public.financial_activity_memberships
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_records r
        where r.id = financial_activity_memberships.record_id
        and r.user_id = financial_activity_memberships.record_owner_id));

create policy financial_activity_groups_account_read on public.financial_activity_groups
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_activity_memberships m
        where m.activity_id = financial_activity_groups.id
        and m.user_id = financial_activity_groups.user_id));

create policy financial_activity_revisions_account_read on public.financial_activity_revisions
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_activity_groups g
        where g.id = financial_activity_revisions.activity_id
        and g.user_id = financial_activity_revisions.user_id));
