-- One purchase comprobante per Business and supplier (D-M1, D-M2).
--
-- The approval already reads for a second accepting or accepted purchase with
-- the same supplier RNC and NCF or e-CF
-- (argus.domain.business.actions.fiscal.require_distinct_fiscal_document);
-- this index refuses the write that read cannot see, as the sale index does
-- (20261021050000). Receipts with no RNC or no comprobante stay with the code
-- check on merchant, date, amount and currency.
--
-- The facts stay in resolution JSON. Three stored generated columns project
-- them the way the code normalizes them: kind as written; the RNC as its 9 or
-- 11 digits, with spaces and dashes removed, and only when some digit is not
-- zero (fiscal_identity.normalized_taxpayer_id); the number as e-CF before NCF
-- (an empty e-CF counts as none), trimmed, upper case, and only a B plus ten
-- digits or an E plus twelve (fiscal_identity.normalized_ncf).
--
-- Two purchases already accepted with one supplier and number would make the
-- index fail, so the migration stops first with a named error and changes
-- nothing. Resolve those rows by hand, then apply again.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

create function argus_private.business_rnc_digits(value text)
returns text
language sql
immutable
strict
set search_path = ''
as $$
    select case
        when value ~ '^[0-9 -]+$'
            and length(regexp_replace(value, '[ -]', '', 'g')) in (9, 11)
            and regexp_replace(value, '[ -]', '', 'g') ~ '[1-9]'
        then regexp_replace(value, '[ -]', '', 'g')
    end
$$;

create function argus_private.business_fiscal_number(ecf text, ncf text)
returns text
language sql
immutable
set search_path = ''
as $$
    select case
        when upper(btrim(coalesce(nullif(ecf, ''), ncf), E' \t\r\n'))
            ~ '^(B[0-9]{10}|E[0-9]{12})$'
        then upper(btrim(coalesce(nullif(ecf, ''), ncf), E' \t\r\n'))
    end
$$;

revoke all on function
    argus_private.business_rnc_digits(text),
    argus_private.business_fiscal_number(text, text)
    from public, anon, authenticated;

alter table public.financial_import_events
    add column business_kind text generated always as (
        resolution->'business'->'facts'->'kind'->>'value'
    ) stored,
    add column business_rnc text generated always as (
        argus_private.business_rnc_digits(
            resolution->'business'->'facts'->'fiscal'->'rnc'->>'value')
    ) stored,
    add column business_fiscal_number text generated always as (
        argus_private.business_fiscal_number(
            resolution->'business'->'facts'->'fiscal'->'ecf'->>'value',
            resolution->'business'->'facts'->'fiscal'->'ncf'->>'value')
    ) stored;

do $$
declare
    duplicated integer;
begin
    select count(*) into duplicated
    from (
        select owner_space_id, business_rnc, business_fiscal_number
        from public.financial_import_events
        where state in ('accepting', 'accepted')
            and owner_space_id is not null
            and business_kind is distinct from 'income'
            and business_rnc is not null
            and business_fiscal_number is not null
        group by 1, 2, 3
        having count(*) > 1
    ) duplicates;
    if duplicated > 0 then
        raise exception 'business_purchase_comprobante_duplicates_present: % Business, RNC and number group(s)',
            duplicated using errcode = 'P0001';
    end if;
end $$;

create unique index financial_import_events_purchase_comprobante_idx
    on public.financial_import_events (owner_space_id, business_rnc, business_fiscal_number)
    where state in ('accepting', 'accepted')
        and owner_space_id is not null
        and business_kind is distinct from 'income'
        and business_rnc is not null
        and business_fiscal_number is not null;

commit;
