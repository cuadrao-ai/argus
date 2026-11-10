-- The Business's legal name (razón social), confirmed by a person who manages it
-- against the registry row for its own tax id. Who confirmed it and when sit on
-- the same row; the confirmation is also a set_business_legal_name action receipt.
-- A legal name needs a stored tax id. Changing or clearing the tax id clears it.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.spaces
    add column business_legal_name text,
    add column business_legal_name_confirmed_by uuid
        references auth.users (id) on delete set null,
    add column business_legal_name_confirmed_at timestamptz,
    add constraint business_legal_name_confirmed check (
        (
            business_legal_name is null
            and business_legal_name_confirmed_by is null
            and business_legal_name_confirmed_at is null
        )
        or (
            kind = 'business'
            and business_rnc is not null
            and length(btrim(business_legal_name)) between 1 and 250
            and business_legal_name = btrim(business_legal_name)
            and business_legal_name_confirmed_at is not null
        )
    );

-- The confirmation is a person's own command, with no turn, like set_business_rnc.
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
            'reopen_draft', 'set_business_legal_name')) is true
    ),
    add constraint business_legal_name_human_commands check (
        command->>'action' <> 'set_business_legal_name' or
        (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null) is true
    );

commit;
