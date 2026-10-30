"""asyncpg pool (Supabase-ready) and the numbered-migration runner."""
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import asyncpg

from . import config

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def pool_args(dsn: str) -> tuple[str, dict]:
    """Clean a copy-pasted Supabase URL and pick SSL / pooler settings.

    - Supabase requires SSL            -> ssl='require' for *.supabase.com / *.supabase.co hosts (or DB_SSL=require)
    - Transaction pooler (port 6543)    -> asyncpg prepared statements must be off (statement_cache_size=0)
    - '?pgbouncer=true' is a Prisma hint that asyncpg rejects, so it is stripped (and implies the pooler setting)
    """
    u = urlparse(dsn)
    q = [(k, v) for k, v in parse_qsl(u.query) if k.lower() not in ("pgbouncer", "supa", "connection_limit", "schema")]
    pgb = any(k.lower() == "pgbouncer" and v.lower() == "true" for k, v in parse_qsl(u.query))
    sslmode = next((v for k, v in q if k == "sslmode"), None)
    q = [(k, v) for k, v in q if k != "sslmode"]
    host = (u.hostname or "").lower()
    kw = {"min_size": 1, "max_size": config.DB_POOL_MAX}
    mode = config.DB_SSL.lower()
    if mode == "require" or (mode == "auto" and ("supabase." in host or sslmode in ("require", "verify-ca", "verify-full"))):
        kw["ssl"] = "require"
    if pgb or u.port == 6543 or config.DB_PGBOUNCER == "1":
        kw["statement_cache_size"] = 0
    return urlunparse(u._replace(query=urlencode(q))), kw


async def create_pool(dsn: str) -> asyncpg.Pool:
    clean, kw = pool_args(dsn)
    return await asyncpg.create_pool(clean, **kw)


TRACK = "vista_schema_migrations"   # this app's own migration log: "schema_migrations" is a common name, a shared database may already have one
OWNED = "vista_owned_tables"        # every table one of THIS app's migrations created (a shared platform's own tables are never locked down by us)
FOUNDATION = ("properties", "users", "visits", "badges", "audit_log", "notifications", "alerts", "gates", "settings")
VILLAGE_BASE = ("village_households", "village_members", "village_lots")   # may already exist (the platform's own migration makes them)
V13_TABLES = ("properties", "users", "visits", "badges", "audit_log", "notifications", "alerts", "gates", "settings",
              "restricted_areas", "restricted_area_members")   # the generic-named tables v13 and earlier created (the others start with village_)
LOCK_KEY = "vista_vms_migrations"


class SchemaError(RuntimeError):
    """The database is not what the migrations expect. The message says what to change. A foundation mismatch is found inside the 0001
    transaction, so the database is left exactly as it was; a failed pre-check likewise leaves the failed migration unapplied."""


# What the app reads and writes in tables a shared platform may already own (columns only; the types are checked by PostgreSQL itself
# when 0002 creates its foreign keys). Columns marked as added by a migration appear once that migration has run.
REQUIRED_COLUMNS = {
    "properties": ["id", "name", "slug", "kind", "active", "created_at"],
    "users": ["id", "property_id", "email", "name", "role", "active", "password_hash", "vista_token_version"],
    "visits": ["id", "property_id", "seq", "status", "qr_token", "created_at"],
    "badges": ["id", "property_id", "code", "status", "holder"],
    "audit_log": ["id", "property_id", "actor", "role", "action", "visit_id", "created_at"],
    "notifications": ["id", "property_id", "recipient", "subject", "status", "created_at"],
    "alerts": ["id", "property_id", "kind", "detail", "status", "visit_id", "created_at"],
    "gates": ["id", "property_id", "name", "kind", "active", "pos_x", "pos_y"],
    "settings": ["property_id", "key", "value"],
    "platform_audit": ["id", "actor", "action", "property_id", "property", "created_at"],
    "village_households": ["id", "property_id", "lot_code", "owner_name", "holder_name", "email", "phone", "status", "verified_at", "verified_by", "created_at"],
    "village_members": ["id", "property_id", "household_id", "full_name", "is_minor"],
    "village_lots": ["id", "property_id", "lot_code", "household_id"],
}
# Values the app writes. If the column has a CHECK list or is an enum, every value must be allowed, or the first such request fails at run time.
REQUIRED_VALUES = {
    ("users", "role"): ["admin", "guard", "hoa", "household"],
    ("visits", "status"): ["pending", "queue", "walkin_pending", "approved", "at_gate", "arrived", "missing", "left", "closed",
                           "declined", "rejected", "wrong_destination"],
    ("badges", "status"): ["avail", "issued", "lost"],
    ("alerts", "status"): ["open", "resolved"],
    ("village_households", "status"): ["invited", "awaiting", "verified"],
}


