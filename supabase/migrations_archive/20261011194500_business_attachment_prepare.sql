alter table public.financial_document_extractions
    add column preparation_binding jsonb,
    add constraint financial_document_preparation_binding_shape check (
        preparation_binding is null or (
            jsonb_typeof(preparation_binding) = 'object'
            and preparation_binding->'schema_version' = '1'::jsonb
            and preparation_binding ?& array['binding_id','space_id','owner_id',
                'connection_id','source_sha256','actor','target','consent','captured_at']
            and jsonb_typeof(preparation_binding->'binding_id') = 'string'
            and jsonb_typeof(preparation_binding->'captured_at') = 'string'
            and jsonb_typeof(preparation_binding->'source_sha256') = 'string'
            and preparation_binding->>'connection_id' = connection_id::text
            and preparation_binding->>'owner_id' = user_id::text
            and preparation_binding->>'source_sha256' ~ '^[0-9a-f]{64}$'
            and preparation_binding->'consent' = 'true'::jsonb
            and jsonb_typeof(preparation_binding->'actor') = 'object'
            and preparation_binding->'actor'->>'actor_kind' = 'extractor'
            and jsonb_typeof(preparation_binding->'actor'->'display_name') = 'string'
            and jsonb_typeof(preparation_binding->'actor'->'issuer_display_name') = 'string'
            and (preparation_binding->'target' = 'null'::jsonb or (
                jsonb_typeof(preparation_binding->'target') = 'object'
                and preparation_binding->'target' ?& array['draft_id','version']
                and jsonb_typeof(preparation_binding->'target'->'version') = 'number'
                and preparation_binding->'target'->>'version' ~ '^[1-9][0-9]*$'
            ))
        ) is true
    );

create function argus_private.business_document_binding_guard()
returns trigger language plpgsql set search_path = '' as $$
declare
    b jsonb := new.preparation_binding;
begin
    if tg_op = 'UPDATE' and old.preparation_binding is not null
        and (new.preparation_binding is distinct from old.preparation_binding
            or new.connection_id is distinct from old.connection_id
            or new.user_id is distinct from old.user_id
            or (old.batch is not null and new.batch is distinct from old.batch)
            or (new.source_bytes is not null
                and new.source_bytes is distinct from old.source_bytes)) then
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
    if tg_op = 'INSERT' or old.preparation_binding is null then
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
        if b->'target' <> 'null'::jsonb and not exists (
            select 1 from public.financial_import_events e
            where e.id=(b->'target'->>'draft_id')::uuid
                and e.owner_space_id=(b->>'space_id')::uuid and e.user_id=new.user_id
                and e.version=(b->'target'->>'version')::integer
                and e.state='open' and e.resolution ? 'business'
            for share of e
        ) then
            raise exception 'business_preparation_target_invalid' using errcode = '23514';
        end if;
    end if;
    return new;
end;
$$;

create trigger business_document_binding_guard before insert or update
    on public.financial_document_extractions for each row
    execute function argus_private.business_document_binding_guard();

alter table public.business_action_receipts
    drop constraint business_action_receipts_unplanned_command,
    add constraint business_action_receipts_unplanned_command check (
        turn_key is not null or
        (command->>'action' in ('review_draft', 'approve_expense', 'capture_note',
            'approve_income', 'prepare_attachment')) is true
    ),
    add constraint business_action_receipts_attachment_extractor check (
        command->>'action' is distinct from 'prepare_attachment'
        or (
            actor->>'actor_kind'='extractor' and turn_key is null and action_index is null
            and command->'binding'->'actor'=actor
            and command->'binding'->>'space_id'=space_id::text
            and command->>'batch_sha256' ~ '^[0-9a-f]{64}$'
        ) is true
    );

create function argus_private.business_attachment_receipt_binding()
returns trigger language plpgsql set search_path = '' as $$
begin
    if new.command->>'action' = 'prepare_attachment' and not exists (
        select 1 from public.financial_document_extractions d
        where d.connection_id=(new.command->'binding'->>'connection_id')::uuid
            and d.user_id=(new.command->'binding'->>'owner_id')::uuid
            and d.preparation_binding=new.command->'binding'
            and d.batch is not null
        for share of d
    ) then
        raise exception 'business_preparation_receipt_binding_missing' using errcode = '23514';
    end if;
    return new;
end;
$$;

create trigger business_attachment_receipt_binding before insert
    on public.business_action_receipts for each row
    execute function argus_private.business_attachment_receipt_binding();

revoke all on function argus_private.business_document_binding_guard() from public, anon, authenticated;
revoke all on function argus_private.business_attachment_receipt_binding() from public, anon, authenticated;
