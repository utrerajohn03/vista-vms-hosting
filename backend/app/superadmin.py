"""Platform level: the Super Admin. Outside any village. Creates properties, assigns one Admin to each, watches the platform,
and can open a property (every such sign-in is audited in that property's own log as "Super Admin")."""
import hmac
import time
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import config
from .core import Ctx, audit, login_limit, make_slug, notify, sign, site_base, tx, verify

router = APIRouter()
PROPERTY_TYPES = ["village"]   # the village type is the one this group builds; the platform can add more kinds later
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SA:
    def __init__(self, name):
        self.name = name


async def super_admin(authorization: str | None = Header(None)) -> SA:
    tok = verify(authorization[7:]) if (authorization or "").lower().startswith("bearer ") else None
    if not tok or tok.get("r") != "super":
        raise HTTPException(403, "Super Admin sign-in required")
    return SA(tok.get("n") or "Super Admin")


async def plat_audit(c, who: SA, action: str, pid=None, pname=None):
    await c.execute("INSERT INTO platform_audit (actor, action, property_id, property) VALUES ($1,$2,$3,$4)", who.name, action, pid, pname)


def admin_link(slug: str, uid, version: int = 0) -> str | None:
    """The Admin's way in: a signed link to the main site. Needs SECRET_KEY. It carries the account's token version, so it stops
    working as soon as the Admin sets or changes a password (a fresh link from the Super Admin works again)."""
    if not config.SECRET_KEY:
        return None
    tok = sign({"k": "adm", "u": str(uid), "v": int(version), "p": slug, "e": int(time.time()) + config.ADMIN_LINK_DAYS * 86400})
    return f"{site_base()}/?admin={tok}"


def village_link(slug: str) -> str:
    return f"{site_base()}/{slug}"


async def send_admin_link(c, prop, village: str, name: str, email: str, link: str | None, slug: str):
    body = (f"Hello {name},\n\nYou are now the Admin of {village} on Vista VMS.\n\n"
            + (f"Sign in with this personal link:\n{link}\n\nIt works for {config.ADMIN_LINK_DAYS} days. Please do not share it.\n\n" if link
               else "The platform administrator will send you your sign-in link.\n\n")
            + f"Your village link (for visitors, guards, the HOA office and households; print it as the gate QR):\n{village_link(slug)}")
    await notify(c, prop, email, f"You are the Admin of {village}", email, body)


# ---------------------------------------------------------------- sign-in
class PlatSession(BaseModel):
    code: str = ""
    name: str = Field(default="", max_length=80)


@router.post("/session", dependencies=[Depends(login_limit)])
async def platform_session(body: PlatSession):
    if not config.SUPER_ADMIN_CODE or not config.SECRET_KEY:
        raise HTTPException(501, "Super Admin sign-in is not set up. Set SUPER_ADMIN_CODE and SECRET_KEY on the server.")
    if not hmac.compare_digest(body.code.encode(), config.SUPER_ADMIN_CODE.encode()):
        raise HTTPException(401, "Wrong Super Admin code")
    name = " ".join(body.name.split()) or "Super Admin"
    return {"role": "super", "name": name, "token": sign({"r": "super", "n": name, "e": int(time.time()) + config.SESSION_HOURS * 3600})}


