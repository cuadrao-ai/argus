begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

create table public.business_lifecycle_commands (
    space_id uuid not null,
    owner_id uuid not null,
    idempotency_key text not null,
    action text not null,
    confirmation text,
    result_closed_at timestamptz,
    result_name text not null check (char_length(result_name) between 1 and 80),
    created_at timestamptz not null default now(),
    primary key (space_id, idempotency_key),
    constraint business_lifecycle_owner_fkey foreign key (space_id, owner_id)
        references public.spaces (id, created_by) on delete cascade,
    constraint business_lifecycle_key_check check (
        char_length(idempotency_key) between 1 and 200
        and char_length(btrim(idempotency_key)) > 0
    ),
    constraint business_lifecycle_action_check check (
        (action = 'close' and confirmation is not null
            and confirmation = result_name
            and result_closed_at is not null)
        or (action = 'reopen' and confirmation is null and result_closed_at is null)
    )
);

alter table public.business_lifecycle_commands enable row level security;
revoke all on public.business_lifecycle_commands from public, anon, authenticated, service_role;
grant select, insert on public.business_lifecycle_commands to service_role;

create index spaces_closed_business_idx on public.spaces (created_by, closed_at, id)
    where kind = 'business' and closed_at is not null;

comment on table public.business_lifecycle_commands is
    'Original owner close/reopen command results for scoped idempotency. '
    'Current state remains spaces.closed_at; grants remain unchanged. '
    'Retained until the owning Business is deleted.';

commit;
