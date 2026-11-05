-- Four more turn-less human ledger rows, all at once so one migration owns
-- the allow-list: access_seen (a grantee saw the one-time "you now have
-- access" line), email_ai_consent_declined (the owner declined the one-time
-- notice about reading emailed receipts with AI; no permission row exists),
-- mark_personal (the owner marks or unmarks a receipt as personal) and
-- decide_606 (a prepare-holder other than the owner answers whether a
-- personal receipt with a fiscal number goes into the 606), and the three
-- writes of the legacy receipt surface a grantee can make (receipt_upload,
-- receipt_review, receipt_confirm), so no grantee write goes unledgered. The list is the
-- union with every name already admitted, so the migration applies after any
-- of them. Each new action is a person's own row: member kind, no turn, no
-- action index.

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment', 'settle_remainder',
            'access_seen', 'email_ai_consent_declined', 'mark_personal', 'decide_606',
            'receipt_upload', 'receipt_review', 'receipt_confirm')) is true
    ),
    add constraint business_action_receipts_human_only_actions check (
        command->>'action' not in ('access_seen', 'email_ai_consent_declined', 'mark_personal', 'decide_606',
            'receipt_upload', 'receipt_review', 'receipt_confirm')
        or (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null) is true
    );
