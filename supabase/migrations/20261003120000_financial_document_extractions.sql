-- Validated candidate delivery checkpoints. No raw document bytes or OCR text.
create table if not exists public.financial_document_extractions (
    connection_id uuid primary key references public.financial_source_connections(id)
        on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    batch jsonb not null check (jsonb_typeof(batch) = 'object'),
    created_at timestamptz not null default now()
);

create index if not exists financial_document_extractions_user_idx
    on public.financial_document_extractions (user_id);

alter table public.financial_document_extractions enable row level security;
revoke all on public.financial_document_extractions from public, anon, authenticated;
grant all on public.financial_document_extractions to service_role;
