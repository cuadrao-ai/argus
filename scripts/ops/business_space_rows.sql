-- Revert gate for the Business space slices (plan section 7). Read-only.
-- A revert of S1 or S2 first records an all-zero result from the target.
select
    (select count(*) from public.financial_accounts
      where owner_space_id is not null) as business_accounts,
    (select count(*) from public.financial_source_connections
      where owner_space_id is not null) as business_connections,
    (select count(*) from public.financial_import_events
      where owner_space_id is not null) as business_import_events,
    (select count(*) from public.conversations
      where owner_space_id is not null) as business_conversations,
    (select count(*) from public.spaces) as spaces;
