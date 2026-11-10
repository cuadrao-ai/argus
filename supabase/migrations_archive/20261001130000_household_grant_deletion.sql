-- Authorization edges may disappear with their membership. Financial ownership
-- and another owner's account/record history retain their existing deletion rules.
alter table public.household_account_grants
 drop constraint household_grant_owner_membership,
 drop constraint household_grant_recipient_membership;
alter table public.household_account_grants add constraint household_grant_owner_membership
 foreign key (owner_membership_id,household_id,owner_user_id)
 references public.household_members(id,household_id,user_id) on delete cascade;
alter table public.household_account_grants add constraint household_grant_recipient_membership
 foreign key (recipient_membership_id,household_id)
 references public.household_members(id,household_id) on delete cascade;
