-- Transacciones outcomes. A bank line has at most one live outcome: matched to
-- one recorded document, or marked as needing no comprobante. Undoing an
-- outcome ends it; the row stays as history. A document holds at most one live
-- match. A match stores the document's settlement before it and the settlement
-- it wrote, and while the match is live the settlement can only be that one.
-- Retention follows the Business record (working assumption ten years).

set local lock_timeout = '5s';
set local statement_timeout = '60s';

create table public.business_bank_line_outcomes (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete cascade,
    line_id uuid not null,
    kind text not null check (kind in ('match', 'no_receipt')),
    target_kind text check (target_kind in ('receipt', 'venta')),
    target_id uuid,
    reason text check (
        reason in ('cargo_banco', 'entre_cuentas', 'compra_informal', 'personal')
    ),
    prior_status text check (prior_status in ('pendiente', 'cobrado', 'pagado')),
    prior_settled_on date,
    prior_payment_method text check (
        prior_payment_method in ('efectivo', 'transferencia', 'tarjeta', 'credito', 'otro')
    ),
    applied_status text check (applied_status in ('cobrado', 'pagado')),
    applied_settled_on date,
    applied_payment_method text check (
        applied_payment_method in ('efectivo', 'transferencia', 'tarjeta', 'credito', 'otro')
    ),
    created_by uuid references auth.users (id) on delete set null,
    created_at timestamptz not null default clock_timestamp(),
    create_key text not null check (char_length(create_key) between 1 and 128),
    ended_by uuid references auth.users (id) on delete set null,
    ended_at timestamptz,
    end_key text check (char_length(end_key) between 1 and 128),
    foreign key (line_id, space_id)
        references public.business_bank_lines (id, space_id) on delete cascade,
    unique (line_id, create_key),
    check ((ended_at is null) = (end_key is null)),
    check (
        (
            kind = 'match'
            and target_kind is not null
            and target_id is not null
            and reason is null
            and (
                (target_kind = 'receipt' and applied_status = 'pagado')
                or (target_kind = 'venta' and applied_status = 'cobrado')
            )
            and applied_settled_on is not null
            and applied_payment_method is not null
            and (
                (prior_status = 'pendiente'
                    and prior_settled_on is null
                    and prior_payment_method is null)
                or (prior_status in ('cobrado', 'pagado')
                    and prior_settled_on is not null
                    and prior_payment_method is not null)
            )
        )
        or (
            kind = 'no_receipt'
            and reason is not null
            and target_kind is null
            and target_id is null
            and prior_status is null
            and prior_settled_on is null
            and prior_payment_method is null
            and applied_status is null
            and applied_settled_on is null
            and applied_payment_method is null
        )
    )
);

create unique index business_bank_line_outcomes_live_line_idx
    on public.business_bank_line_outcomes (line_id)
    where ended_at is null;
create unique index business_bank_line_outcomes_live_document_idx
    on public.business_bank_line_outcomes (space_id, target_id)
    where ended_at is null and kind = 'match';
create index business_bank_line_outcomes_space_idx
    on public.business_bank_line_outcomes (space_id, created_at);
create index business_bank_line_outcomes_created_by_idx
    on public.business_bank_line_outcomes (created_by);
create index business_bank_line_outcomes_ended_by_idx
    on public.business_bank_line_outcomes (ended_by);

comment on table public.business_bank_line_outcomes is
    'One live outcome per bank line and one live match per document. Ending an outcome keeps the row. Keep with the Business record. No delete API.';
comment on column public.business_bank_line_outcomes.prior_status is
    'The document settlement before this match. Undoing the match writes it back.';
comment on column public.business_bank_line_outcomes.applied_status is
    'The settlement this match wrote. It stays the settlement while the match is live.';

-- Account deletion nulls created_by and ended_by through their foreign keys,
-- and space or line removal cascades. Those are the only changes from inside
-- another statement. A direct change may only end a live outcome once.
create function argus_private.business_bank_line_outcomes_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if tg_op = 'DELETE' then
        if pg_trigger_depth() > 1 then
            return old;
        end if;
        raise exception 'business_evidence_immutable' using errcode = '23514';
    end if;
    if pg_trigger_depth() > 1
        and (to_jsonb(new) - 'created_by' - 'ended_by')
            = (to_jsonb(old) - 'created_by' - 'ended_by')
        and (new.created_by is null or new.created_by = old.created_by)
        and (new.ended_by is null or new.ended_by = old.ended_by)
    then
        return new;
    end if;
    if old.ended_at is null
        and new.ended_at is not null
        and (to_jsonb(new) - 'ended_at' - 'ended_by' - 'end_key')
            = (to_jsonb(old) - 'ended_at' - 'ended_by' - 'end_key')
    then
        return new;
    end if;
    raise exception 'business_evidence_immutable' using errcode = '23514';
end;
$$;

