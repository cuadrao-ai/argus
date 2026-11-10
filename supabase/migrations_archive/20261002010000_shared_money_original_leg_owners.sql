-- A single logical activity retains every original leg owner and exact revision.
begin;
alter table public.financial_activity_memberships add column record_owner_id uuid;
update public.financial_activity_memberships set record_owner_id=user_id;
alter table public.financial_activity_memberships alter column record_owner_id set not null;
alter table public.financial_activity_memberships drop constraint financial_activity_membership_record_id_record_revision_us_fkey;
alter table public.financial_activity_memberships add constraint financial_activity_original_record_revision
 foreign key(record_id,record_revision,record_owner_id) references public.financial_record_revisions(record_id,revision,user_id)
 deferrable initially deferred;
create function public.default_activity_record_owner() returns trigger language plpgsql set search_path='' as $$
begin NEW.record_owner_id=coalesce(NEW.record_owner_id,NEW.user_id); return NEW; end $$;
create trigger activity_record_owner before insert on public.financial_activity_memberships
 for each row execute function public.default_activity_record_owner();
drop policy financial_activity_memberships_owner_select on public.financial_activity_memberships;
create policy financial_activity_memberships_owner_select on public.financial_activity_memberships for select to authenticated
 using(user_id=(select auth.uid()) and record_owner_id=(select auth.uid()) and ((select auth.jwt())->>'is_anonymous') is distinct from 'true');
create index financial_activity_leg_owner on public.financial_activity_memberships(record_owner_id,activity_id,activity_revision);

alter table public.financial_record_revisions add column reversal_of_owner_id uuid
 generated always as (case when details->>'reversal_of_activity_id' is not null
 then coalesce((details->>'reversal_of_owner_id')::uuid,user_id) end) stored;
alter table public.financial_record_revisions drop constraint financial_payment_return_owner_fk;
alter table public.financial_record_revisions add constraint financial_payment_return_original_owner_fk
 foreign key(reversal_of_activity_id,reversal_of_revision,reversal_of_owner_id)
 references public.financial_activity_revisions(activity_id,revision,user_id) deferrable initially deferred;

create function public.protect_foreign_activity_history() returns trigger language plpgsql set search_path='' as $$
begin
 if exists(select 1 from public.financial_activity_memberships where activity_id=OLD.id and record_owner_id<>OLD.user_id) then
  raise exception 'surviving original owners retain canonical activity history' using errcode='23514';
 end if;
 return OLD;
end $$;
create trigger retain_foreign_activity before delete on public.financial_activity_groups
 for each row execute function public.protect_foreign_activity_history();
revoke all on function public.default_activity_record_owner(),public.protect_foreign_activity_history() from public,anon,authenticated;
commit;