# ---------------------------------------------------------------- overview
@router.get("/overview")
async def overview(request: Request, who: SA = Depends(super_admin)):
    pool = request.app.state.pool
    rows = await pool.fetch(
        """SELECT p.id, p.name, p.slug, p.kind, p.active, p.created_at,
                  a.name AS admin_name, a.email AS admin_email,
                  (SELECT count(*) FROM village_households h WHERE h.property_id=p.id) AS households,
                  (SELECT count(*) FROM village_households h WHERE h.property_id=p.id AND h.status='verified') AS verified,
                  (SELECT count(*) FROM visits v WHERE v.property_id=p.id) AS visits,
                  (SELECT count(*) FROM visits v WHERE v.property_id=p.id AND v.created_at >= date_trunc('day', now())) AS visits_today,
                  (SELECT count(*) FROM visits v WHERE v.property_id=p.id AND v.status IN ('at_gate','arrived','missing','wrong_destination')) AS inside,
                  (SELECT count(*) FROM alerts al WHERE al.property_id=p.id AND al.status='open') AS open_alerts
           FROM properties p LEFT JOIN users a ON a.property_id=p.id AND a.role='admin'
           ORDER BY p.created_at DESC""")
    props = [{"id": str(r["id"]), "name": r["name"], "slug": r["slug"], "type": r["kind"], "active": r["active"],
              "created": r["created_at"].strftime("%b %d, %Y"), "admin": r["admin_name"] or "", "admin_email": r["admin_email"] or "",
              "households": r["households"], "verified": r["verified"], "visits": r["visits"], "today": r["visits_today"],
              "inside": r["inside"], "alerts": r["open_alerts"], "link": village_link(r["slug"])} for r in rows]
    audit_rows = await pool.fetch("SELECT to_char(created_at,'Mon DD HH24:MI') AS t, actor, action, property FROM platform_audit ORDER BY id DESC LIMIT 300")
    return {"me": who.name, "types": PROPERTY_TYPES,
            "totals": {"properties": len(props), "active": sum(1 for p in props if p["active"]), "households": sum(p["households"] for p in props),
                       "today": sum(p["today"] for p in props), "inside": sum(p["inside"] for p in props), "alerts": sum(p["alerts"] for p in props),
                       "no_admin": sum(1 for p in props if not p["admin"])},
            "properties": props,
            "audit": [{"time": a["t"], "actor": a["actor"], "action": a["action"], "property": a["property"] or "-"} for a in audit_rows]}


# ---------------------------------------------------------------- properties
class NewProperty(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    type: str = "village"
    admin_name: str = Field(min_length=1, max_length=120)
    admin_email: str = Field(pattern=EMAIL, max_length=120)


@router.post("/properties")
async def create_property(body: NewProperty, request: Request, who: SA = Depends(super_admin)):
    if body.type not in PROPERTY_TYPES:
        raise HTTPException(422, "Choose a village type from the list")
    name, admin_name, email = " ".join(body.name.split()), " ".join(body.admin_name.split()), body.admin_email.strip().lower()
    async with tx(request) as c:
        slug = None
        for _ in range(8):   # name plus a random code; a clash is astronomically unlikely, but try again if it happens
            cand = make_slug(name)
            if not await c.fetchval("SELECT 1 FROM properties WHERE slug=$1", cand):
                slug = cand
                break
        if not slug:
            raise HTTPException(500, "Could not make a village link. Try again")
        pid = await c.fetchval("INSERT INTO properties (name, slug, kind) VALUES ($1,$2,$3) RETURNING id", name, slug, body.type)
        uid = await c.fetchval("INSERT INTO users (property_id, email, name, role) VALUES ($1,$2,$3,'admin') RETURNING id", pid, email, admin_name)
        await c.execute("INSERT INTO gates (property_id, name, kind) VALUES ($1,'Main gate','Entry and exit')", pid)
        await c.executemany("INSERT INTO badges (property_id, code) VALUES ($1,$2)", [(pid, f"P{i:02d}") for i in range(1, config.PASS_COUNT + 1)])
        await c.execute("INSERT INTO audit_log (property_id, actor, role, action) VALUES ($1,$2,'Super Admin',$3)", pid, who.name,
                        f"Property created, Admin assigned: {admin_name}")
        link = admin_link(slug, uid)
        await send_admin_link(c, pid, name, admin_name, email, link, slug)
        await plat_audit(c, who, f"Created {name} ({body.type}); Admin: {admin_name} <{email}>", pid, name)
    return {"id": str(pid), "slug": slug, "village_link": village_link(slug), "admin_link": link}


class PropertyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    type: str | None = None
    active: bool | None = None


@router.patch("/properties/{pid}")
async def patch_property(pid: UUID, body: PropertyPatch, request: Request, who: SA = Depends(super_admin)):
    if body.type is not None and body.type not in PROPERTY_TYPES:
        raise HTTPException(422, "Choose a village type from the list")
    async with tx(request) as c:
        cur = await c.fetchrow("SELECT name, active FROM properties WHERE id=$1 FOR UPDATE", pid)
        if not cur:
            raise HTTPException(404, "Property not found")   # the link (slug) never changes: printed gate QR codes keep working
        name = " ".join(body.name.split()) if body.name else None
        await c.execute("UPDATE properties SET name=COALESCE($2,name), kind=COALESCE($3,kind), active=COALESCE($4,active) WHERE id=$1", pid, name, body.type, body.active)
        what = ("switched on" if body.active else "switched off") if body.active is not None and body.active != cur["active"] else "edited"
        await c.execute("INSERT INTO audit_log (property_id, actor, role, action) VALUES ($1,$2,'Super Admin',$3)", pid, who.name, f"Property {what}")
        await plat_audit(c, who, f"Property {what}", pid, name or cur["name"])
    return {"ok": True}


class AdminIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=EMAIL, max_length=120)


