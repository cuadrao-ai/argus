begin;
set local lock_timeout='5s';
set local statement_timeout='60s';

create table argus_private.business_custody_reservations (
    space_id uuid primary key references public.spaces(id) on delete restrict,
    custodian_id uuid not null unique,
    deleted_actor_id uuid not null unique,
    created_at timestamptz not null default clock_timestamp(),
    auth_ready_at timestamptz,
    check(custodian_id<>deleted_actor_id)
);
create table argus_private.business_custody_objects (
    space_id uuid not null references argus_private.business_custody_reservations(space_id) on delete restrict,
    source_path text not null,
    destination_path text not null,
    sha256 text not null check(sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint not null check(size_bytes>=0),
    media_type text not null,
    created_at timestamptz not null default clock_timestamp(),
    verified_at timestamptz,
    primary key(space_id,source_path)
);
create index business_custody_destination_idx on argus_private.business_custody_objects(destination_path);
alter table argus_private.business_custody_reservations enable row level security;
alter table argus_private.business_custody_objects enable row level security;
revoke all on argus_private.business_custody_reservations,argus_private.business_custody_objects from public,anon,authenticated,service_role;
grant select,insert,update on argus_private.business_custody_reservations,argus_private.business_custody_objects to service_role;
comment on table argus_private.business_custody_reservations is
    'One reserved banned custodian and anonymous historical actor per Business. No departed-person key. Copy preparation alone never authorizes record movement or deletion.';
comment on table argus_private.business_custody_objects is
    'Tracked destination before external copy. Original and rebuilt hashes are independent. Source paths contain in-flight identity and must be cleared by the future deletion completion writer. RESTRICT prevents silently losing the purge plan.';
commit;
