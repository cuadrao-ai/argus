set lock_timeout = '5s';
set statement_timeout = '60s';

-- The current due date lives in financial_import_events.resolution.business.due_on.
-- These columns keep each revision's before and after value, like before_dgii.
alter table public.business_draft_revisions
    add column before_due_on date,
    add column after_due_on date;

-- The table stays server-only: RLS on, no client policy, and only the service
-- role reads and appends rows.
alter table public.business_draft_revisions enable row level security;
revoke all on public.business_draft_revisions from public, anon, authenticated;

reset lock_timeout;
reset statement_timeout;
