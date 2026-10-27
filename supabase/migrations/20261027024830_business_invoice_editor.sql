begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

create table public.business_customers (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    version integer not null default 1 check(version>0),
    data jsonb not null check(octet_length(data::text)<=16384),
    archived boolean not null default false,
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    unique(id,space_id)
);
create table public.business_invoices (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    version integer not null default 1 check(version>0),
    operation_id uuid,
    issue_snapshot jsonb,
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp(),
    unique(id,space_id),
    unique(operation_id),
    foreign key(operation_id,space_id) references public.business_fiscal_operations(id,space_id),
    check((operation_id is null)=(issue_snapshot is null))
);
create table public.business_invoice_revisions (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    invoice_id uuid not null,
    version integer not null check(version>0),
    customer_id uuid,
    amounts jsonb,
    data jsonb not null check(octet_length(data::text)<=65536),
    created_at timestamptz not null default clock_timestamp(),
    unique(invoice_id,version),
    unique(id,space_id),
    foreign key(invoice_id,space_id) references public.business_invoices(id,space_id) on delete cascade,
    foreign key(customer_id,space_id) references public.business_customers(id,space_id)
);
create table public.business_invoice_commands (
    space_id uuid not null references public.spaces(id) on delete cascade,
    command_key text not null check(length(command_key) between 1 and 128),
    request_digest text not null check(request_digest ~ '^[a-f0-9]{64}$'),
    result jsonb not null check(octet_length(result::text)<=131072),
    primary key(space_id,command_key)
);
create index business_customers_page on public.business_customers(space_id,updated_at desc,id);
create index business_invoices_page on public.business_invoices(space_id,updated_at desc,id);
alter table public.business_customers enable row level security;
alter table public.business_invoices enable row level security;
alter table public.business_invoice_revisions enable row level security;
alter table public.business_invoice_commands enable row level security;
revoke all on public.business_customers,public.business_invoices,public.business_invoice_revisions,public.business_invoice_commands from public,anon,authenticated,service_role;
grant select,insert,update on public.business_customers,public.business_invoices to service_role;
grant select,insert on public.business_invoice_revisions,public.business_invoice_commands to service_role;

create function argus_private.business_invoice_immutable() returns trigger
language plpgsql set search_path='' as $$
begin
    if tg_table_name in ('business_invoice_revisions','business_invoice_commands') then
        raise exception 'invoice_revision_immutable' using errcode='23514';
    end if;
    if old.operation_id is not null and new is distinct from old then
        raise exception 'invoice_issue_immutable' using errcode='23514';
    end if;
    return new;
end;
$$;
create trigger business_invoice_revision_immutable before update on public.business_invoice_revisions
    for each row execute function argus_private.business_invoice_immutable();
create trigger business_invoice_command_immutable before update on public.business_invoice_commands
    for each row execute function argus_private.business_invoice_immutable();
create trigger business_invoice_issue_immutable before update on public.business_invoices
    for each row execute function argus_private.business_invoice_immutable();
revoke all on function argus_private.business_invoice_immutable() from public,anon,authenticated,service_role;
commit;
