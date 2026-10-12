-- The owner may move a receipt's preparation binding from a grant that is no
-- longer live to their current grant. That move is a turn-less ledger row by a
-- member, so the receipts check grows by one action, and the binding guard
-- admits exactly that move: same document, same source, old grant no longer
-- live, new binding held by a live grant of the space.

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment',
            'owner_grant', 'grant_access', 'invite_access', 'accept_invite', 'revoke_grant', 'revoke_invite',
            'rebind_attachment')) is true
    ),
    add constraint business_action_receipts_rebind_human check (
        command->>'action' is distinct from 'rebind_attachment'
        or (actor->>'actor_kind' = 'member' and turn_key is null and action_index is null
            and command->'binding'->>'space_id' = space_id::text) is true
    );

create or replace function argus_private.business_document_binding_guard()
returns trigger language plpgsql set search_path = '' as $$
declare
    b jsonb := new.preparation_binding;
    moved boolean := tg_op = 'UPDATE' and old.preparation_binding is not null
        and new.preparation_binding is distinct from old.preparation_binding;
begin
    if tg_op = 'UPDATE' and old.preparation_binding is not null
        and (new.connection_id is distinct from old.connection_id
            or new.user_id is distinct from old.user_id
            or (old.batch is not null and new.batch is distinct from old.batch)
            or (new.source_bytes is not null
                and new.source_bytes is distinct from old.source_bytes)) then
        raise exception 'business_preparation_binding_immutable' using errcode = '23514';
    end if;
    if moved and (
        b is null
        or b->>'source_sha256' is distinct from old.preparation_binding->>'source_sha256'
        or b->'target' is distinct from old.preparation_binding->'target'
        or exists (
            select 1 from public.business_client_grants g
            where g.id=(old.preparation_binding->'actor'->>'grant_id')::uuid
                and g.revoked_at is null
                and (g.expires_at is null or g.expires_at > clock_timestamp())
        )
    ) then
        raise exception 'business_preparation_binding_immutable' using errcode = '23514';
    end if;
    if b is null then
        return new;
    end if;
    if new.draft->>'sha256' is distinct from b->>'source_sha256'
        or (new.source_sha256 is not null
            and new.source_sha256 is distinct from b->>'source_sha256') then
        raise exception 'business_preparation_source_changed' using errcode = '23514';
    end if;
    if tg_op = 'INSERT' or old.preparation_binding is null or moved then
        perform (b->>'binding_id')::uuid, (b->>'captured_at')::timestamptz;
        if not exists (
            select 1 from public.financial_source_connections c
            join public.spaces s on s.id=c.owner_space_id
            join public.business_client_grants g on g.space_id=s.id
            join auth.users u on u.id=g.grantee_id
            where c.id=new.connection_id and c.user_id=new.user_id
                and c.owner_space_id=(b->>'space_id')::uuid
                and s.created_by=new.user_id and s.kind='business' and s.closed_at is null
                and c.status<>'disconnected'
                and g.id=(b->'actor'->>'grant_id')::uuid
                and g.grantee_id=(b->'actor'->>'actor_id')::uuid
                and g.issuer_id=(b->'actor'->>'issuer_id')::uuid
                and g.revoked_at is null
                and (g.expires_at is null or g.expires_at > clock_timestamp())
                and g.capabilities @> array['read','prepare']::text[]
                and coalesce(u.is_anonymous,false)=false
                and new.draft->'consent'='true'::jsonb
                and new.draft->'source_available'='true'::jsonb
                and (new.source_path is not null or new.source_bytes is not null)
            for share of c,s,g
        ) then
            raise exception 'business_preparation_binding_denied' using errcode = '23514';
        end if;
    end if;
    if (tg_op = 'INSERT' or old.preparation_binding is null)
        and b->'target' <> 'null'::jsonb and not exists (
            select 1 from public.financial_import_events e
            where e.id=(b->'target'->>'draft_id')::uuid
                and e.owner_space_id=(b->>'space_id')::uuid and e.user_id=new.user_id
                and e.version=(b->'target'->>'version')::integer
                and e.state='open' and e.resolution ? 'business'
            for share of e
        ) then
        raise exception 'business_preparation_target_invalid' using errcode = '23514';
    end if;
    return new;
end;
$$;
