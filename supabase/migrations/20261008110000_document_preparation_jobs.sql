-- The current preparation attempt of a document draft (#823). It lives on the
-- existing private checkpoint row, so disconnect and deletion erase it with the
-- draft and source. Only the attempt named here may claim the draft.
alter table public.financial_document_extractions
    add column if not exists preparation_job jsonb
        check (preparation_job is null or jsonb_typeof(preparation_job) = 'object');

alter table public.financial_document_extractions enable row level security;
revoke all on public.financial_document_extractions from public, anon, authenticated;
grant all on public.financial_document_extractions to service_role;

-- The reconciler sweep reads only drafts awaiting preparation or a retry.
create index if not exists financial_document_extractions_pending_idx
    on public.financial_document_extractions (created_at, connection_id)
    where draft->>'status' in ('queued', 'preparing')
        or (draft->>'status' = 'needs_attention'
            and (preparation_job->>'retry')::boolean);
