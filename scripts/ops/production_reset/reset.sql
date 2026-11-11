BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';
SET LOCAL search_path = pg_catalog, pg_temp;

DO $precheck$
DECLARE scheduled_jobs boolean;
BEGIN
  IF current_database() <> 'postgres' OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'Reset requires database postgres and role postgres';
  END IF;
  IF to_regclass('public.cuadrao_reset_marker') IS NULL THEN
    RAISE EXCEPTION 'Missing independently approved database project marker';
  END IF;
  IF (SELECT count(*) FROM public.cuadrao_reset_marker) <> 1
      OR (SELECT project_ref FROM public.cuadrao_reset_marker) IS DISTINCT FROM 'lgdhvepyrzbnscqssgqq' THEN
    RAISE EXCEPTION 'Wrong independently approved database project marker';
  END IF;
  IF EXISTS (SELECT FROM storage.buckets) OR EXISTS (SELECT FROM storage.objects) THEN
    RAISE EXCEPTION 'Storage buckets and objects must be empty';
  END IF;
  IF to_regclass('cron.job') IS NOT NULL THEN
    EXECUTE 'SELECT EXISTS (SELECT FROM cron.job)' INTO scheduled_jobs;
    IF scheduled_jobs THEN RAISE EXCEPTION 'Scheduled jobs must be removed before reset'; END IF;
  END IF;
  IF EXISTS (
    SELECT FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE n.nspname = 'argus_private'
  ) OR EXISTS (
    SELECT FROM pg_depend member JOIN pg_depend ns
      ON ns.classid = member.classid AND ns.objid = member.objid
    JOIN pg_namespace n ON ns.refclassid = 'pg_namespace'::regclass AND ns.refobjid = n.oid
    WHERE member.refclassid = 'pg_extension'::regclass AND member.deptype IN ('e', 'x')
      AND n.nspname = 'argus_private'
  ) THEN
    RAISE EXCEPTION 'Extension objects in argus_private require separate review';
  END IF;
END
$precheck$;

CREATE TEMP TABLE reset_protected (classid oid, objid oid, objsubid integer,
                                  PRIMARY KEY (classid, objid, objsubid)) ON COMMIT DROP;
WITH RECURSIVE protected(classid, objid, objsubid) AS (
  SELECT 'pg_extension'::regclass::oid, oid, 0 FROM pg_extension
  UNION
  SELECT d.classid, d.objid, d.objsubid FROM pg_depend d JOIN protected p
    ON d.refclassid = p.classid AND d.refobjid = p.objid
      AND (p.objsubid = 0 OR d.refobjsubid = p.objsubid)
  WHERE d.deptype IN ('e', 'x', 'i', 'a', 'P', 'S')
)
INSERT INTO reset_protected SELECT * FROM protected;

CREATE TEMP TABLE reset_auth_triggers (oid oid PRIMARY KEY) ON COMMIT DROP;
DO $auth_triggers$
DECLARE candidate_trigger record;
BEGIN
  FOR candidate_trigger IN
    SELECT t.*, p.proname, p.pronargs, n.nspname FROM pg_trigger t
    JOIN pg_proc p ON p.oid = t.tgfoid JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE t.tgrelid = 'auth.users'::regclass AND NOT t.tgisinternal
      AND (n.nspname IN ('public', 'argus_private') OR t.tgname = ANY(ARRAY[
        'bind_guest_signup_handoff', 'business_auth_retention_guard',
        'business_fiscal_actor_retained', 'business_invitation_auth_retention',
        'finalize_linked_guest_identity', 'refuse_placeholder_email']))
  LOOP
    IF candidate_trigger.nspname NOT IN ('public', 'argus_private')
       OR candidate_trigger.proname <> candidate_trigger.tgname OR candidate_trigger.pronargs <> 0
       OR candidate_trigger.tgname <> ALL(ARRAY['bind_guest_signup_handoff', 'business_auth_retention_guard',
         'business_fiscal_actor_retained', 'business_invitation_auth_retention',
         'finalize_linked_guest_identity', 'refuse_placeholder_email']) THEN
      RAISE EXCEPTION 'Unapproved application trigger on auth.users: %', candidate_trigger.tgname;
    END IF;
    INSERT INTO reset_auth_triggers VALUES (candidate_trigger.oid);
  END LOOP;
END
$auth_triggers$;
INSERT INTO reset_auth_triggers
SELECT t.oid FROM pg_trigger t JOIN pg_constraint c ON c.oid = t.tgconstraint
JOIN pg_class r ON r.oid = c.conrelid JOIN pg_namespace n ON n.oid = r.relnamespace
WHERE t.tgrelid = 'auth.users'::regclass AND t.tgisinternal AND c.contype = 'f'
  AND c.confrelid = 'auth.users'::regclass AND n.nspname IN ('public', 'argus_private');

CREATE TEMP TABLE reset_allowed (classid oid, objid oid, objsubid integer,
                                PRIMARY KEY (classid, objid, objsubid)) ON COMMIT DROP;
