"""Migrations against a database the platform already owns (a SIMULATED one: same table names as the foundation, other shapes),
an upgrade from v13's bookkeeping, and two instances starting at once. Each scenario gets its own scratch database."""
import asyncio

import asyncpg
import pytest

from app import config
from app.db import SchemaError, V13_TABLES, create_pool, migrate
from tests.conftest import ADMIN

BASE = ADMIN.rsplit("/", 1)[0]
ALL_ROLES = "'super_admin','manager','admin','guard','hoa','household'"
ALL_STATUS = ("'pending','queue','walkin_pending','approved','at_gate','arrived','missing','left','closed',"
              "'declined','rejected','wrong_destination'")
FILES = sorted(f.name for f in (__import__("pathlib").Path(__file__).resolve().parent.parent / "migrations").glob("*.sql"))


async def scratch_db(name: str) -> str:
    a = await asyncpg.connect(ADMIN)
    await a.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    await a.execute(f"CREATE DATABASE {name}")
    for r in ("anon", "authenticated"):   # the roles Supabase's REST API uses
        await a.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{r}') THEN CREATE ROLE {r} NOLOGIN; END IF; END $$")
    await a.close()
    return f"{BASE}/{name}"


async def platform_schema(dsn: str, *, roles=ALL_ROLES, status=ALL_STATUS, qr_token=True, password_hash=False, log="other_shape"):
    """What a platform that already owns properties / users / visits / badges / audit_log might look like."""
    c = await asyncpg.connect(dsn)
    await c.execute(f"""
      CREATE TABLE properties (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, slug text NOT NULL UNIQUE,
                               kind text NOT NULL DEFAULT 'condo', created_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id), email text NOT NULL,
                          name text NOT NULL, role text NOT NULL CHECK (role IN ({roles})), active boolean NOT NULL DEFAULT true,
                          created_at timestamptz NOT NULL DEFAULT now() {', password_hash text' if password_hash else ''});
      CREATE TABLE visits (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id),
                           seq bigint GENERATED ALWAYS AS IDENTITY, status text NOT NULL CHECK (status IN ({status})),
                           {'qr_token text NOT NULL UNIQUE,' if qr_token else ''} created_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE badges (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id), code text NOT NULL,
                           status text NOT NULL DEFAULT 'avail', holder text, UNIQUE (property_id, code));
      CREATE TABLE audit_log (id bigserial PRIMARY KEY, property_id uuid NOT NULL REFERENCES properties(id), actor text NOT NULL, role text NOT NULL,
                              action text NOT NULL, visit_id uuid, created_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE platform_widgets (id serial PRIMARY KEY, note text);
      INSERT INTO platform_widgets (note) VALUES ('platform data');
      GRANT SELECT ON platform_widgets, properties, users TO anon, authenticated;
    """)
    if log == "other_shape":
        await c.execute("CREATE TABLE schema_migrations (id serial PRIMARY KEY, name text NOT NULL); INSERT INTO schema_migrations (name) VALUES ('p1'),('p2'),('p3')")
    elif log == "same_shape_same_names":   # the platform's log has a version column AND even a clashing file name, but no Vista tables
        await c.execute("CREATE TABLE schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());"
                        "INSERT INTO schema_migrations (version) VALUES ('0001_foundation.sql'),('0002_village.sql'),('0003_platform.sql')")
    await c.close()


async def run(dsn: str):
    pool = await create_pool(dsn)
    try:
        return await migrate(pool)
    finally:
        await pool.close()


async def has_priv(c, role, table):
    return await c.fetchval("SELECT has_table_privilege($1, $2, 'SELECT')", role, table)


async def rls(c, table):
    return await c.fetchval("SELECT relrowsecurity FROM pg_class WHERE relname=$1 AND relnamespace='public'::regnamespace", table)


