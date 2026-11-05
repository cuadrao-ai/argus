begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table argus_private.business_saved_report_views
    drop constraint business_saved_report_views_recipe_check;
alter table argus_private.business_saved_report_views
    add constraint business_saved_report_views_recipe_check
    check (jsonb_typeof(recipe) = 'object' and recipe->>'schema_version' in ('1', '2'));

alter table public.business_draft_revisions
    add column before_current_note text,
    add column after_current_note text;
alter table public.business_draft_revisions
    add constraint business_draft_revisions_current_note_length
    check (after_current_note is null or char_length(after_current_note) <= 500);

comment on column public.business_draft_revisions.after_current_note is
    'Current-note replacement in Unicode code points. Null means no note edit; empty text explicitly clears. Financial facts remain unchanged.';
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
            'resolve_duplicate', 'change_role', 'edit_current_note', 'append_supporting_file')) is true
    );

alter table public.business_action_receipts
    add constraint business_annotation_human_commands check (
        command->>'action' not in ('edit_current_note', 'append_supporting_file') or
        (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null) is true
    );

commit;
