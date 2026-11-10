-- Derivative semantic index for personalization-memory recall.
--
-- Not canonical truth: dropping this table costs recall quality, never a
-- memory. Owning the shape here keeps DDL privileges out of the API service.
-- Private backend state, like every other memory table.

create extension if not exists vector;

create table if not exists public.argus_memory_vectors (
  id uuid primary key,
  vector vector(1024),
  payload jsonb
);

-- Cosine, matching the `<=>` operator the store searches with.
create index if not exists argus_memory_vectors_hnsw_idx
  on public.argus_memory_vectors
  using hnsw (vector vector_cosine_ops);

create index if not exists argus_memory_vectors_text_lemmatized_idx
  on public.argus_memory_vectors
  using gin (to_tsvector('simple', payload ->> 'text_lemmatized'));

alter table public.argus_memory_vectors enable row level security;
alter table public.argus_memory_vectors force row level security;

revoke all on table public.argus_memory_vectors
  from public, anon, authenticated, service_role;
