begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

create table argus_private.business_saved_report_views (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces(id) on delete cascade,
    actor_id uuid not null references auth.users(id) on delete cascade,
    name text not null check(char_length(name) between 1 and 120 and char_length(btrim(name)) > 0),
    recipe jsonb not null check(jsonb_typeof(recipe) = 'object' and recipe->>'schema_version' = '1'),
    version bigint not null default 1 check(version > 0),
    created_at timestamptz not null default clock_timestamp(),
    updated_at timestamptz not null default clock_timestamp()
);
create index business_saved_report_views_actor_space_idx
    on argus_private.business_saved_report_views(actor_id,space_id,id);
alter table argus_private.business_saved_report_views enable row level security;
revoke all on argus_private.business_saved_report_views from public,anon,authenticated,service_role;
grant select,insert,update,delete on argus_private.business_saved_report_views to service_role;

create table argus_private.business_report_view_commands (
    space_id uuid not null references public.spaces(id) on delete cascade,
    actor_id uuid not null references auth.users(id) on delete cascade,
    command_key text not null check(char_length(command_key) between 1 and 200 and char_length(btrim(command_key)) > 0),
    command jsonb not null check(jsonb_typeof(command) = 'object'),
    result jsonb not null check(jsonb_typeof(result) = 'object'),
    created_at timestamptz not null default clock_timestamp(),
    primary key(space_id,actor_id,command_key)
);
alter table argus_private.business_report_view_commands enable row level security;
revoke all on argus_private.business_report_view_commands from public,anon,authenticated,service_role;
grant select,insert on argus_private.business_report_view_commands to service_role;

comment on table argus_private.business_saved_report_views is
    'Private validated query and column recipes. Current selected Business membership is checked by the service on every operation. No financial rows, report results or authority are stored.';
comment on table argus_private.business_report_view_commands is
    'Private idempotency receipts for preference changes. Account deletion cascades preference metadata only; financial custody and retained records do not change.';
commit;
