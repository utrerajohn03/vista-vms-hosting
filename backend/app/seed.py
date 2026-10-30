"""Demo data. Run: python -m app.seed   (safe to run twice: skips if the property already exists)"""
import asyncio
from datetime import datetime, timedelta, timezone

from . import config
from .api import VisitIn
from .core import Ctx, create_visit, hash_password, make_slug
from .db import create_pool, migrate


async def seed(pool, slug=None) -> bool:
    slug = slug or config.DEFAULT_PROPERTY
    async with pool.acquire() as c, c.transaction():
        if await c.fetchval("SELECT 1 FROM properties WHERE slug=$1", slug):
            return False
        p = await c.fetchval("INSERT INTO properties (name, slug) VALUES ('Greenfield Village',$1) RETURNING id", slug)
        for em, n, r in [("admin@greenfield.ph", "Village Admin", "admin"), ("ramon@greenfield.ph", "Ramon Dela Cruz", "guard"),
                         ("edgar@greenfield.ph", "Edgar Santos", "guard"), ("hoa@greenfield.ph", "HOA desk", "hoa"),
                         ("lorna@greenfield.ph", "Lorna Aquino", "hoa")]:
            await c.execute("INSERT INTO users (property_id, email, name, role, password_hash) VALUES ($1,$2,$3,$4,$5)", p, em, n, r,
                            hash_password(config.SEED_PASSWORD) if len(config.SEED_PASSWORD) >= config.MIN_PASSWORD else None)
        hh = {}
        for lot, owner, holder, em, st, mem in [
            ("B1-L4", "Reyes", "Maria Reyes", "maria@mail.ph", "verified", [("Maria Reyes", 0), ("Lito Reyes", 0), ("Paolo Reyes", 1)]),
            ("B2-L7", "Santos", "Ana Santos", "ana@mail.ph", "verified", [("Ana Santos", 0), ("Jun Santos", 0), ("Mika Santos", 1)]),
            ("B3-L2", "Cruz", "Ben Cruz", "ben@mail.ph", "awaiting", [("Ben Cruz", 0)]),
            ("B2-L2", "Dela Rosa", "Rosa Dela Rosa", "rosa@mail.ph", "verified", [("Rosa Dela Rosa", 0)]),
            ("B3-L5", "Garcia", "Pia Garcia", "pia@mail.ph", "awaiting", [("Pia Garcia", 0), ("Gio Garcia", 0)])]:
            hid = await c.fetchval("""INSERT INTO village_households (property_id, lot_code, owner_name, holder_name, email, phone, status, verified_at)
                                      VALUES ($1,$2,$3,$4,$5,$6,$7, CASE WHEN $7='verified' THEN now() END) RETURNING id""",
                                   p, lot, owner, holder, em, "0917 555 01" + str(len(hh)).zfill(2), st)
            hh[lot] = hid
            await c.execute("INSERT INTO village_lots (property_id, lot_code, household_id) VALUES ($1,$2,$3)", p, lot, hid)
            for n, minor in mem:
                await c.execute("INSERT INTO village_members (property_id, household_id, full_name, is_minor) VALUES ($1,$2,$3,$4)", p, hid, n, bool(minor))
        await c.execute("INSERT INTO village_households (property_id, email, holder_name) VALUES ($1,'lim@mail.ph','lim@mail.ph')", p)
        await c.execute("INSERT INTO village_lots (property_id, lot_code) VALUES ($1,'B1-L1')", p)
        for area, member in [("Care wing, Block 2", "Jun Santos"), ("Maintenance yard", "Ben Cruz")]:
            a = await c.fetchval("INSERT INTO restricted_areas (property_id, name) VALUES ($1,$2) RETURNING id", p, area)
            await c.execute("INSERT INTO restricted_area_members (property_id, area_id, member_id) SELECT $1,$2,id FROM village_members WHERE property_id=$1 AND full_name=$3", p, a, member)
        for g, k, act in [("Main gate", "Entry and exit", True), ("Service gate", "Deliveries", True), ("North pedestrian gate", "Walk-ins", False)]:
            await c.execute("INSERT INTO gates (property_id, name, kind, active) VALUES ($1,$2,$3,$4)", p, g, k, act)
        for i in range(1, 15):
            await c.execute("INSERT INTO badges (property_id, code) VALUES ($1,$2)", p, f"P{i:02d}")
        cx = Ctx(p, slug, "admin", "Seed")

        async def mk(name, phone, house, host, arr, friends=(), status=None, hours_in=None):
            seq = await create_visit(c, cx, VisitIn(name=name, phone=phone, house=house, host=host, arrival=arr,
                                                    purpose="Visit", friends=list(friends)))
            vid = await c.fetchval("SELECT id FROM visits WHERE property_id=$1 AND seq=$2", p, seq)
            if status:
                await c.execute("UPDATE visits SET status=$2 WHERE id=$1", vid, status)
            if status in ("at_gate", "arrived", "missing", "left"):
                people = await c.fetch("SELECT id, full_name FROM village_visit_people WHERE visit_id=$1 ORDER BY sort", vid)
                for pe in people:
                    b = await c.fetchrow("SELECT id FROM badges WHERE property_id=$1 AND status='avail' ORDER BY code LIMIT 1", p)
                    inn = status == "arrived"
                    await c.execute("UPDATE village_visit_people SET badge_id=$2, arrived_at=CASE WHEN $3 THEN now() END, left_at=CASE WHEN $4 THEN now() END WHERE id=$1",
                                    pe["id"], b["id"], inn, status == "left")
                    await c.execute("UPDATE badges SET status=$2, holder=$3 WHERE id=$1", b["id"], "avail" if status == "left" else "issued",
                                    None if status == "left" else pe["full_name"])
                await c.execute("UPDATE village_visit_details SET gate_notified_at=$2 WHERE visit_id=$1", vid,
                                datetime.now(timezone.utc) - timedelta(hours=hours_in or 1))
            if arr == "Own vehicle" and status in ("at_gate", "arrived", "left"):
                await c.execute("INSERT INTO village_vehicle_checks (visit_id, property_id, photo_path, plate_ok, color_ok, type_ok) VALUES ($1,$2,'entry-photos/demo.jpg',true,true,true)", vid, p)
            return seq

        await mk("Rico Mendoza", "0917 555 0114", "B1-L4", "Maria Reyes", "Own vehicle", ["Rico’s guest 1", "Rico’s guest 2"], "approved")
        await mk("Carla Bautista", "0917 555 0113", "B2-L7", "Ana Santos", "Walking")
        await mk("Grace Tan", "0917 555 0111", "B2-L7", "Jun Santos", "Walking", status="approved")
        await mk("Dennis Uy", "0917 555 0112", "B1-L4", "Lito Reyes", "Ride", ["Dennis’s guest"], "at_gate", 1)
        await mk("Paolo Lim", "0917 555 0110", "B3-L2", "", "Own vehicle", status="arrived")
        await mk("Ana Flores", "0917 555 0108", "B2-L2", "Rosa Dela Rosa", "Walking", status="missing", hours_in=4)
        await mk("Tess Villanueva", "0917 555 0107", "B1-L99", "Maria Reyes", "Walking")
        await mk("Ken Aquino", "0917 555 0106", "B2-L7", "Ana Santos", "Ride", status="left", hours_in=5)
        await mk("Liza Ramos", "0917 555 0105", "B3-L5", "Pia Garcia", "Walking", status="declined")
        await c.execute("INSERT INTO alerts (property_id, kind, detail) SELECT $1,'Missing', 'VS-0006 Ana Flores: no house scan 3 hours after the gate notice'", p)
        await c.execute("INSERT INTO audit_log (property_id, actor, role, action) VALUES ($1,'Seed','System','Demo data loaded')", p)
    return True


