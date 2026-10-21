-- One profile photo per person and one logo per Business.
--
-- The picture itself is an object in the private profile-images bucket, at a
-- path the server derives from the row's key (people/{user_id}/256.webp and
-- business/{space_id}/256.webp). The server re-encodes every upload to a 256
-- px WebP square with no metadata, so the bucket accepts only that. Readers
-- get a short-lived signed URL from the API; no client reaches the bucket or
-- these rows (RLS on, no client grant), the same as receipt sources.
--
-- The row goes with its auth user or its space. The object does not: account
-- deletion erases the person's photo and the logos of every Business they
-- created (spaces.created_by cascades) in its storage step. There is no
-- Business purge yet; the one #1222 adds must erase business/{space_id}/
-- before it deletes the spaces row.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('profile-images', 'profile-images', false, 1048576, array['image/webp'])
on conflict (id) do update
    set public = false,
        file_size_limit = excluded.file_size_limit,
        allowed_mime_types = excluded.allowed_mime_types;

create table public.profile_photos (
    user_id uuid primary key references auth.users (id) on delete cascade,
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    updated_at timestamptz not null default now()
);

create table public.business_logos (
    space_id uuid primary key references public.spaces (id) on delete cascade,
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    updated_at timestamptz not null default now()
);

alter table public.profile_photos enable row level security;
alter table public.business_logos enable row level security;

revoke all on public.profile_photos from public, anon, authenticated, service_role;
revoke all on public.business_logos from public, anon, authenticated, service_role;
grant select, insert, update, delete on public.profile_photos to service_role;
grant select, insert, update, delete on public.business_logos to service_role;

comment on table public.profile_photos is
    'The person has a photo at people/{user_id}/256.webp in the private profile-images bucket; served as signed URLs by the API.';
comment on table public.business_logos is
    'The Business has a logo at business/{space_id}/256.webp in the private profile-images bucket; served as signed URLs by the API.';