# ------------------------------------------------------------------ a shared platform database
async def test_platform_tables_logs_and_grants_are_left_alone():
    dsn = await scratch_db("mig_shared_ok")
    await platform_schema(dsn)
    assert await run(dsn) == FILES
    c = await asyncpg.connect(dsn)
    try:
        assert [r["name"] for r in await c.fetch("SELECT name FROM schema_migrations ORDER BY id")] == ["p1", "p2", "p3"]   # the platform's log: untouched
        assert await c.fetchval("SELECT count(*) FROM vista_schema_migrations") == len(FILES)                                # ours: separate
        for t in ("platform_widgets", "properties", "users", "visits", "badges", "audit_log"):                              # the platform's own tables
            assert not await rls(c, t), f"{t}: Vista switched row level security on for a platform table"
        for t in ("platform_widgets", "properties", "users"):
            assert await has_priv(c, "anon", t) and await has_priv(c, "authenticated", t), f"{t}: Vista revoked the platform's grant"
        for t in ("village_households", "village_visit_details", "restricted_areas", "platform_audit", "vista_schema_migrations",
                  "vista_owned_tables", "notifications", "alerts", "gates", "settings"):                                      # ours: closed
            assert await rls(c, t), f"{t} is not closed to the REST API"
            assert not await has_priv(c, "anon", t) and not await has_priv(c, "authenticated", t)
        owned = {r["name"] for r in await c.fetch("SELECT name FROM vista_owned_tables")}
        assert not owned & {"properties", "users", "visits", "badges", "audit_log"}                                          # the platform's
        assert {"notifications", "alerts", "gates", "settings", "restricted_areas", "village_households"} <= owned           # created by Vista
    finally:
        await c.close()
    assert await run(dsn) == []     # a second start changes nothing, and does not lock the platform's tables
    c = await asyncpg.connect(dsn)
    assert not await rls(c, "platform_widgets") and await has_priv(c, "anon", "platform_widgets")
    await c.close()


async def test_a_platform_log_with_the_same_shape_and_clashing_names_is_not_taken_for_ours():
    dsn = await scratch_db("mig_shared_log")
    await platform_schema(dsn, log="same_shape_same_names")
    assert await run(dsn) == FILES                  # nothing was skipped because of the platform's rows
    c = await asyncpg.connect(dsn)
    assert [r["version"] for r in await c.fetch("SELECT version FROM schema_migrations ORDER BY version")] == ["0001_foundation.sql", "0002_village.sql", "0003_platform.sql"]
    await c.close()


@pytest.mark.parametrize("kw, words", [
    ({"roles": "'manager','tenant'"}, ["users.role", "guard"]),
    ({"status": "'pending','approved','left'"}, ["visits.status", "walkin_pending"]),
    ({"qr_token": False}, ["visits", "qr_token"]),
])
async def test_a_platform_table_that_cannot_hold_vista_data_stops_the_start_with_a_plain_message(kw, words):
    dsn = await scratch_db("mig_shared_bad")
    await platform_schema(dsn, **kw)
    with pytest.raises(SchemaError) as e:
        await run(dsn)
    assert all(w in str(e.value) for w in words), str(e.value)
    c = await asyncpg.connect(dsn)   # refused before anything was created: the platform database is exactly as it was
    try:
        assert await c.fetchval("SELECT to_regclass('public.village_households') IS NULL")
        assert await c.fetchval("SELECT count(*) FROM vista_schema_migrations") == 0
        assert not await c.fetchval("SELECT 1 FROM pg_indexes WHERE indexname IN ('ux_users_email','ix_visits_prop_status')")
    finally:
        await c.close()


async def test_the_schema_check_can_be_switched_off(monkeypatch):
    dsn = await scratch_db("mig_shared_off")
    await platform_schema(dsn, roles="'manager','tenant'")
    monkeypatch.setattr(config, "SCHEMA_CHECK", False)
    assert await run(dsn) == FILES


