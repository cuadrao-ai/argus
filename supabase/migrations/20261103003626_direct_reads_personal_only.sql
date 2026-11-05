-- Direct client reads stop at Personal rows.
--
-- A Business keeps its storage identity when ownership moves, so user_id does
-- not say who may read a Business row today. Only the API checks live grants.
-- These restrictive policies keep the client role on Personal rows, and name
-- authenticated alone, so the server roles read as before.
--
-- A child asks whether its parent is visible, because row security applies
-- inside a policy's subquery. financial_accounts and
-- financial_source_connections own the Personal fact. Revisions, activity
-- memberships, groups and activity revisions already ask their parent through
-- the *_account_read policies of 20261011010000, so they follow financial_records.
--
-- Two lookups run as definer functions. The client role has no read on
-- conversations, and it cannot see every leg of an activity.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

create function argus_private.conversation_is_personal(p_conversation_id uuid)
returns boolean
language sql stable security definer set search_path = '' as $$
    select not exists (
        select 1 from public.conversations c
        where c.id = p_conversation_id and c.owner_space_id is not null
    );
$$;

create function argus_private.financial_activity_is_personal(p_activity_id uuid)
returns boolean
language sql stable security definer set search_path = '' as $$
    select not exists (
        select 1 from public.financial_activity_memberships m
        join public.financial_records r on r.id = m.record_id
        left join public.financial_accounts a on a.id = r.account_id
        where m.activity_id = p_activity_id
          and (r.owner_space_id is not null or a.owner_space_id is not null)
    );
$$;

revoke all on function argus_private.conversation_is_personal(uuid),
    argus_private.financial_activity_is_personal(uuid) from public, anon;
grant execute on function argus_private.conversation_is_personal(uuid),
    argus_private.financial_activity_is_personal(uuid) to authenticated, service_role;

create policy financial_accounts_personal_read on public.financial_accounts
    as restrictive for select to authenticated
    using (owner_space_id is null);

create policy financial_source_connections_personal_read
    on public.financial_source_connections
    as restrictive for select to authenticated
    using (owner_space_id is null);

-- Also covers what this replaces: a record with no account has no parent.
drop policy financial_records_account_read on public.financial_records;
create policy financial_records_personal_read on public.financial_records
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_accounts a
        where a.id = financial_records.account_id));

create policy financial_asset_details_personal_read on public.financial_asset_details
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_accounts a
        where a.id = financial_asset_details.account_id));

create policy financial_asset_changes_personal_read on public.financial_asset_changes
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_accounts a
        where a.id = financial_asset_changes.account_id));

create policy financial_observation_coverage_personal_read
    on public.financial_observation_coverage
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_accounts a
        where a.id = financial_observation_coverage.account_id));

create policy financial_goal_allocations_personal_read
    on public.financial_goal_allocations
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_accounts a
        where a.id = financial_goal_allocations.account_id));

create policy financial_debt_plans_personal_read on public.financial_debt_plans
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_accounts a
        where a.id = financial_debt_plans.debt_account_id));

create policy financial_import_account_links_personal_read
    on public.financial_import_account_links
    as restrictive for select to authenticated
    using (
        exists (select 1 from public.financial_accounts a
            where a.id = financial_import_account_links.account_id)
        and exists (select 1 from public.financial_source_connections c
            where c.id = financial_import_account_links.connection_id)
    );

create policy financial_source_gmail_senders_personal_read
    on public.financial_source_gmail_senders
    as restrictive for select to authenticated
    using (exists (select 1 from public.financial_source_connections c
        where c.id = financial_source_gmail_senders.connection_id));

create policy financial_plan_links_personal_read on public.financial_plan_links
    as restrictive for select to authenticated
    using (argus_private.financial_activity_is_personal(activity_id));

create policy chat_turn_lifecycles_personal_read on public.chat_turn_lifecycles
    as restrictive for select to authenticated
    using (argus_private.conversation_is_personal(conversation_id));

create policy conversation_read_states_personal_read on public.conversation_read_states
    as restrictive for select to authenticated
    using (argus_private.conversation_is_personal(conversation_id));

create policy backtest_jobs_personal_read on public.backtest_jobs
    as restrictive for select to authenticated
    using (argus_private.conversation_is_personal(conversation_id));

commit;
