-- Widen the retained-source media types to the application's SOURCE_MEDIA_TYPES:
-- PDF, JPEG, PNG, TXT, CSV, XLSX and EML. Additive: the bucket keeps its id,
-- privacy and size limit; the path check is replaced by the same rule with the
-- wider list. Migration 20261008100000 is applied on staging and stays as is.

update storage.buckets
set allowed_mime_types = array[
    'application/pdf',
    'image/jpeg',
    'image/png',
    'text/plain',
    'text/csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'message/rfc822'
]
where id = 'financial-document-sources';

alter table public.financial_document_extractions
    drop constraint financial_document_extractions_source_object_path,
    add constraint financial_document_extractions_source_object_path check (
        source_path is null
        or (
            source_bucket = 'financial-document-sources'
            and source_sha256 ~ '^[0-9a-f]{64}$'
            and source_path = user_id::text || '/' || connection_id::text || '/' || source_sha256
            and source_media_type in (
                'application/pdf',
                'image/jpeg',
                'image/png',
                'text/plain',
                'text/csv',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'message/rfc822'
            )
            and source_size_bytes between 1 and 10485760
        )
    );