ADDED_LATER = {("properties", "active"), ("users", "password_hash"), ("users", "vista_token_version"), ("gates", "pos_x"), ("gates", "pos_y")}


async def check_schema(c, early: bool = False, only: tuple | None = None) -> None:
    """Fail at start-up, with a plain message, when a table that already existed (a shared platform's) lacks something the app needs.
    early=True skips what later migrations add. only=(tables) checks just those: it runs inside the transaction of the migration that
    makes or extends them (0001: foundation, 0002: village), so a mismatch undoes that migration and leaves the database as it was."""
    problems = []
    cols: dict[str, set] = {}
    for r in await c.fetch("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'"):
        cols.setdefault(r["table_name"], set()).add(r["column_name"])
    for t, need in REQUIRED_COLUMNS.items():
        if only is not None and t not in only:
            continue
        missing = [x for x in need if x not in cols.get(t, set()) and not (early and (t, x) in ADDED_LATER)]
        if missing:
            problems.append(f"table {t} has no column {', '.join(missing)}")
    for (t, col), values in REQUIRED_VALUES.items():
        if (only is not None and t not in only) or col not in cols.get(t, set()):
            continue
        allowed = None   # None = no list found (free text), otherwise the values the database lets through
        enum = await c.fetch("""SELECT e.enumlabel FROM pg_attribute a JOIN pg_type ty ON ty.oid=a.atttypid JOIN pg_enum e ON e.enumtypid=ty.oid
                                WHERE a.attrelid=format('public.%I', $1::text)::regclass AND a.attname=$2""", t, col)
        if enum:
            allowed = {r["enumlabel"] for r in enum}
            bad = [v for v in values if v not in allowed]
            if bad:
                problems.append(f"{t}.{col} is an enum without the values {', '.join(bad)}")
            continue
        for r in await c.fetch("""SELECT conname, pg_get_constraintdef(oid) AS d FROM pg_constraint
                                  WHERE conrelid=format('public.%I', $1::text)::regclass AND contype='c'""", t):
            d = r["d"]
            if col in d and "'" in d:   # a CHECK that lists literal values for this column
                bad = [v for v in values if f"'{v}'" not in d]
                if bad:
                    problems.append(f"{t}.{col} has the CHECK {r['conname']} which does not allow: {', '.join(bad)}")
    if problems:
        raise SchemaError("The database does not match what Vista VMS needs (a shared platform table differs from the foundation in "
                          "migrations/0001_foundation.sql):\n  - " + "\n  - ".join(problems) +
                          "\nAlign these tables (or adjust the Vista code), then start again. SCHEMA_CHECK=0 skips this check at your own risk.")


async def _pre_0008(c):
    dup = await c.fetch("SELECT property_id FROM users WHERE role='admin' GROUP BY property_id HAVING count(*) > 1")
    if dup:
        raise SchemaError(f"0008 makes 'one Admin per property' a database rule, but {len(dup)} propert{'y has' if len(dup) == 1 else 'ies have'} "
                          "more than one users row with role 'admin'. Remove the extra Admin rows, then start again.")


async def _pre_0009(c):
    if await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='users' AND column_name='password_hash'"):
        other = await c.fetchval("SELECT count(*) FROM users WHERE password_hash IS NOT NULL AND password_hash NOT LIKE 'scrypt$%'")
        if other:
            raise SchemaError(f"users.password_hash already exists and holds {other} password(s) that Vista did not write. Vista would read them as "
                              "invalid and overwrite them on a password change, which would break the platform's own sign-in. "
                              "Do not share that column: give Vista its own (rename the column in 0009 and in the code) or keep the staff accounts in a separate table.")


