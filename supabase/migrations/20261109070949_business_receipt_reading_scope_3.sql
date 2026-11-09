-- Business document reading: scope version 3 names everything the reader
-- handles, invoices, receipts and PDFs. Scope 1 and 2 rows stay as they were,
-- the record of what each owner agreed to; the app reads them as off, so those
-- owners are asked again.
-- Additive: the scope check widens from 1 or 2 to 1, 2 or 3. No row changes.

begin;

alter table public.business_receipt_reading_consents
  drop constraint business_receipt_reading_consents_scope_version_check,
  add constraint business_receipt_reading_consents_scope_version_check
    check (scope_version in (1, 2, 3));

commit;
