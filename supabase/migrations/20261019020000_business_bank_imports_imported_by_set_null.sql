-- A departed importer leaves the statement upload with the business.
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.business_bank_imports
    alter column imported_by drop not null;

alter table public.business_bank_imports
    drop constraint business_bank_imports_imported_by_fkey;

alter table public.business_bank_imports
    add constraint business_bank_imports_imported_by_fkey
    foreign key (imported_by) references auth.users (id) on delete set null;
