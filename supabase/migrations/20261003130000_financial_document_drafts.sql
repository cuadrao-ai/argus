-- Source and draft share the existing owner-scoped preparation checkpoint.
alter table public.financial_document_extractions
    alter column batch drop not null,
    add column if not exists source_bytes bytea
        check (octet_length(source_bytes) between 1 and 10485760),
    add column if not exists draft jsonb
        check (jsonb_typeof(draft) = 'object');

comment on table public.financial_document_extractions is
    'Private retained document source, draft and preparation checkpoint; erased on disconnect/deletion.';
