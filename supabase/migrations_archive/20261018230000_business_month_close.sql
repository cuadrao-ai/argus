-- Month close settlements. One row annotates one recorded activity in one
-- Business. Amounts, ITBIS, RNC, and the fiscal number stay on the activity
-- and its draft. This table stores only how that document was settled.

begin;

create table public.business_document_settlements (
    space_id uuid not null,
    owner_id uuid not null,
    activity_id uuid not null,
    document_kind text not null check (document_kind in ('invoice', 'receipt')),
    status text not null check (status in ('pendiente', 'cobrado', 'pagado')),
    settled_on date,
    payment_method text,
    updated_at timestamptz not null default clock_timestamp(),
    primary key (space_id, activity_id),
    foreign key (space_id, owner_id)
        references public.spaces (id, created_by) on delete cascade,
    foreign key (activity_id, owner_id)
        references public.financial_activity_groups (id, user_id) on delete cascade,
    check (
        (document_kind = 'invoice' and status in ('pendiente', 'cobrado'))
        or (document_kind = 'receipt' and status in ('pendiente', 'pagado'))
    ),
    check (
        (status = 'pendiente' and settled_on is null and payment_method is null)
        or (
            status in ('cobrado', 'pagado')
            and settled_on is not null
            and payment_method is not null
        )
    ),
    check (
        payment_method is null
        or payment_method in ('efectivo', 'transferencia', 'tarjeta', 'credito', 'otro')
    )
);
create index business_document_settlements_status_idx
    on public.business_document_settlements (space_id, status);

create table public.business_document_settlement_revisions (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null,
    activity_id uuid not null,
    actor_id uuid references auth.users (id) on delete set null,
    previous_status text not null check (previous_status in ('pendiente', 'cobrado', 'pagado')),
    previous_settled_on date,
    previous_payment_method text,
    created_at timestamptz not null default clock_timestamp(),
    -- Deferred so account deletion can blank actor_id before the settlement
    -- cascade removes this parent. An immediate check fires after the
    -- activity is already gone and rejects the blanking.
    foreign key (space_id, activity_id)
        references public.business_document_settlements (space_id, activity_id)
        on delete cascade
        deferrable initially deferred,
    check (
        previous_payment_method is null
        or previous_payment_method in (
            'efectivo', 'transferencia', 'tarjeta', 'credito', 'otro'
        )
    ),
    check (
        (previous_status = 'pendiente'
            and previous_settled_on is null
            and previous_payment_method is null)
        or (
            previous_status in ('cobrado', 'pagado')
            and previous_settled_on is not null
            and previous_payment_method is not null
        )
    )
);
create index business_document_settlement_revisions_activity_idx
    on public.business_document_settlement_revisions (space_id, activity_id, created_at);

-- Account deletion nulls actor_id through the foreign key. That is an update
-- fired from inside the delete, and it is the only update this history allows.
-- A direct edit or delete is still refused. A direct delete of the settlement
-- is refused the same way; the space and activity cascades stay allowed.
create function argus_private.business_settlement_revision_immutable()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if pg_trigger_depth() > 1 then
        if tg_op = 'DELETE' then
            return old;
        end if;
        if old.actor_id is not null
            and new.actor_id is null
            and (to_jsonb(new) - 'actor_id') = (to_jsonb(old) - 'actor_id') then
            return new;
        end if;
    end if;
    raise exception 'business_evidence_immutable' using errcode = '23514';
end;
$$;

create function argus_private.business_settlement_delete_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if tg_op = 'DELETE' and pg_trigger_depth() > 1 then
        return old;
    end if;
    raise exception 'business_evidence_immutable' using errcode = '23514';
end;
$$;

create trigger business_document_settlement_revision_immutable
    before update or delete on public.business_document_settlement_revisions
    for each row execute function argus_private.business_settlement_revision_immutable();

create trigger business_document_settlement_delete_guard
    before delete on public.business_document_settlements
    for each row execute function argus_private.business_settlement_delete_guard();

revoke all on function argus_private.business_settlement_revision_immutable(),
    argus_private.business_settlement_delete_guard()
    from public, anon, authenticated;

alter table public.business_document_settlements enable row level security;
alter table public.business_document_settlement_revisions enable row level security;
revoke all on public.business_document_settlements,
    public.business_document_settlement_revisions
    from public, anon, authenticated;
grant select, insert, update, delete
    on public.business_document_settlements to service_role;
grant select, insert
    on public.business_document_settlement_revisions to service_role;

commit;