create trigger business_bank_line_outcomes_guard
    before update or delete on public.business_bank_line_outcomes
    for each row execute function argus_private.business_bank_line_outcomes_guard();

-- While a document has a live match, its settlement is the one the match wrote.
-- The match path ends the match before it restores the prior settlement.
create function argus_private.business_settlement_follows_match()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    live record;
begin
    select o.applied_status, o.applied_settled_on, o.applied_payment_method
    into live
    from public.business_bank_line_outcomes o
    where o.space_id = new.space_id
        and o.target_id = new.activity_id
        and o.kind = 'match'
        and o.ended_at is null;
    if found and (new.status, new.settled_on, new.payment_method)
        is distinct from
        (live.applied_status, live.applied_settled_on, live.applied_payment_method)
    then
        raise exception 'business_document_matched' using errcode = '23514';
    end if;
    return new;
end;
$$;

create trigger business_document_settlement_follows_match
    before insert or update on public.business_document_settlements
    for each row execute function argus_private.business_settlement_follows_match();

-- Matches decided before this table become live outcomes. The settlement they
-- now own is written with a revision row, as a person's settle would be.
alter table public.business_bank_suggestions
    disable trigger business_bank_suggestions_guard;

create temporary table decided as
select s.space_id, s.line_id, s.target_kind, s.target_id::uuid as target_id,
    s.decided_by, s.decided_at, s.decision_key, l.occurred_on,
    sp.created_by as owner_id,
    case fa.type
        when 'checking' then 'transferencia'
        when 'savings' then 'transferencia'
        when 'credit_card' then 'tarjeta'
        when 'cash' then 'efectivo'
        else 'otro'
    end as method,
    case s.target_kind when 'receipt' then 'pagado' else 'cobrado' end as applied,
    coalesce(st.status, 'pendiente') as prior_status,
    st.settled_on as prior_settled_on,
    st.payment_method as prior_payment_method
from public.business_bank_suggestions s
join public.business_bank_lines l on l.id = s.line_id
join public.business_bank_accounts ba on ba.id = l.bank_account_id
join public.financial_accounts fa on fa.id = ba.account_id
join public.spaces sp on sp.id = s.space_id
left join public.business_document_settlements st
    on st.space_id = s.space_id and st.activity_id = s.target_id::uuid
where s.status = 'confirmed';

insert into public.business_bank_line_outcomes (
    space_id, line_id, kind, target_kind, target_id,
    prior_status, prior_settled_on, prior_payment_method,
    applied_status, applied_settled_on, applied_payment_method,
    created_by, created_at, create_key
)
select space_id, line_id, 'match', target_kind, target_id,
    prior_status, prior_settled_on, prior_payment_method,
    applied, occurred_on, method, decided_by, decided_at, decision_key
from decided;

insert into public.business_document_settlement_revisions (
    space_id, activity_id, actor_id,
    previous_status, previous_settled_on, previous_payment_method
)
select space_id, target_id, decided_by,
    prior_status, prior_settled_on, prior_payment_method
from decided
where (prior_status, prior_settled_on, prior_payment_method)
    is distinct from (applied, occurred_on, method);

insert into public.business_document_settlements (
    space_id, owner_id, activity_id, document_kind,
    status, settled_on, payment_method
)
select space_id, owner_id, target_id,
    case target_kind when 'receipt' then 'receipt' else 'invoice' end,
    applied, occurred_on, method
from decided
where (prior_status, prior_settled_on, prior_payment_method)
    is distinct from (applied, occurred_on, method)
on conflict (space_id, activity_id) do update
    set status = excluded.status,
        settled_on = excluded.settled_on,
        payment_method = excluded.payment_method,
        updated_at = clock_timestamp();

drop table decided;

update public.business_bank_suggestions
set status = 'pending', decided_at = null, decided_by = null, decision_key = null
where status = 'confirmed';

alter table public.business_bank_suggestions
    enable trigger business_bank_suggestions_guard;

drop index public.business_bank_suggestions_one_confirmed_idx;
alter table public.business_bank_suggestions
    drop constraint business_bank_suggestions_status_check;
alter table public.business_bank_suggestions
    add constraint business_bank_suggestions_status_check
    check (status in ('pending', 'declined'));

comment on table public.business_bank_suggestions is
    'One offer per line and target. Pending or declined. A declined row keeps that pair out of later offers. Accepting an offer adds a live business_bank_line_outcomes match; the offer row does not change. Score parts are the historical offer. Keep 10 years.';

alter table public.business_bank_line_outcomes enable row level security;
revoke all on public.business_bank_line_outcomes from public, anon, authenticated;
grant select, insert, update on public.business_bank_line_outcomes to service_role;

revoke all on function argus_private.business_bank_line_outcomes_guard(),
    argus_private.business_settlement_follows_match()
    from public, anon, authenticated;