async def test_the_platforms_own_password_column_is_never_overwritten():
    dsn = await scratch_db("mig_shared_pw")
    await platform_schema(dsn, password_hash=True)
    c = await asyncpg.connect(dsn)
    pid = await c.fetchval("INSERT INTO properties (name, slug) VALUES ('Tower','tower') RETURNING id")
    await c.execute("INSERT INTO users (property_id,email,name,role,password_hash) VALUES ($1,'b@p.ph','Boss','manager','$2b$12$bcrypt-hash-of-the-platform')", pid)
    await c.close()
    with pytest.raises(SchemaError) as e:
        await run(dsn)
    assert "password_hash" in str(e.value)
    c = await asyncpg.connect(dsn)
    assert await c.fetchval("SELECT password_hash FROM users") == "$2b$12$bcrypt-hash-of-the-platform"
    assert not await c.fetchval("SELECT 1 FROM vista_schema_migrations WHERE version='0009_staff_passwords.sql'")   # not recorded as done
    await c.close()


async def test_two_admins_in_one_property_stop_migration_0008_with_a_plain_message():
    dsn = await scratch_db("mig_shared_admins")
    await platform_schema(dsn)
    c = await asyncpg.connect(dsn)
    pid = await c.fetchval("INSERT INTO properties (name, slug) VALUES ('Tower','tower') RETURNING id")
    await c.executemany("INSERT INTO users (property_id,email,name,role) VALUES ($1,$2,'A','admin')", [(pid, "a@p.ph"), (pid, "b@p.ph")])
    await c.close()
    with pytest.raises(SchemaError, match="more than one"):
        await run(dsn)


