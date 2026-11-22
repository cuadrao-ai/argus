begin;

-- Taking a supporting file off a record and putting it back are human
-- commands, like the append beside them.
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
            'unlink_supporting_file'::text,
            'restore_supporting_file'::text,
            'reopen_draft'::text,
            'set_business_legal_name'::text,
            'delete_document'::text,
            'restore_document'::text,
            'purge_document'::text
        ])) is true
    ),
    drop constraint business_annotation_human_commands,
    add constraint business_annotation_human_commands check (
        command->>'action' not in (
            'edit_current_note', 'append_supporting_file',
            'unlink_supporting_file', 'restore_supporting_file'
        )
        or ((actor->>'actor_kind' = 'member'
             and turn_key is null and action_index is null) is true)
    );

-- What a revision did to the one supporting file in source_ids, and the file's
-- name as it was then. The name stays after the file's bytes are erased.
alter table public.business_draft_revisions
    add column supporting_change text,
    add column supporting_filename text,
    add constraint business_draft_revisions_supporting_change check (
        (supporting_change is null and supporting_filename is null)
        or ((supporting_change in ('appended', 'unlinked', 'restored')
             and cardinality(source_ids) = 1
             and (supporting_filename is null
                  or char_length(supporting_filename) between 1 and 80)) is true)
    );

comment on column public.business_draft_revisions.supporting_change is 'Set on a supporting-file revision: appended, unlinked or restored. The newest unlinked revision of a file with no link starts its 7-day restore window. Null on every other revision and on appends from before this column.';

-- The expiry pass reads only supporting files and their unlink revisions.
create index business_sources_supporting_idx
    on public.business_sources (space_id, id)
    where kind = 'attachment' and source_key = 'supporting:' || connection_id::text;
create index business_draft_revisions_unlinked_idx
    on public.business_draft_revisions (space_id, created_at)
    where supporting_change = 'unlinked';

-- A supporting file's upload carries its own reference from now on, so the
-- same bytes uploaded as a receipt are a second upload, never this one. An
-- upload from before that only a supporting file holds moves to that form.
update public.financial_source_connections c
set external_ref = 'supporting:' || c.external_ref
where c.source = 'statement'
    and c.external_ref not like 'supporting:%'
    and c.external_ref not like 'retained:%'
    and exists (
        select 1 from public.business_sources s
        where s.space_id = c.owner_space_id and s.connection_id = c.id
            and s.kind = 'attachment'
            and s.source_key = 'supporting:' || s.connection_id::text
            and not exists (
                select 1 from public.business_sources o
                where o.space_id = s.space_id
                    and o.connection_id = s.connection_id and o.id <> s.id)
            and not exists (
                select 1 from public.financial_import_observations o
                where o.connection_id = s.connection_id));

commit;