@router.put("/properties/{pid}/admin")
async def assign_admin(pid: UUID, body: AdminIn, request: Request, who: SA = Depends(super_admin)):
    """One Admin per property: assigning replaces the current Admin. The old link stops working because it names the account's id."""
    name, email = " ".join(body.name.split()), body.email.strip().lower()
    async with tx(request) as c:
        p = await c.fetchrow("SELECT name, slug FROM properties WHERE id=$1", pid)
        if not p:
            raise HTTPException(404, "Property not found")
        if await c.fetchval("SELECT 1 FROM users WHERE property_id=$1 AND lower(email)=lower($2) AND role<>'admin'", pid, email):
            raise HTTPException(409, "That email is already a guard or HOA account in this village. Use another email")
        await c.execute("DELETE FROM users WHERE property_id=$1 AND role='admin'", pid)
        uid = await c.fetchval("INSERT INTO users (property_id, email, name, role) VALUES ($1,$2,$3,'admin') RETURNING id", pid, email, name)
        link = admin_link(p["slug"], uid)
        await send_admin_link(c, pid, p["name"], name, email, link, p["slug"])
        await c.execute("INSERT INTO audit_log (property_id, actor, role, action) VALUES ($1,$2,'Super Admin',$3)", pid, who.name, f"Admin assigned: {name}")
        await plat_audit(c, who, f"Assigned Admin {name} <{email}>", pid, p["name"])
    return {"admin_link": link}


@router.post("/properties/{pid}/admin-link")
async def new_admin_link(pid: UUID, request: Request, who: SA = Depends(super_admin)):
    """A fresh sign-in link for the current Admin (also emailed)."""
    async with tx(request) as c:
        r = await c.fetchrow("""SELECT p.name, p.slug, u.id, u.name AS uname, u.email, u.vista_token_version AS v FROM properties p JOIN users u ON u.property_id=p.id AND u.role='admin'
                                WHERE p.id=$1""", pid)
        if not r:
            raise HTTPException(404, "This property has no Admin yet. Assign one first")
        link = admin_link(r["slug"], r["id"], r["v"])
        await send_admin_link(c, pid, r["name"], r["uname"], r["email"], link, r["slug"])
        await plat_audit(c, who, f"Sent a new Admin link to {r['uname']}", pid, r["name"])
    return {"admin_link": link}


@router.post("/properties/{pid}/enter")
async def enter_property(pid: UUID, request: Request, who: SA = Depends(super_admin)):
    """Work inside a property as its Admin. Always audited, in the property's own log as "Super Admin" and on the platform."""
    async with tx(request) as c:
        p = await c.fetchrow("SELECT id, name, slug FROM properties WHERE id=$1", pid)
        if not p:
            raise HTTPException(404, "Property not found")
        await audit(c, Ctx(p["id"], p["slug"], "admin", who.name, sa=True), "Super Admin signed in to this property")
        await plat_audit(c, who, "Signed in to the property", pid, p["name"])
    t = sign({"r": "admin", "n": who.name, "p": p["slug"], "sa": 1, "e": int(time.time()) + config.SESSION_HOURS * 3600})
    return {"role": "admin", "name": who.name, "token": t, "property": {"name": p["name"], "slug": p["slug"]}}
