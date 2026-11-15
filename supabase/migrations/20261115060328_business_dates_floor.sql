-- Fixed storage backstop. Rolling acceptance belongs to the application.
-- Existing rows are deliberately not scanned. Validation is a separate,
-- approved operation after a read-only count of older stored dates.
-- Prior values in immutable history remain evidence and can be copied during
-- a correction. Only the new value is constrained.
ALTER TABLE public.business_bank_lines
    ADD CONSTRAINT business_bank_lines_date_floor
    CHECK (occurred_on >= DATE '2000-01-01') NOT VALID;

ALTER TABLE public.business_bank_line_outcomes
    ADD CONSTRAINT business_bank_outcomes_date_floor
    CHECK (applied_settled_on >= DATE '2000-01-01') NOT VALID;

ALTER TABLE public.business_document_settlements
    ADD CONSTRAINT business_settlements_date_floor
    CHECK (settled_on >= DATE '2000-01-01') NOT VALID;

ALTER TABLE public.business_draft_revisions
    ADD CONSTRAINT business_draft_due_date_floor
    CHECK (after_due_on >= DATE '2000-01-01') NOT VALID;

-- Empty invoice fields are incomplete drafts, not dates.
ALTER TABLE public.business_invoice_revisions
    ADD CONSTRAINT business_invoice_dates_floor
    CHECK (
        NULLIF(data ->> 'issued_on', '')::date >= DATE '2000-01-01'
        AND NULLIF(data ->> 'due_on', '')::date >= DATE '2000-01-01'
    ) NOT VALID;

-- Read evidence may contain a wrong year. It stays available for review with
-- a null anchor; a person must correct it before approval. Other products'
-- import dates are outside this constraint.
ALTER TABLE public.financial_import_events
    ADD CONSTRAINT business_import_dates_floor
    CHECK (NOT (resolution ? 'business') OR (
        (anchor_on IS NULL OR anchor_on >= DATE '2000-01-01')
        AND ((resolution #>> '{business,facts,occurred_on,origin}') IN ('extracted', 'qr_decoded', 'matched')
             OR (resolution #>> '{business,facts,occurred_on,value}')::date >= DATE '2000-01-01')
        AND (resolution #>> '{business,due_on}')::date >= DATE '2000-01-01'
        AND (resolution #>> '{business,dgii,paid_on}')::date >= DATE '2000-01-01'
        AND (resolution #>> '{business,dgii,withheld_on}')::date >= DATE '2000-01-01'
    )) NOT VALID;
