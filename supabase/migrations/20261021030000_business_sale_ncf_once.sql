-- One sale comprobante per Business. The approval already reads for a second
-- accepting or accepted sale with the same NCF or e-CF
-- (argus.domain.business.actions.fiscal.require_distinct_fiscal_document);
-- this index refuses the write the read cannot see. The number is normalized
-- the way that read normalizes it: e-CF before NCF, trimmed, upper case, and
-- only a B plus ten digits or an E plus twelve digits counts.
--
-- Two sales already approved with one number would make the index fail, so the
-- migration stops first with a named error and changes nothing. Resolve those
-- rows by hand, then apply again.
set lock_timeout = '5s';
set statement_timeout = '60s';

do $$
declare
  duplicated integer;
begin
  select count(*) into duplicated
  from (
    select owner_space_id,
           upper(btrim(coalesce(
             resolution->'business'->'facts'->'fiscal'->'ecf'->>'value',
             resolution->'business'->'facts'->'fiscal'->'ncf'->>'value'))) as number
    from public.financial_import_events
    where state in ('accepting', 'accepted')
      and owner_space_id is not null
      and resolution->'business'->'facts'->'kind'->>'value' = 'income'
      and upper(btrim(coalesce(
            resolution->'business'->'facts'->'fiscal'->'ecf'->>'value',
            resolution->'business'->'facts'->'fiscal'->'ncf'->>'value')))
          ~ '^(B[0-9]{10}|E[0-9]{12})$'
    group by 1, 2
    having count(*) > 1
  ) duplicates;
  if duplicated > 0 then
    raise exception 'business_sale_ncf_duplicates_present: % Business and number pair(s)',
      duplicated using errcode = 'P0001';
  end if;
end $$;

create unique index if not exists financial_import_events_sale_ncf_idx
  on public.financial_import_events (
    owner_space_id,
    (upper(btrim(coalesce(
      resolution->'business'->'facts'->'fiscal'->'ecf'->>'value',
      resolution->'business'->'facts'->'fiscal'->'ncf'->>'value'))))
  )
  where state in ('accepting', 'accepted')
    and owner_space_id is not null
    and resolution->'business'->'facts'->'kind'->>'value' = 'income'
    and upper(btrim(coalesce(
          resolution->'business'->'facts'->'fiscal'->'ecf'->>'value',
          resolution->'business'->'facts'->'fiscal'->'ncf'->>'value')))
        ~ '^(B[0-9]{10}|E[0-9]{12})$';

reset lock_timeout;
reset statement_timeout;
