alter table public.business_draft_revisions
    add column before_document_type text check (before_document_type in ('recibo', 'venta')),
    add column after_document_type text check (after_document_type in ('recibo', 'venta'));
