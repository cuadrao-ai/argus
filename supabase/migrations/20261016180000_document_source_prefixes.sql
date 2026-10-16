-- One row remains one document connection. Each copy has its own reference;
-- owner/hash objects may be shared by several connections for the same owner.
alter table public.financial_document_extractions
    add column rebuilt_bucket text,
    add column rebuilt_path text,
    add column rebuilt_media_type text,
    add column rebuilt_size_bytes integer,
    add column rebuilt_sha256 text,
    drop constraint financial_document_extractions_source_object_path,
    add constraint financial_document_extractions_source_object_path check (
        source_path is null or (
            source_bucket = 'financial-document-sources'
            and source_sha256 ~ '^[0-9a-f]{64}$'
            and source_path in (
                user_id::text || '/' || connection_id::text || '/' || source_sha256,
                'sealed/' || user_id::text || '/' || source_sha256
            )
            and source_media_type in (
                'application/pdf', 'image/jpeg', 'image/png', 'text/plain', 'text/csv',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/xml', 'text/xml', 'message/rfc822'
            )
            and source_size_bytes between 1 and 10485760
        )
    ),
    add constraint financial_document_extractions_rebuilt_object check (
        num_nulls(rebuilt_bucket, rebuilt_path, rebuilt_media_type,
                  rebuilt_size_bytes, rebuilt_sha256) in (0, 5)
    ),
    add constraint financial_document_extractions_rebuilt_path check (
        rebuilt_path is null or (
            rebuilt_bucket = 'financial-document-sources'
            and rebuilt_sha256 ~ '^[0-9a-f]{64}$'
            and draft is not null and draft->>'sha256' is not null
            and draft->>'sha256' ~ '^[0-9a-f]{64}$'
            and rebuilt_path = 'rebuilt/' || user_id::text || '/' || (draft->>'sha256')
            and rebuilt_media_type in (
                'application/pdf', 'image/jpeg', 'image/png', 'text/plain', 'text/csv',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'application/xml', 'text/xml', 'message/rfc822'
            )
            and rebuilt_size_bytes between 1 and 10485760
        )
    );

create index financial_document_extractions_source_references
    on public.financial_document_extractions (user_id, source_path)
    where source_path is not null;
create index financial_document_extractions_rebuilt_references
    on public.financial_document_extractions (user_id, rebuilt_path)
    where rebuilt_path is not null;

comment on column public.financial_document_extractions.source_path is
    'Sealed original at sealed/{user_id}/{original_sha256}; legacy unprefixed objects stay in place.';
comment on column public.financial_document_extractions.rebuilt_path is
    'User-readable copy at rebuilt/{user_id}/{original_sha256}; absent until a rebuilt producer writes it.';
comment on column public.financial_document_extractions.rebuilt_sha256 is
    'Digest of rebuilt bytes, independently verified when read. The object name uses the original digest.';
