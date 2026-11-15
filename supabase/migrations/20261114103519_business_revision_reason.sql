begin;

-- Why a revision that no person and no read made exists. Null for every other
-- revision. The first Business RNC writes 'business_rnc_set' on the drafts it
-- moves to Ventas.
alter table public.business_draft_revisions
    add column reason text,
    add constraint business_draft_revisions_reason_check check (
        reason in ('business_rnc_set')
    );

commit;
