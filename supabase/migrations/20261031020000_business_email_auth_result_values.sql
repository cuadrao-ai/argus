-- What: widens business_email_deliveries_auth_result, the check on
-- public.business_email_deliveries.auth_result created by
-- 20261019040000_business_receipt_address, to also allow 'ambiguous',
-- 'no_result' and 'none'.
-- Why: the email intake routing records these sender authentication verdicts.
-- The new set contains every old value, so existing rows stay valid.
-- Rerun: drop if exists, then add, inside one transaction.
-- Rollout: staging first; James applies to production at release.

begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.business_email_deliveries
    drop constraint if exists business_email_deliveries_auth_result,
    add constraint business_email_deliveries_auth_result check (
        auth_result is null or auth_result in (
            'aligned', 'failed', 'unknown', 'ambiguous', 'no_result', 'none'
        )
    );

commit;
