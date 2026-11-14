begin;

-- The owner's "Eliminar definitivamente" is a human command, like delete and
-- restore. The 7-day expiry writes no ledger row.
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
            'restore_document'::text,
            'purge_document'::text
        ])) is true
    ),
    drop constraint business_document_delete_human_commands,
    add constraint business_document_delete_human_commands check (
        command->>'action' not in ('delete_document', 'restore_document', 'purge_document')
        or ((actor->>'actor_kind' = 'member'
             and turn_key is null and action_index is null) is true)
    );

-- A document purge deletes the message sources of its own drafts. The mark is
-- transaction-local, Postgres-only and names one Business.
create function argus_private.business_document_purge_marked(space uuid) returns boolean
    language sql stable
    set search_path to ''
    as $$
    select current_user = 'postgres'
        and current_setting('argus.business_document_purge_space', true) = space::text
$$;

revoke all on function argus_private.business_document_purge_marked(space uuid) from public;
grant all on function argus_private.business_document_purge_marked(space uuid) to service_role;

create or replace function argus_private.business_immutable_evidence() returns trigger
    language plpgsql
    set search_path to ''
    as $$
begin
    if current_user = 'postgres' and tg_op = 'UPDATE' then
        if argus_private.business_custody_identity_change(tg_table_name, to_jsonb(old), to_jsonb(new)) then
            return new;
        end if;
    end if;
    if tg_op = 'DELETE'
        and (pg_trigger_depth() > 1
             or argus_private.business_purge_marked(old.space_id)
             or argus_private.business_document_purge_marked(old.space_id)) then
        return old;
    end if;
    raise exception 'business_evidence_immutable' using errcode = '23514';
end;
$$;

create table argus_private.business_document_purges (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    document_ids uuid[] not null,
    reason text not null,
    purged_at timestamptz not null default clock_timestamp(),
    pending_objects text[] not null default '{}'::text[],
    constraint business_document_purges_ids check (cardinality(document_ids) between 1 and 1000),
    constraint business_document_purges_reason check (reason in ('owner', 'expiry'))
);

comment on table argus_private.business_document_purges is 'One row per purged Business document: the draft and upload ids it answered to, why it went, and the stored objects still to erase. No name, amount, file name or content. A Business purge removes it with the space.';

alter table argus_private.business_document_purges enable row level security;

create index business_document_purges_space_idx
    on argus_private.business_document_purges (space_id, purged_at);
create index business_document_purges_pending_idx
    on argus_private.business_document_purges (purged_at)
    where pending_objects <> '{}'::text[];

-- The hourly expiry reads only deleted documents.
create index financial_import_events_deleted_idx
    on public.financial_import_events (owner_space_id)
    where state = 'dismissed' and resolution ? 'deleted';
create index financial_document_extractions_deleted_idx
    on public.financial_document_extractions (connection_id)
    where (draft->>'status') = 'dismissed' and (draft->'resolution') ? 'deleted';

commit;
