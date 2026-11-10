-- business_bank_line_outcomes was born with the default service_role grant
-- (every privilege, delete and truncate included) and only granted select,
-- insert and update on top of it. Its guard trigger refuses a row delete but
-- not a truncate. Strip the inherited grant and give back only what the
-- outcomes store uses, as the other bank tables already have.

set local lock_timeout = '5s';
set local statement_timeout = '60s';

revoke all on public.business_bank_line_outcomes from service_role;
grant select, insert, update on public.business_bank_line_outcomes to service_role;
