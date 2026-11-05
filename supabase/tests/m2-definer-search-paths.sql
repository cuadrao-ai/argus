-- Synthetic records exist only inside this rolled-back local test transaction.
BEGIN;
SET LOCAL statement_timeout = '60s';
SET LOCAL plpgsql.check_asserts = on;
DO $test$
DECLARE
  owner_id uuid := gen_random_uuid();
  guest_id uuid := gen_random_uuid();
  outsider_id uuid := gen_random_uuid();
  household_id uuid := gen_random_uuid();
  account_id uuid;
  conversation_id uuid;
  feedback_id uuid := gen_random_uuid();
  result jsonb;
  replay jsonb;
  workspace public.guest_workspaces;
  conversation public.conversations;
  window_row record;
BEGIN
  INSERT INTO auth.users(id,email,is_anonymous) VALUES
    (owner_id,'m2-owner@example.test',false),
    (outsider_id,'m2-outsider@example.test',false),
    (guest_id,null,true);
  INSERT INTO public.profiles(id,email) VALUES
    (owner_id,'m2-owner@example.test'),
    (outsider_id,'m2-outsider@example.test'),(guest_id,null);
  BEGIN
    UPDATE public.profiles SET email='wrong@example.test' WHERE id=owner_id;
    RAISE EXCEPTION 'profile identity mismatch accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  INSERT INTO public.guest_workspaces(user_id,created_at,expires_at)
    VALUES(guest_id,now(),now()+interval '1 hour');
  ASSERT (SELECT expires_at=created_at+interval '7 days'
    FROM public.guest_workspaces WHERE user_id=guest_id);
  BEGIN
    UPDATE public.guest_workspaces SET expires_at=now() WHERE user_id=guest_id;
    RAISE EXCEPTION 'guest expiry mutation accepted';
  EXCEPTION WHEN check_violation THEN NULL;
  END;

  EXECUTE 'SET LOCAL ROLE service_role';
  result := public.create_financial_account(owner_id,'m2-create','m2-hash','cash','DOP',
    null,10000,12345,now(),'UTC',null);
  ASSERT result->>'decision'='created';
  account_id := (result->>'account_id')::uuid;
  replay := public.create_financial_account(owner_id,'m2-create','m2-hash','cash','DOP',
    null,10000,12345,now(),'UTC',null);
  ASSERT replay->>'decision'='replay' AND replay->>'account_id'=account_id::text;
  ASSERT public.create_financial_account(owner_id,'m2-create','other','cash','DOP',
    null,10000,null,null,null,null)->>'decision'='conflict';
  ASSERT public.create_financial_account(guest_id,'guest','hash','cash','DOP',
    null,10000,null,null,null,null)->>'decision'='registered_required';
  ASSERT public.write_financial_opening(owner_id,account_id,1,99,23456,now(),'UTC',
    'correction')->>'decision'='stale';
  ASSERT public.write_financial_opening(outsider_id,account_id,1,1,23456,now(),'UTC',
    'correction')->>'decision'='not_found';
  ASSERT public.write_financial_opening(guest_id,account_id,1,1,23456,now(),'UTC',
    'correction')->>'decision'='registered_required';
  result := public.write_financial_opening(owner_id,account_id,1,1,23456,now(),'UTC',
    'correction');
  ASSERT result->>'decision'='written' AND result->>'revision'='2';
  ASSERT (SELECT amount_minor=23456 FROM public.financial_record_revisions
    WHERE record_id=(result->>'record_id')::uuid AND revision=2);
  ASSERT (SELECT count(*)=2 FROM public.financial_record_revisions
    WHERE record_id=(result->>'record_id')::uuid);

  EXECUTE 'RESET ROLE';
  INSERT INTO public.households(id,admin_user_id,created_by)
    VALUES(household_id,owner_id,owner_id);
  INSERT INTO public.household_members(household_id,user_id)
    VALUES(household_id,owner_id);
  CREATE TEMP TABLE household_members(household_id uuid,user_id uuid,left_at timestamptz);
  INSERT INTO pg_temp.household_members VALUES(household_id,outsider_id,null);
  ASSERT public.is_active_household_member(household_id,owner_id);
  ASSERT NOT public.is_active_household_member(household_id,outsider_id);
  EXECUTE 'SET LOCAL ROLE authenticated';
  ASSERT public.is_active_household_member(household_id,owner_id);
  EXECUTE 'RESET ROLE';
  UPDATE public.household_members SET left_at=now() WHERE user_id=owner_id;
  ASSERT NOT public.is_active_household_member(household_id,owner_id);

  SELECT * INTO window_row FROM argus_private.validated_usage_windows(
    owner_id,'feedback','[{"period":"day","limit":2}]',now());
  ASSERT window_row.limit_count=2 AND NOT window_row.guest_session;
  result := public.create_feedback_settling_usage(feedback_id,owner_id,'general',
    'Synthetic M2 feedback','{}','feedback','[{"period":"day","limit":2}]');
  ASSERT result->>'decision'='accepted' AND result->>'replayed'='false';
  result := public.create_feedback_settling_usage(feedback_id,owner_id,'general',
    'Synthetic M2 feedback','{}','feedback','[{"period":"day","limit":2}]');
  ASSERT result->>'replayed'='true';
  result := public.admit_backtest_job(owner_id,'backtests.run','m2','hash','hash','{}',
    'running',null,null,null,'{}',2,2,4,4,'[{"period":"day","limit":2}]');
  ASSERT result->>'decision'='admitted';
  ASSERT public.finalize_direct_backtest_success(owner_id,gen_random_uuid(),'none',
    '{}','{}','{}','{}') IS NULL;
  ASSERT NOT public.delete_withheld_backtest_result(owner_id,gen_random_uuid());

  ASSERT public.claim_guest_compute_usage('m2-visitor','m2-session','compute',1,1)
    ->>'available'='true';
  ASSERT public.claim_guest_compute_usage('m2-visitor','m2-session','compute',1,1)
    ->>'visitor_exhausted'='true';
  ASSERT public.claim_registered_compute_usage('m2-account','compute',1)
    ->>'available'='true';
  ASSERT public.claim_registered_compute_usage('m2-account','compute',1)
    ->>'available'='false';
  result := public.claim_research_usage('m2-guest','research','m2-global',2,1);
  ASSERT result->>'available'='true';
  ASSERT public.claim_research_usage('m2-guest','research','m2-global',2,1)
    ->>'guest_exhausted'='true';
  ASSERT public.release_research_usage('m2-guest','research','m2-global',
    (result->>'period_start')::timestamptz)->>'released'='true';
  ASSERT public.release_research_usage('m2-guest','research','m2-global',
    (result->>'period_start')::timestamptz)->>'released'='false';
  ASSERT public.settle_visitor_usage('m2-settle','other',jsonb_build_array(
    jsonb_build_object('period','day','limit',2,'period_start',date_trunc('day',now()),
    'period_end',date_trunc('day',now())+interval '1 day')))->>'settled'='true';
  ASSERT public.claim_guest_funnel_milestone('m2-subject','opened',now()+interval '1 day');
  ASSERT NOT public.claim_guest_funnel_milestone('m2-subject','opened',now()+interval '1 day');
  ASSERT public.purge_expired_guest_funnel_milestones(now()+interval '2 days')=1;
  ASSERT public.purge_expired_visitor_usage(now()+interval '2 days')=6;

  INSERT INTO public.conversations(user_id,title) VALUES(guest_id,'M2')
    RETURNING id INTO conversation_id;
  workspace := public.bind_guest_conversation(guest_id,conversation_id);
  ASSERT workspace.conversation_id=conversation_id;
  conversation := public.replace_empty_guest_conversation(guest_id,'Empty replacement',
    'user_renamed','en');
  ASSERT conversation.title='Empty replacement';
  conversation := public.replace_guest_conversation(guest_id,'Replacement','user_renamed','en');
  ASSERT conversation.title='Replacement';
END;
$test$;
ROLLBACK;
