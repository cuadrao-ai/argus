-- #778: retained document sources move from source_bytes to private Storage.
--
-- Capture writes the object first, then commits this row's reference, so a
-- crash leaves an unreferenced object under the owner's prefix, never a row
-- pointing at nothing. Disconnect deletes the connection's prefix and then the
-- row; account deletion deletes the owner's prefix. Only the service role
-- reaches the bucket: it is private and storage.objects has no policy for it.
--
-- source_bytes is never written again. Rows captured before this migration
-- keep it and are still served from it (dual read) until a later migration
-- drops the column.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'financial-document-sources',
    'financial-document-sources',
    false,
    10485760,
    array['application/pdf', 'image/jpeg', 'image/png']
)
on conflict (id) do update
    set public = false,
        file_size_limit = excluded.file_size_limit,
        allowed_mime_types = excluded.allowed_mime_types;

alter table public.financial_document_extractions
    add column source_bucket text,
    add column source_path text,
    add column source_media_type text,
    add column source_size_bytes integer,
    add column source_sha256 text,
    add constraint financial_document_extractions_source_object check (
        num_nulls(
            source_bucket, source_path, source_media_type, source_size_bytes, source_sha256
        ) in (0, 5)
    ),
    add constraint financial_document_extractions_source_object_path check (
        source_path is null
        or (
            source_bucket = 'financial-document-sources'
            and source_sha256 ~ '^[0-9a-f]{64}$'
            and source_path = user_id::text || '/' || connection_id::text || '/' || source_sha256
            and source_media_type in ('application/pdf', 'image/jpeg', 'image/png')
            and source_size_bytes between 1 and 10485760
        )
    ),
    add constraint financial_document_extractions_one_source check (
        source_bytes is null or source_path is null
    ),
    add constraint financial_document_extractions_source_has_draft check (
        (source_bytes is null and source_path is null) or draft is not null
    ),
    add constraint financial_document_extractions_not_empty check (
        batch is not null or draft is not null
    );

comment on table public.financial_document_extractions is
    'Private document draft, preparation checkpoint and Storage reference to the retained source; erased on disconnect/deletion.';
comment on column public.financial_document_extractions.source_path is
    'Object in the private financial-document-sources bucket: {user_id}/{connection_id}/{sha256}.';
comment on column public.financial_document_extractions.source_bytes is
    'Legacy retained source from before 20261008100000. Read only; never written.';
