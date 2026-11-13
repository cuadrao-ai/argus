begin;

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or ((command->>'action') = any (array[
            'review_draft'::text,
            'approve_expense'::text,
            'capture_note'::text,
            'approve_income'::text,
            'prepare_attachment'::text,
            'owner_grant'::text,
            'grant_access'::text,
            'invite_access'::text,
            'accept_invite'::text,
            'revoke_grant'::text,
            'revoke_invite'::text,
            'rebind_attachment'::text,
            'settle_remainder'::text,
            'access_seen'::text,
            'email_ai_consent_declined'::text,
            'mark_personal'::text,
            'decide_606'::text,
            'receipt_upload'::text,
            'receipt_review'::text,
            'receipt_confirm'::text,
            'approve_refund'::text,
            'set_business_rnc'::text,
            'resolve_duplicate'::text,
            'change_role'::text,
            'edit_current_note'::text,
            'append_supporting_file'::text,
            'reopen_draft'::text,
            'set_business_legal_name'::text,
            'delete_document'::text,
            'restore_document'::text
        ])) is true
    ),
    add constraint business_document_delete_human_commands check (
        command->>'action' not in ('delete_document', 'restore_document')
        or ((actor->>'actor_kind' = 'member'
             and turn_key is null and action_index is null) is true)
    );

commit;