WITH RECURSIVE allowed(classid, objid, objsubid) AS (
  SELECT d.classid, d.objid, d.objsubid FROM pg_depend d
  JOIN pg_namespace n ON d.refclassid = 'pg_namespace'::regclass AND d.refobjid = n.oid
  WHERE n.nspname IN ('public', 'argus_private')
    AND d.classid <> 'pg_extension'::regclass
    AND (d.classid <> 'pg_default_acl'::regclass OR n.nspname = 'argus_private')
    AND NOT EXISTS (SELECT FROM reset_protected p
      WHERE (p.classid, p.objid, p.objsubid) = (d.classid, d.objid, d.objsubid))
  UNION
  SELECT d.classid, d.objid, d.objsubid FROM pg_depend d JOIN allowed a
    ON d.refclassid = a.classid AND d.refobjid = a.objid
      AND (a.objsubid = 0 OR d.refobjsubid = a.objsubid)
  WHERE d.deptype IN ('i', 'a', 'P', 'S')
    AND NOT EXISTS (SELECT FROM reset_protected p
      WHERE (p.classid, p.objid, p.objsubid) = (d.classid, d.objid, d.objsubid))
    AND CASE d.classid
      WHEN 'pg_trigger'::regclass THEN EXISTS (
        SELECT FROM pg_trigger t JOIN pg_class r ON r.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = r.relnamespace
        WHERE t.oid = d.objid AND (n.nspname IN ('public', 'argus_private')
          OR t.oid IN (SELECT oid FROM reset_auth_triggers)))
      WHEN 'pg_rewrite'::regclass THEN EXISTS (
        SELECT FROM pg_rewrite r JOIN pg_class c ON c.oid = r.ev_class
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE r.oid = d.objid AND n.nspname IN ('public', 'argus_private'))
      WHEN 'pg_attrdef'::regclass THEN EXISTS (
        SELECT FROM pg_attrdef a JOIN pg_class c ON c.oid = a.adrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE a.oid = d.objid AND n.nspname IN ('public', 'argus_private'))
      WHEN 'pg_policy'::regclass THEN EXISTS (
        SELECT FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE p.oid = d.objid AND n.nspname IN ('public', 'argus_private'))
      ELSE (pg_identify_object(d.classid, d.objid, d.objsubid)).schema
        IN ('public', 'argus_private', 'pg_toast')
        OR d.classid IN ('pg_amop'::regclass, 'pg_amproc'::regclass, 'pg_enum'::regclass)
    END
)
INSERT INTO reset_allowed SELECT * FROM allowed;
INSERT INTO reset_allowed
SELECT 'pg_class'::regclass, a.attrelid, a.attnum FROM pg_attribute a
WHERE a.attnum > 0 AND NOT a.attisdropped AND EXISTS (
  SELECT FROM reset_allowed r WHERE r.classid = 'pg_class'::regclass
    AND r.objid = a.attrelid AND r.objsubid = 0)
ON CONFLICT DO NOTHING;
INSERT INTO reset_allowed SELECT 'pg_trigger'::regclass, oid, 0 FROM reset_auth_triggers
ON CONFLICT DO NOTHING;
INSERT INTO reset_allowed SELECT 'pg_namespace'::regclass, oid, 0 FROM pg_namespace
WHERE nspname = 'argus_private';

DO $event_trigger$
DECLARE e record;
BEGIN
  IF EXISTS (
    SELECT FROM pg_event_trigger t JOIN pg_proc p ON p.oid = t.evtfoid
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('public', 'argus_private') AND t.evtname <> 'ensure_rls'
  ) THEN
    RAISE EXCEPTION 'Unapproved event trigger depends on an application function';
  END IF;
  SELECT t.*, p.proname, p.pronargs, n.nspname INTO e FROM pg_event_trigger t
  JOIN pg_proc p ON p.oid = t.evtfoid JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE t.evtname = 'ensure_rls';
  IF FOUND THEN
    IF e.nspname <> 'public' OR e.proname <> 'rls_auto_enable' OR e.pronargs <> 0
        OR EXISTS (SELECT FROM reset_protected p WHERE
          (p.classid = 'pg_event_trigger'::regclass AND p.objid = e.oid)
          OR (p.classid = 'pg_proc'::regclass AND p.objid = e.evtfoid)) THEN
      RAISE EXCEPTION 'ensure_rls has an unexpected function';
    END IF;
    INSERT INTO reset_allowed VALUES ('pg_event_trigger'::regclass, e.oid, 0);
  END IF;
END
$event_trigger$;

WITH RECURSIVE ledger(classid, objid, objsubid) AS (
  SELECT 'pg_class'::regclass::oid, 'supabase_migrations.schema_migrations'::regclass::oid, 0
  UNION
  SELECT d.classid, d.objid, d.objsubid FROM pg_depend d JOIN ledger l
    ON d.refclassid = l.classid AND d.refobjid = l.objid
      AND (l.objsubid = 0 OR d.refobjsubid = l.objsubid)
  WHERE d.deptype IN ('i', 'a')
    AND (pg_identify_object(d.classid, d.objid, d.objsubid)).schema
      IN ('supabase_migrations', 'pg_toast')
)
INSERT INTO reset_allowed SELECT * FROM ledger ON CONFLICT DO NOTHING;
INSERT INTO reset_allowed
SELECT 'pg_class'::regclass, a.attrelid, a.attnum FROM pg_attribute a
WHERE a.attnum > 0 AND NOT a.attisdropped AND a.attrelid = 'supabase_migrations.schema_migrations'::regclass
ON CONFLICT DO NOTHING;

