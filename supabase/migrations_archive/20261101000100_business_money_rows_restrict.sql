-- Money rows and their evidence never cascade from a Business (#1446 Q1).
-- The eight keys from those tables to spaces become ON DELETE RESTRICT, so a
-- space delete is refused while a receipt, draft, record, account, turn,
-- command receipt or settlement still names it. Removal runs only through
-- the closed-Business purge (argus.domain.business.purge), which deletes
-- these rows itself, child first, before the space. Operational rows
-- (grants, invites, leases, outboxes, read states, consents) keep cascading.
--
-- A person who leaves never reaches these rows: a Business custodian's
-- auth.users delete is refused by business_auth_retention_guard until custody
-- moves to a placeholder (20261021140000), and every Business row's user_id is
-- that custodian. Each key keeps its name, columns, ON UPDATE NO ACTION and
-- deferrability, so the custody move's deferred-key list still names it.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.business_action_receipts
    drop constraint business_action_receipts_space_id_fkey,
    add constraint business_action_receipts_space_id_fkey
        foreign key (space_id) references public.spaces (id) on delete restrict;

alter table public.business_turns
    drop constraint business_turns_space_id_fkey,
    add constraint business_turns_space_id_fkey
        foreign key (space_id) references public.spaces (id) on delete restrict;

alter table public.business_sources
    drop constraint business_sources_space_id_fkey,
    add constraint business_sources_space_id_fkey
        foreign key (space_id) references public.spaces (id) on delete restrict;

alter table public.business_document_settlements
    drop constraint business_document_settlements_space_id_owner_id_fkey,
    add constraint business_document_settlements_space_id_owner_id_fkey
        foreign key (space_id, owner_id) references public.spaces (id, created_by)
        on delete restrict deferrable initially immediate;

alter table public.financial_import_events
    drop constraint financial_import_events_owner_space_fkey,
    add constraint financial_import_events_owner_space_fkey
        foreign key (owner_space_id, user_id) references public.spaces (id, created_by)
        on delete restrict deferrable initially immediate;

alter table public.financial_source_connections
    drop constraint financial_source_connections_owner_space_fkey,
    add constraint financial_source_connections_owner_space_fkey
        foreign key (owner_space_id, user_id) references public.spaces (id, created_by)
        on delete restrict deferrable initially immediate;

alter table public.financial_records
    drop constraint financial_records_owner_funded_scope_fk,
    add constraint financial_records_owner_funded_scope_fk
        foreign key (owner_space_id, user_id) references public.spaces (id, created_by)
        on delete restrict deferrable initially immediate;

alter table public.financial_accounts
    drop constraint financial_accounts_owner_space_fkey,
    add constraint financial_accounts_owner_space_fkey
        foreign key (owner_space_id, user_id) references public.spaces (id, created_by)
        on delete restrict deferrable initially immediate;

-- Sources, draft revisions and settlements refuse a direct delete and only
-- went with a parent's cascade (business_evidence_immutable). The space
-- cascade is gone, so the purge marks the space it is removing, on its own
-- postgres connection and for its transaction only, and these guards let that
-- delete through. Cascades from an event, a connection or an activity still
-- pass as before. Nothing else may delete evidence.
create function argus_private.business_purge_marked(space uuid)
returns boolean
language sql
stable
set search_path = ''
as $$
    select current_user = 'postgres'
        and current_setting('argus.business_purge_space', true) = space::text
$$;
-- The guards run with the caller's rights, so the service role must be able
-- to evaluate the mark (always false for it) and reach the refusal.
revoke all on function argus_private.business_purge_marked(uuid)
    from public, anon, authenticated;
grant execute on function argus_private.business_purge_marked(uuid) to service_role;

create or replace function argus_private.business_immutable_evidence()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if current_user = 'postgres' and tg_op = 'UPDATE' then
        if argus_private.business_custody_identity_change(tg_table_name, to_jsonb(old), to_jsonb(new)) then
            return new;
        end if;
    end if;
    if tg_op = 'DELETE'
        and (pg_trigger_depth() > 1 or argus_private.business_purge_marked(old.space_id)) then
        return old;
    end if;
    raise exception 'business_evidence_immutable' using errcode = '23514';
end;
$$;

create or replace function argus_private.business_settlement_delete_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if tg_op = 'DELETE'
        and (pg_trigger_depth() > 1 or argus_private.business_purge_marked(old.space_id)) then
        return old;
    end if;
    raise exception 'business_evidence_immutable' using errcode = '23514';
end;
$$;

commit;