# ------------------------------------------------------------------ upgrading a v13 database
async def test_a_v13_database_upgrades_in_place_and_only_the_new_migration_runs():
    dsn = await scratch_db("mig_v13")
    await run(dsn)                                                          # a complete database ...
    c = await asyncpg.connect(dsn)
    await c.execute("ALTER TABLE users DROP COLUMN vista_token_version")   # ... put back the way v13 left it:
    await c.execute("DROP TABLE vista_schema_migrations; DROP TABLE vista_owned_tables")
    await c.execute("CREATE TABLE schema_migrations (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    await c.executemany("INSERT INTO schema_migrations (version) VALUES ($1)", [(f,) for f in FILES if not f.startswith("0010")])
    await c.close()
    assert await run(dsn) == ["0010_token_version.sql"]
    c = await asyncpg.connect(dsn)
    assert await c.fetchval("SELECT count(*) FROM schema_migrations") == len(FILES) - 1       # the old table is left as it was
    assert {r["name"] for r in await c.fetch("SELECT name FROM vista_owned_tables")} >= set(V13_TABLES)
    assert await c.fetchval("SELECT vista_token_version FROM users LIMIT 1") in (0, None)
    for t in V13_TABLES:
        assert await rls(c, t)
    await c.close()


async def test_two_instances_starting_together_apply_each_migration_once():
    dsn = await scratch_db("mig_race")
    pools = [await create_pool(dsn), await create_pool(dsn)]
    try:
        a, b = await asyncio.gather(migrate(pools[0]), migrate(pools[1]))
    finally:
        for p in pools:
            await p.close()
    assert sorted(a + b) == FILES            # every file exactly once, and neither instance crashed


# ------------------------------------------------------------------ the platform's own village households tables (its migration 0003)
async def platform_village_tables(dsn: str, *, status_check="'invited','awaiting','verified'"):
    """The brief: the village households tables already exist from the platform's migration 0003, and the Village group extends them."""
    c = await asyncpg.connect(dsn)
    await c.execute(f"""
      CREATE TABLE village_households (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id),
                                       owner_name text NOT NULL, lot_code text, status text NOT NULL DEFAULT 'invited' CHECK (status IN ({status_check})));
      CREATE TABLE village_members (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id),
                                    household_id uuid NOT NULL REFERENCES village_households(id) ON DELETE CASCADE);
      INSERT INTO properties (name, slug) VALUES ('Tower','tower');
    """)
    pid = await c.fetchval("SELECT id FROM properties WHERE slug='tower'")
    hid = await c.fetchval("INSERT INTO village_households (property_id, owner_name, lot_code, status) VALUES ($1,'Maria Reyes','B1-L4','invited') RETURNING id", pid)
    await c.execute("INSERT INTO village_members (property_id, household_id) VALUES ($1,$2)", pid, hid)
    await c.close()


async def test_village_tables_the_platform_already_made_are_extended_not_recreated():
    dsn = await scratch_db("mig_village_ext")
    await platform_schema_with_village(dsn)
    assert await run(dsn) == FILES
    c = await asyncpg.connect(dsn)
    try:
        cols = {r["column_name"] for r in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='village_households'")}
        assert {"holder_name", "email", "phone", "verified_at", "verified_by", "created_at"} <= cols      # added
        mem = {r["column_name"] for r in await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_name='village_members'")}
        assert {"full_name", "is_minor"} <= mem
        row = await c.fetchrow("SELECT owner_name, lot_code, status, email FROM village_households")
        assert (row["owner_name"], row["lot_code"], row["status"], row["email"]) == ("Maria Reyes", "B1-L4", "invited", None)   # the platform's rows are intact
        assert "village_households" not in {r["name"] for r in await c.fetch("SELECT name FROM vista_owned_tables")}
    finally:
        await c.close()


async def platform_schema_with_village(dsn: str, **kw):
    c = await asyncpg.connect(dsn)
    await c.execute("""
      CREATE TABLE properties (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, slug text NOT NULL UNIQUE,
                               kind text NOT NULL DEFAULT 'condo', created_at timestamptz NOT NULL DEFAULT now())""")
    await c.close()
    # rebuild the rest of the platform foundation around that properties table, then add the village tables
    await platform_schema_rest(dsn)
    await platform_village_tables(dsn, **kw)


async def platform_schema_rest(dsn: str):
    c = await asyncpg.connect(dsn)
    await c.execute(f"""
      CREATE TABLE users (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id), email text NOT NULL,
                          name text NOT NULL, role text NOT NULL CHECK (role IN ({ALL_ROLES})), active boolean NOT NULL DEFAULT true,
                          created_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE visits (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id),
                           seq bigint GENERATED ALWAYS AS IDENTITY, status text NOT NULL CHECK (status IN ({ALL_STATUS})),
                           qr_token text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE badges (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), property_id uuid NOT NULL REFERENCES properties(id), code text NOT NULL,
                           status text NOT NULL DEFAULT 'avail', holder text, UNIQUE (property_id, code));
      CREATE TABLE audit_log (id bigserial PRIMARY KEY, property_id uuid NOT NULL REFERENCES properties(id), actor text NOT NULL, role text NOT NULL,
                              action text NOT NULL, visit_id uuid, created_at timestamptz NOT NULL DEFAULT now());
    """)
    await c.close()


async def test_a_platform_households_status_list_that_cannot_hold_our_values_stops_0002_and_undoes_it():
    dsn = await scratch_db("mig_village_bad")
    await platform_schema_with_village(dsn, status_check="'invited','active'")
    with pytest.raises(SchemaError) as e:
        await run(dsn)
    assert "village_households.status" in str(e.value) and "awaiting" in str(e.value)
    c = await asyncpg.connect(dsn)
    try:   # 0002 was undone: none of its tables or columns exist, and 0001 stays applied
        assert await c.fetchval("SELECT to_regclass('public.village_visit_details') IS NULL")
        assert not await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_name='village_households' AND column_name='email'")
        assert await c.fetchval("SELECT count(*) FROM village_households") == 1
        assert [r["version"] for r in await c.fetch("SELECT version FROM vista_schema_migrations")] == ["0001_foundation.sql"]
    finally:
        await c.close()
