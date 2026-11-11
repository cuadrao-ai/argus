-- Deleting a Business owner's auth user failed while the space held a bank
-- account. business_bank_accounts.account_id is a NO ACTION key to
-- financial_accounts. The auth.users cascade reaches financial_accounts (the
-- older user_id key) before spaces, so the key was checked while the binding
-- still existed. Check it at commit instead: by then the spaces cascade has
-- taken the binding and its imports, lines, suggestions and outcomes. Deleting
-- the account while the binding exists is still refused, at commit.

set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.business_bank_accounts
    alter constraint business_bank_accounts_account_id_fkey
    deferrable initially deferred;
