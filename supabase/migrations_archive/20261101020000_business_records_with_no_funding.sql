-- A Business purchase or sale may be recorded with no account and no funding.
--
-- Approval needs no account and no payment answer (cuadrao-pilot-review-spec).
-- The owner-funds shape held only an expense with funding 'owner_funds'. This
-- check keeps that shape and adds a null funding on an expense or an income.
-- Null means nobody stated how it was paid; no word stands for it, so no reader
-- can mistake it for a fact. A refund, a transfer and any other kind keep their
-- account, and income still cannot be funded by the owner.
--
-- Every row the old check admits passes this one, so the old API writes as
-- before. An API from before this change does not read the new rows.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.financial_records
    drop constraint financial_records_funding_shape,
    add constraint financial_records_funding_shape check (
        (account_id is not null and owner_space_id is null and funding is null and currency is null)
        or (account_id is null and owner_space_id is not null
            and currency is not null and currency ~ '^[A-Z]{3}$'
            and ((record_kind = 'expense' and (funding is null or funding = 'owner_funds'))
                or (record_kind = 'income' and funding is null)))
    );

commit;
