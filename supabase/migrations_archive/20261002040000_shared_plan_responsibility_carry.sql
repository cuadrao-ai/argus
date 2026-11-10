-- Every definition writer carries the same canonical responsibility history.
begin;

create or replace function public.record_plan_definition_revision() returns trigger language plpgsql
 set search_path='' as $$
begin
 if TG_OP='UPDATE' and OLD.body=NEW.body then return NEW; end if;
 if TG_OP='UPDATE' and (NEW.body->>'version')::integer <= (OLD.body->>'version')::integer then
  raise exception 'canonical definition revision must advance' using errcode='23514';
 end if;
 insert into public.financial_plan_definition_revisions(kind,definition_id,owner_id,revision,body,actor_id)
 values(TG_ARGV[0],NEW.id,NEW.user_id,(NEW.body->>'version')::integer,NEW.body,
 nullif(current_setting('argus.plan_actor',true),'')::uuid);
 if TG_OP='UPDATE' then
  insert into public.financial_plan_responsibilities
   select kind,definition_id,owner_id,(NEW.body->>'version')::integer,
    membership_id,amount_minor,period,occurrence_id,schedule_id,agreed_date
   from public.financial_plan_responsibilities
   where kind=TG_ARGV[0] and definition_id=NEW.id and owner_id=NEW.user_id
    and revision=(OLD.body->>'version')::integer;
 end if;
 return NEW;
end $$;

commit;