PRECHECKS = {"0008_platform.sql": _pre_0008, "0009_staff_passwords.sql": _pre_0009}


async def lockdown(c):
    """Supabase publishes every table in the public schema through its REST API (PostgREST). Row level security with no policies closes
    that door; this backend connects as the table owner, which bypasses RLS. Only THIS app's tables are touched (see 0003_rls.sql):
    a shared platform's own tables keep whatever protection and grants the platform gave them."""
    await c.execute((MIGRATIONS / "0003_rls.sql").read_text())


async def _tables(c) -> set:
    return {r["tablename"] for r in await c.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")}


async def _bootstrap(c):
    await c.execute(f"CREATE TABLE IF NOT EXISTS {TRACK} (version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    await c.execute(f"CREATE TABLE IF NOT EXISTS {OWNED} (name text PRIMARY KEY)")
    # Upgrade from v13 and earlier, which logged into a table called schema_migrations. Copy only if that table is clearly ours
    # (our first two file names AND our village tables), and then only our own file names, never a platform's rows.
    if await c.fetchval(f"SELECT count(*) FROM {TRACK}") == 0 and await c.fetchval("SELECT to_regclass('public.schema_migrations') IS NOT NULL"):
        if await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='schema_migrations' AND column_name='version'"):
            ours = [f.name for f in MIGRATIONS.glob("*.sql")]
            old = {r["version"] for r in await c.fetch("SELECT version FROM schema_migrations WHERE version = ANY($1::text[])", ours)}
            if {"0001_foundation.sql", "0002_village.sql"} <= old and await c.fetchval("SELECT to_regclass('public.village_households') IS NOT NULL"):
                await c.executemany(f"INSERT INTO {TRACK} (version) VALUES ($1) ON CONFLICT DO NOTHING", [(v,) for v in sorted(old)])
                # a v13 database was created by this app, so it also created the foundation tables (and has already locked them down)
                await c.executemany(f"INSERT INTO {OWNED} (name) VALUES ($1) ON CONFLICT DO NOTHING", [(t,) for t in V13_TABLES])


async def migrate(pool: asyncpg.Pool) -> list[str]:
    """Apply migrations/NNNN_*.sql in order, once each, each inside a transaction. Safe to run from two instances at once
    (a transaction-level advisory lock, which also works through a transaction pooler). Raises SchemaError, with the reason, when the
    database cannot take a migration; the failed migration is rolled back whole."""
    applied_now = []
    async with pool.acquire() as c:
        async with c.transaction():
            await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", LOCK_KEY)
            await _bootstrap(c)
        for f in sorted(MIGRATIONS.glob("*.sql")):
            async with c.transaction():
                await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", LOCK_KEY)
                if await c.fetchval(f"SELECT 1 FROM {TRACK} WHERE version=$1", f.name):   # another instance applied it while we waited
                    continue
                if f.name in PRECHECKS:
                    await PRECHECKS[f.name](c)
                before = await _tables(c)   # a table that was already there when its CREATE TABLE IF NOT EXISTS ran belongs to the platform, not to us
                await c.execute(f.read_text())
                if config.SCHEMA_CHECK and f.name == "0001_foundation.sql":
                    await check_schema(c, early=True, only=FOUNDATION)   # raises inside this transaction: an incompatible platform is left untouched
                if config.SCHEMA_CHECK and f.name == "0002_village.sql":
                    await check_schema(c, only=VILLAGE_BASE)
                made = sorted(await _tables(c) - before)
                if made:
                    await c.executemany(f"INSERT INTO {OWNED} (name) VALUES ($1) ON CONFLICT DO NOTHING", [(t,) for t in made])
                await c.execute(f"INSERT INTO {TRACK} (version) VALUES ($1)", f.name)
            applied_now.append(f.name)
        async with c.transaction():   # same lock: two instances changing grants and RLS at the same moment collide in the catalog
            await c.execute("SELECT pg_advisory_xact_lock(hashtext($1))", LOCK_KEY)
            if config.SCHEMA_CHECK:
                await check_schema(c)
            if config.ENABLE_RLS:
                await lockdown(c)  # also covers tables added by future migrations
    return applied_now
