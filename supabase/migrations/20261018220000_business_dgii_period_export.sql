set lock_timeout = '5s';
set statement_timeout = '60s';

alter table public.spaces
    add column business_rnc text,
    add constraint business_rnc_shape check (
        business_rnc is null or (kind = 'business' and business_rnc ~ '^([0-9]{9}|[0-9]{11})$' and business_rnc !~ '^0+$')
    );

alter table public.business_draft_revisions
    add column before_dgii jsonb,
    add column after_dgii jsonb,
    add constraint business_dgii_snapshot_objects check (
        (before_dgii is null or jsonb_typeof(before_dgii) = 'object') and
        (after_dgii is null or jsonb_typeof(after_dgii) = 'object')
    );

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment', 'settle_remainder',
            'access_seen', 'email_ai_consent_declined', 'mark_personal', 'decide_606',
            'receipt_upload', 'receipt_review', 'receipt_confirm', 'approve_refund', 'set_business_rnc')) is true
    ),
    add constraint business_dgii_human_commands check (
        command->>'action' not in ('approve_refund', 'set_business_rnc') or
        (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null) is true
    );

reset lock_timeout;
reset statement_timeout;