async def bootstrap(pool, name="Greenfield Village", slug=None, passes=20) -> bool:
    """A clean village for real use: the property, one gate and a pass inventory. No fake people or visits."""
    slug = slug or config.DEFAULT_PROPERTY
    async with pool.acquire() as c, c.transaction():
        if await c.fetchval("SELECT 1 FROM properties WHERE slug=$1", slug):
            return False
        p = await c.fetchval("INSERT INTO properties (name, slug) VALUES ($1,$2) RETURNING id", name, slug)
        await c.execute("INSERT INTO gates (property_id, name, kind) VALUES ($1,'Main gate','Entry and exit')", p)
        for i in range(1, passes + 1):
            await c.execute("INSERT INTO badges (property_id, code) VALUES ($1,$2)", p, f"P{i:02d}")
        await c.execute("INSERT INTO audit_log (property_id, actor, role, action) VALUES ($1,'System','System','Property created')", p)
    return True


async def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--empty", action="store_true", help="create the property only (no demo people or visits)")
    ap.add_argument("--name", default="Greenfield Village")
    ap.add_argument("--passes", type=int, default=20)
    ap.add_argument("--new-link", action="store_true", help="with --empty: give the village its own generated link (name plus a random code) instead of DEFAULT_PROPERTY")
    a = ap.parse_args()
    pool = await create_pool(config.DATABASE_URL)
    await migrate(pool)
    if a.empty:
        slug = make_slug(a.name) if a.new_link else None
        made = await bootstrap(pool, a.name, slug, a.passes)
        print((f"created. Village link: /{slug or config.DEFAULT_PROPERTY}") if made else "already exists")
    else:
        print("seeded" if await seed(pool) else "already seeded")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
