-- Fixed storage backstop. Rolling acceptance belongs to the application.
-- A CHECK, even NOT VALID, would reject metadata-only writes to legacy rows.
-- AFTER row triggers see the actual INSERT or UPDATE chosen by an upsert and
-- compare individual date values. No stored rows are scanned or rewritten.
CREATE FUNCTION public.enforce_business_date_floor() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
    current_row jsonb := to_jsonb(NEW);
    previous_row jsonb;
    field_path text[];
    origin_path text[];
    field_name text;
    current_date_value date;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        previous_row := to_jsonb(OLD);
    END IF;
    FOREACH field_name IN ARRAY TG_ARGV LOOP
        field_path := string_to_array(field_name, ',');
        origin_path := NULL;
        -- Raw receipt evidence is allowed to retain a wrong year. Changing
        -- its origin to a person's assertion must still validate the date.
        IF field_path[array_length(field_path, 1)] = 'value' THEN
            origin_path := field_path[1:array_length(field_path, 1) - 1] || 'origin'::text;
            IF current_row #>> origin_path IN ('extracted', 'qr_decoded', 'matched') THEN
                CONTINUE;
            END IF;
        END IF;
        IF TG_OP = 'UPDATE'
            AND (current_row #>> field_path) IS NOT DISTINCT FROM (previous_row #>> field_path)
            AND (origin_path IS NULL OR
                 (current_row #>> origin_path) IS NOT DISTINCT FROM (previous_row #>> origin_path))
            -- Moving another product's row into Business is fresh input.
            AND (TG_TABLE_NAME <> 'financial_import_events' OR
                 previous_row -> 'resolution' ? 'business') THEN
            CONTINUE;
        END IF;
        current_date_value := NULLIF(current_row #>> field_path, '')::date;
        IF current_date_value < DATE '2000-01-01' THEN
            RAISE EXCEPTION 'business_date_before_storage_floor'
                USING ERRCODE = '23514', CONSTRAINT = TG_NAME,
                      TABLE = TG_TABLE_NAME, SCHEMA = TG_TABLE_SCHEMA,
                      COLUMN = field_path[1];
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$;

CREATE TRIGGER business_bank_lines_date_floor
AFTER INSERT OR UPDATE ON public.business_bank_lines
FOR EACH ROW EXECUTE FUNCTION public.enforce_business_date_floor('occurred_on');

CREATE TRIGGER business_bank_outcomes_date_floor
AFTER INSERT OR UPDATE ON public.business_bank_line_outcomes
FOR EACH ROW EXECUTE FUNCTION public.enforce_business_date_floor('applied_settled_on');

CREATE TRIGGER business_settlements_date_floor
AFTER INSERT OR UPDATE ON public.business_document_settlements
FOR EACH ROW EXECUTE FUNCTION public.enforce_business_date_floor('settled_on');

CREATE TRIGGER business_draft_due_date_floor
AFTER INSERT OR UPDATE ON public.business_draft_revisions
FOR EACH ROW EXECUTE FUNCTION public.enforce_business_date_floor('after_due_on');

CREATE TRIGGER business_invoice_dates_floor
AFTER INSERT OR UPDATE ON public.business_invoice_revisions
FOR EACH ROW EXECUTE FUNCTION public.enforce_business_date_floor('data,issued_on', 'data,due_on');

CREATE TRIGGER business_import_dates_floor
AFTER INSERT OR UPDATE ON public.financial_import_events
FOR EACH ROW WHEN (NEW.resolution ? 'business')
EXECUTE FUNCTION public.enforce_business_date_floor(
    'anchor_on', 'resolution,business,facts,occurred_on,value',
    'resolution,business,due_on', 'resolution,business,dgii,paid_on',
    'resolution,business,dgii,withheld_on'
);
