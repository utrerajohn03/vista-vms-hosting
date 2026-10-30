-- 0003_rls.sql
-- Close the Supabase REST API (anon / authenticated roles) on the tables THIS app owns. The FastAPI backend connects as the owner
-- (postgres), which bypasses RLS, so nothing changes for the app. Safe on plain PostgreSQL too (role checks are skipped when anon /
-- authenticated do not exist).
--
-- Only this app's tables are touched: village_*, platform_audit, its own bookkeeping tables, and the foundation tables the app itself
-- created (listed in vista_owned_tables by the migration runner). A table that a shared platform already owned is left exactly as the
-- platform has it. Runs again at every start, so it only changes what is not locked yet.
DO $$
DECLARE
  owned text[];
  t text;
  s text;
  r text;
BEGIN
  SELECT coalesce(array_agg(tablename), '{}') INTO owned FROM pg_tables
   WHERE schemaname = 'public'
     AND (left(tablename, 8) = 'village_'
          OR tablename IN ('platform_audit', 'vista_schema_migrations', 'vista_owned_tables')
          OR tablename IN (SELECT name FROM vista_owned_tables));

  FOREACH t IN ARRAY owned LOOP
    IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = format('public.%I', t)::regclass) THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END IF;
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', t, r);
      END IF;
    END LOOP;
  END LOOP;

  -- sequences that belong to those tables (identity and serial columns)
  FOR s IN
    SELECT seq.relname FROM pg_class seq
      JOIN pg_depend d ON d.objid = seq.oid AND d.classid = 'pg_class'::regclass AND d.deptype IN ('a', 'i')
      JOIN pg_class tbl ON tbl.oid = d.refobjid
     WHERE seq.relkind = 'S' AND seq.relnamespace = 'public'::regnamespace
       AND tbl.relnamespace = 'public'::regnamespace AND tbl.relname = ANY (owned)
  LOOP
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
        EXECUTE format('REVOKE ALL ON SEQUENCE public.%I FROM %I', s, r);
      END IF;
    END LOOP;
  END LOOP;
END $$;
