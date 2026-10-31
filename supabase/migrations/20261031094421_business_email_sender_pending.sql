-- What: lets public.business_email_senders.status be 'pending' and adds the
-- sender's last authentication verdict (last_auth_result) and the time its
-- last message arrived (last_seen_at).
-- Why: mail from a sender not on the list is no longer stored; the sender row
-- is the only trace, so the Recepcion list can show it with a Verificado or
-- Sin verificar tag. Both columns stay null on existing rows (no backfill).
-- Rerun: drop if exists, then add, inside one transaction.
-- Rollout: staging first; James applies to production at release.

begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.business_email_senders
    drop constraint if exists business_email_senders_status_check,
    drop constraint if exists business_email_senders_status,
    add constraint business_email_senders_status check (
        status in ('authorized', 'blocked', 'pending')
    ),
    add column if not exists last_auth_result text,
    add column if not exists last_seen_at timestamptz,
    drop constraint if exists business_email_senders_last_auth_result,
    add constraint business_email_senders_last_auth_result check (
        last_auth_result is null or last_auth_result in (
            'aligned', 'failed', 'unknown', 'ambiguous', 'no_result', 'none'
        )
    );

commit;
