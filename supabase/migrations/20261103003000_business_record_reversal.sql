-- Reabrir: an approved record returns to the Bandeja for correction. Its money
-- row stays, with every revision, membership and receipt, and reversed_at names
-- the instant it stopped counting. The ledger loaders leave a reversed row out
-- (argus.domain.recording: canonical_groups.load, loop_postgres.hydrate,
-- owner_funds_postgres.load), so period totals, the month close, the 606 and
-- 607, Registros and the account it debited read as before the approval. Who
-- reopened it, when and from which draft version is the reopen_draft row in
-- business_action_receipts. A later approval writes a new row; this one is
-- never written to again.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.financial_activity_groups
    add column reversed_at timestamptz;

-- The reopen is a person's own command, with no turn, like the approval it undoes.
alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment', 'settle_remainder',
            'access_seen', 'email_ai_consent_declined', 'mark_personal', 'decide_606',
            'receipt_upload', 'receipt_review', 'receipt_confirm', 'approve_refund', 'set_business_rnc',
            'resolve_duplicate', 'change_role', 'edit_current_note', 'append_supporting_file',
            'reopen_draft')) is true
    );

commit;
