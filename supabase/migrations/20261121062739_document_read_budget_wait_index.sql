-- The document worker's read-resume pass looks, every ten minutes, for
-- receipts a spent Business read budget left saved and unread. This index
-- holds only those rows, so the pass reads nothing while none wait.
create index financial_document_extractions_refused_idx
    on public.financial_document_extractions (created_at, connection_id)
    where (draft->>'status') = 'saved'
      and (draft->>'error_code') in ('business_read_budget_day', 'business_read_budget_month');