CREATE FUNCTION pg_temp.reset_drop_guard() RETURNS event_trigger LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp AS $guard$
DECLARE dropped record;
BEGIN
  FOR dropped IN SELECT * FROM pg_event_trigger_dropped_objects() LOOP
    IF NOT EXISTS (SELECT FROM pg_temp.reset_allowed a
      WHERE (a.classid, a.objid, a.objsubid) = (dropped.classid, dropped.objid, dropped.objsubid))
      OR EXISTS (SELECT FROM pg_temp.reset_protected p
      WHERE p.classid = dropped.classid AND p.objid = dropped.objid
        AND (p.objsubid = 0 OR p.objsubid = dropped.objsubid)) THEN
      RAISE EXCEPTION 'Reset refused collateral drop of % %', dropped.object_type, dropped.object_identity;
    END IF;
  END LOOP;
END
$guard$;
CREATE EVENT TRIGGER cuadrao_reset_drop_guard ON sql_drop EXECUTE FUNCTION pg_temp.reset_drop_guard();

DO $drop_app$
DECLARE target record;
BEGIN
  IF EXISTS (SELECT FROM pg_event_trigger WHERE evtname = 'ensure_rls') THEN
    DROP EVENT TRIGGER ensure_rls;
  END IF;
  FOR target IN SELECT t.tgname FROM pg_trigger t JOIN reset_auth_triggers a ON a.oid = t.oid
    WHERE NOT t.tgisinternal
  LOOP
    EXECUTE format('DROP TRIGGER %I ON auth.users', target.tgname);
  END LOOP;
  LOOP
    SELECT d.classid, d.objid, ident.type, ident.identity INTO target
    FROM pg_depend d JOIN pg_namespace n
      ON d.refclassid = 'pg_namespace'::regclass AND d.refobjid = n.oid
    CROSS JOIN LATERAL pg_identify_object(d.classid, d.objid, d.objsubid) ident
    WHERE n.nspname IN ('public', 'argus_private') AND d.objsubid = 0
      AND EXISTS (SELECT FROM reset_allowed a
        WHERE (a.classid, a.objid, a.objsubid) = (d.classid, d.objid, 0))
      AND (d.classid <> 'pg_class'::regclass OR EXISTS (
        SELECT FROM pg_class c WHERE c.oid = d.objid AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')))
      AND ident.type IN ('table', 'partitioned table', 'view', 'materialized view', 'foreign table',
        'sequence', 'function', 'procedure', 'aggregate', 'type', 'domain', 'operator',
        'operator class', 'operator family', 'collation', 'conversion', 'text search configuration',
        'text search dictionary', 'text search parser', 'text search template', 'statistics object')
      AND NOT EXISTS (SELECT FROM pg_depend own WHERE own.classid = d.classid AND own.objid = d.objid
        AND own.deptype IN ('i', 'a', 'P', 'S'))
    ORDER BY CASE WHEN d.classid = 'pg_class'::regclass THEN 0 ELSE 1 END, d.objid LIMIT 1;
    EXIT WHEN NOT FOUND;
    EXECUTE format('DROP %s %s CASCADE',
      CASE target.type WHEN 'partitioned table' THEN 'TABLE'
        WHEN 'statistics object' THEN 'STATISTICS' ELSE target.type END, target.identity);
  END LOOP;
  IF EXISTS (
    SELECT FROM pg_depend d JOIN pg_namespace n
      ON d.refclassid = 'pg_namespace'::regclass AND d.refobjid = n.oid
    WHERE n.nspname IN ('public', 'argus_private')
      AND d.classid NOT IN ('pg_extension'::regclass, 'pg_default_acl'::regclass)
      AND NOT EXISTS (SELECT FROM reset_protected p
        WHERE (p.classid, p.objid, p.objsubid) = (d.classid, d.objid, d.objsubid))
  ) THEN
    RAISE EXCEPTION 'Unsupported application objects survived reset';
  END IF;
  IF EXISTS (SELECT FROM pg_namespace WHERE nspname = 'argus_private') THEN
    DROP SCHEMA argus_private RESTRICT;
  END IF;
END
$drop_app$;

DELETE FROM auth.users;
DROP TABLE supabase_migrations.schema_migrations;
CREATE TABLE supabase_migrations.schema_migrations (version text PRIMARY KEY, statements text[], name text);
ALTER TABLE supabase_migrations.schema_migrations OWNER TO postgres;
ALTER SCHEMA public OWNER TO pg_database_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC, postgres, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA public TO PUBLIC, postgres, anon, authenticated, service_role;
DROP EVENT TRIGGER cuadrao_reset_drop_guard;
DROP FUNCTION pg_temp.reset_drop_guard();
COMMIT;
