"""Shared helpers: request context, role checks, audit, notifications, visit creation, Missing job."""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import unicodedata
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from fastapi import Depends, Header, HTTPException, Request

from . import config, mailer

ROLES = {"admin", "guard", "hoa", "household"}
ROLE_LABEL = {"admin": "Admin", "guard": "Guard", "hoa": "HOA office", "household": "Household"}
STATUS_LABEL = {
    "pending": "Pending", "queue": "In HOA queue", "walkin_pending": "Pending", "approved": "Waiting at gate",
    "at_gate": "Inside", "arrived": "Arrived", "missing": "Missing", "left": "Left", "closed": "Closed",
    "declined": "Declined", "rejected": "Rejected", "wrong_destination": "Wrong destination",
}
ARR_LABEL = {"walking": "Walking", "own_vehicle": "Own vehicle", "ride": "Ride"}
ARR_CODE = {"walking": "walking", "own vehicle": "own_vehicle", "own_vehicle": "own_vehicle",
            "ride": "ride", "ride or taxi": "ride"}
ACTIVE = ("at_gate", "arrived", "missing", "wrong_destination")  # visitor is inside the village
TZ = ZoneInfo(config.TIMEZONE)


class Ctx:
    def __init__(self, prop, slug, role, name, hid=None, hlot=None, sa=False):
        self.prop, self.slug, self.role, self.name, self.hid, self.hlot = prop, slug, role, name, hid, hlot
        self.sa = sa   # a Super Admin working inside this village: shown as "Super Admin" in its audit log


def sign(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify(token: str) -> dict | None:
    try:
        body, sig = token.rsplit(".", 1)
        good = hmac.new(config.SECRET_KEY.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not config.SECRET_KEY or not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return data if data.get("e", 0) > time.time() else None
    except Exception:
        return None


def session_token(role: str, name: str, slug: str, *, uid=None, version: int = 0, hid=None, code: bool = False) -> str:
    """A village sign-in token. uid = the personal account (checked against the database on every request), version = that account's
    vista_token_version when the token was issued, code = signed in with the shared staff code."""
    claims = {"r": role, "n": name, "p": slug, "e": int(time.time()) + config.SESSION_HOURS * 3600}
    if uid:
        claims["u"], claims["v"] = str(uid), int(version)
    if hid:
        claims["h"] = str(hid)
    if code:
        claims["c"] = 1
    return sign(claims)


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()}"


_DUMMY = hash_password("not-a-real-password")


def check_password(pw: str, stored: str | None) -> bool:
    """Always does the same work, whether or not the account exists, so response time does not reveal which emails are real."""
    try:
        _, salt, good = (stored or _DUMMY).split("$")
        h = hashlib.scrypt((pw or "").encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32).hex()
    except Exception:
        return False
    return hmac.compare_digest(h, good) and bool(stored)


# scrypt takes tens of milliseconds of pure CPU. Called straight from an async endpoint it stops every other request (the gate included)
# until it finishes, so the endpoints use these two, which run it on a worker thread.
async def check_password_async(pw: str, stored: str | None) -> bool:
    return await asyncio.to_thread(check_password, pw, stored)


async def hash_password_async(pw: str) -> str:
    return await asyncio.to_thread(hash_password, pw)


def code_ok(code: str | None) -> bool:
    return bool(config.STAFF_ACCESS_CODE) and hmac.compare_digest((code or "").encode(), config.STAFF_ACCESS_CODE.encode())


async def resolve_property(pool, slug: str, allow_off: bool = False):
    """The property row for a village link. 404 when unknown, 403 when the platform switched it off."""
    p = await pool.fetchrow("SELECT id, active FROM properties WHERE slug=$1", slug)
    if not p:
        raise HTTPException(404, "Unknown property")
    if not p["active"] and not allow_off:
        raise HTTPException(403, "This village is switched off. Please contact the platform administrator.")
    return p


async def ctx(request: Request, authorization: str | None = Header(None), x_role: str | None = Header(None),
              x_user: str | None = Header(None), x_household: str | None = Header(None),
              x_property: str | None = Header(None)) -> Ctx:
    """Who is calling?
    - STAFF_ACCESS_CODE set: only a signed session token (from POST /api/session) counts; role headers are ignored.
    - otherwise AUTH_MODE=dev: the role comes from X-Role / X-Household headers (demo only, never expose publicly).
    Replace this one function to plug in the platform's real auth."""
    pool = request.app.state.pool
    slug = x_property or config.DEFAULT_PROPERTY
    role = hid = name = uid = None
    sa = False
    tok = verify((authorization or "")[7:]) if (authorization or "").lower().startswith("bearer ") else None
    tok_v = 0
    if tok and tok.get("r") in ROLES and tok.get("p"):   # a village sign-in token (not an invitation or a platform token)
        slug, role, name, hid, sa, uid = tok["p"], tok["r"], tok["n"], tok.get("h"), bool(tok.get("sa")), tok.get("u")
        tok_v = int(tok.get("v") or 0)
        # A token the shared staff code produced carries no account (staff roles) or the "c" mark (household picker). Once the shared
        # code is switched off (STAFF_CODE_LOGIN=0) those sessions end too, not only new sign-ins.
        if not config.STAFF_CODE_LOGIN and not sa and not uid and (tok.get("c") or role != "household"):
            raise HTTPException(401, "Your session has ended. Sign in with your own email and password.")
    elif config.STAFF_ACCESS_CODE:
        pass   # published mode: role headers are never trusted
    elif x_role in ROLES:
        if config.AUTH_MODE != "dev":
            raise HTTPException(501, "Plug the platform auth into core.ctx")
        role, name = x_role, x_user
    p = await resolve_property(pool, slug, allow_off=sa)
    if uid:   # a personal account: the token only works while the account exists, is active and still has that role
        u = await pool.fetchrow("SELECT role, active, name, vista_token_version AS v FROM users WHERE id=$1 AND property_id=$2", UUID(uid), p["id"])
        if not u or not u["active"] or u["role"] != role:
            raise HTTPException(401, "Your account is no longer active. Ask the Admin.")
        if u["v"] != tok_v:   # the password was changed or reset, or the account was switched off and on, after this token was issued
            raise HTTPException(401, "Your session has ended because the password or the account changed. Sign in again.")
        name = u["name"]
    hlot = None
    if role == "household":
        if hid:
            h = await pool.fetchrow("SELECT id, lot_code, holder_name FROM village_households WHERE property_id=$1 AND id=$2", p["id"], hid)
        else:
            h = await pool.fetchrow("SELECT id, lot_code, holder_name FROM village_households WHERE property_id=$1 AND lower(lot_code)=lower($2)",
                                    p["id"], x_household or "")
        if not h:
            raise HTTPException(403, "Choose a household")
        hid, hlot, name = h["id"], h["lot_code"], name or h["holder_name"]
    return Ctx(p["id"], slug, role, name or (ROLE_LABEL.get(role) if role else None), hid, hlot, sa)


def need(*roles: str):
    async def dep(c: Ctx = Depends(ctx)) -> Ctx:
        if c.role not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return c
    return dep


_hits: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    """The caller's address for rate limiting. X-Forwarded-For is written by the client too, so only the entry added by our own
    proxy counts: the one TRUST_PROXY_HOPS from the right. Taking the first entry would let anyone dodge the limit by sending
    a made-up header (and so guess the access code without being slowed down)."""
    parts = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
    if config.TRUST_PROXY_HOPS > 0 and len(parts) >= config.TRUST_PROXY_HOPS:
        return parts[-config.TRUST_PROXY_HOPS]
    return request.client.host if request.client else "x"


def _limit(request: Request, bucket: str, cap: int, who: str = ""):
    ip = client_ip(request)
    key, now = (f"{bucket}:{who}" if who else f"{bucket}:{ip}"), time.time()   # per account when given: changing address does not reset it
    if len(_hits) > 5000:   # forget addresses that have been quiet for a minute, so the table cannot grow without limit
        for k in [k for k, v in _hits.items() if not v or now - v[-1] >= 60]:
            del _hits[k]
    w = [t for t in _hits.get(key, []) if now - t < 60]
    if len(w) >= cap:
        raise HTTPException(429, "Too many requests. Try again in a minute.")
    w.append(now)
    _hits[key] = w


async def public_limit(request: Request):
    """Fixed-window limiter for the public visitor endpoints (slows house-number guessing)."""
    _limit(request, "pub", config.RATE_LIMIT_PER_MIN)


def account_limit(request: Request, email: str):
    """Failed-guess brake per account and address, on top of the per-address login limit."""
    _limit(request, "acct", 10, (email or "").strip().lower()[:120])


async def login_limit(request: Request):
    """Tighter limiter for staff sign-in (slows access-code guessing)."""
    _limit(request, "login", config.LOGIN_RATE_LIMIT_PER_MIN)


def tx(request: Request):
    """async with tx(request) as con: ...  (one transaction per endpoint)"""
    class _T:
        async def __aenter__(s):
            s.con = await request.app.state.pool.acquire()
            s.t = s.con.transaction()
            await s.t.start()
            return s.con

        async def __aexit__(s, et, ev, tb):
            try:
                if et:
                    await s.t.rollback()
                else:
                    await s.t.commit()
            finally:
                await request.app.state.pool.release(s.con)
    return _T()


async def audit(c, cx: Ctx, action: str, visit_id=None):
    await c.execute("INSERT INTO audit_log (property_id, actor, role, action, visit_id) VALUES ($1,$2,$3,$4,$5)",
                    cx.prop, cx.name or "Visitor", "Super Admin" if cx.sa else ROLE_LABEL.get(cx.role, "Visitor"), action, visit_id)


async def setting(c, prop, tab: int, i: int, default=None):
    """One value the Admin saved on the Settings page (tab0 General, tab1 Visit rules, tab2 Notifications). default when unset."""
    import json
    raw = await c.fetchval("SELECT value FROM settings WHERE property_id=$1 AND key=$2", prop, f"tab{tab}")
    try:
        row = json.loads(raw) if isinstance(raw, str) else raw
        v = row[i]
        return default if v is None or v == "" else v
    except (TypeError, IndexError, ValueError, KeyError):
        return default


async def setting_int(c, prop, tab: int, i: int, default: int, lo: int = 1, hi: int = 3650) -> int:
    try:
        return min(max(int(str(await setting(c, prop, tab, i, default)).strip()), lo), hi)
    except ValueError:
        return default


_bg: set = set()


async def notify(c, prop, recipient: str, subject: str, email: str | None = None, body: str | None = None, qr: str | None = None):
    """Store the notice (shown on the Messages page) and, if email is set up (EmailJS, or SMTP on a laptop), also email it.
    qr = the text inside a QR code (VISTA:...): the email then carries the QR picture."""
    await c.execute("INSERT INTO notifications (property_id, recipient, subject) VALUES ($1,$2,$3)", prop, recipient, subject)
    if not email:
        return
    if not mailer.email_ready():
        logging.getLogger("vista").warning("Email to %s NOT sent (%s): no email is set up. Fill in the EMAILJS_* settings (SMTP_* on a laptop) in backend/.env", email, subject)
        return
    t = asyncio.create_task(mailer.send_email(email, subject, body or subject, qr))
    _bg.add(t)   # asyncio keeps only a weak reference to a task: hold it until it finishes or it can be dropped mid-send
    t.add_done_callback(_bg.discard)


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_SLUGS = {"api", "assets", "admin", "static", "health", "favicon", "login", "invite"}


def make_slug(name: str) -> str:
    """The property link: the village name plus a random code, e.g. 'Greenfield Village' -> 'greenfield-village-7f3a'.
    The random part makes the link impossible to guess, which is what keeps one village's page private from another's."""
    base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()).strip("-")
    base = (base or "village")[:40].strip("-")
    return f"{base}-{secrets.token_hex(2)}"


def valid_slug(s: str | None) -> bool:
    return bool(s) and 3 <= len(s) <= 60 and bool(SLUG_RE.match(s)) and s not in RESERVED_SLUGS


LOT_RE = re.compile(r"^B(\d{1,3})\s*-\s*L(\d{1,3})$", re.I)
HOUSE_RE = re.compile(r"^[A-Z0-9][A-Z0-9 .#/-]{0,19}$")


def norm_lot(s: str | None) -> str | None:
    """Block and lot, or a house number. 'b1 - l4' -> 'B1-L4'; '25a' -> '25A'. None when empty or not a usable code."""
    t = " ".join((s or "").split())
    m = LOT_RE.match(t)
    if m:
        return f"B{int(m.group(1))}-L{int(m.group(2))}"
    t = t.upper()
    return t if HOUSE_RE.match(t) and re.search(r"[A-Z0-9]", t) else None


MAX_PHOTO_BYTES = 1_500_000


def decode_photo(data: str | None, what: str = "entry photo") -> bytes:
    """A photo sent as base64 (a data: URL prefix is fine). Must be a real JPEG and not too large."""
    if not data:
        raise HTTPException(422, "Take the entry photo for the vehicle check" if what == "entry photo" else f"Add the {what}")
    raw = data.split(",", 1)[1] if data.startswith("data:") else data
    try:
        img = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(422, f"The {what} could not be read. Choose it again")
    if not img.startswith(b"\xff\xd8\xff"):
        raise HTTPException(422, f"The {what} must be a JPEG image")
    if len(img) > MAX_PHOTO_BYTES:
        raise HTTPException(413, f"The {what} is too large. Choose a smaller one")
    return img


def parse_ref(ref: str) -> int:
    m = re.fullmatch(r"VS-(\d+)", ref or "")
    if not m:
        raise HTTPException(404, "Visit not found")
    return int(m.group(1))


async def get_visit(c, cx: Ctx, ref: str, lock=False):
    q = """SELECT v.id, v.seq, v.status, v.qr_token, d.* FROM visits v
           JOIN village_visit_details d ON d.visit_id=v.id
           WHERE v.property_id=$1 AND v.seq=$2""" + (" FOR UPDATE OF v" if lock else "")
    v = await c.fetchrow(q, cx.prop, parse_ref(ref))
    if not v or (cx.role == "household" and v["household_id"] != cx.hid):
        raise HTTPException(404, "Visit not found")
    return v


async def match_household(c, prop, house: str, host: str):
    """Returns (household, member, restricted). household is None when the house or person is not found."""
    h = await c.fetchrow("SELECT id, holder_name, phone, email FROM village_households "
                         "WHERE property_id=$1 AND lower(lot_code)=lower($2)", prop, (house or "").strip())
    member, restricted = None, False
    if h and (host or "").strip():
        member = await c.fetchrow("SELECT id FROM village_members WHERE property_id=$1 AND household_id=$2 "
                                  "AND lower(full_name)=lower($3)", prop, h["id"], host.strip())
        if not member:
            return None, None, False
        restricted = await c.fetchval(
            """SELECT EXISTS(SELECT 1 FROM restricted_area_members m JOIN restricted_areas a ON a.id=m.area_id
               WHERE m.property_id=$1 AND m.member_id=$2 AND a.active)""", prop, member["id"])
    return h, member, restricted


_HAS_TIME = re.compile(r"[T ]\d{1,2}:\d{2}")


def parse_when(s, need_time: bool = False):
    """A visit date and time from the form ('2026-10-24T18:00'). None when empty or unreadable.
    need_time=True also refuses a bare date, because a visit request must say when the visitor arrives."""
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    if need_time and not _HAS_TIME.search(s):
        return None
    try:
        d = datetime.fromisoformat(s.replace(" ", "T"))
        return d if d.tzinfo else d.replace(tzinfo=TZ)
    except ValueError:
        return None


def site_base() -> str:
    return (config.FRONTEND_URL or (config.CORS_ORIGINS.split(",")[0] if config.CORS_ORIGINS else "")).strip().rstrip("/")


def approval_link(slug: str, visit_id, hid) -> str | None:
    """Signed, stateless link in the household's email: opens the confirmation page for this one request.
    None when the server cannot sign tokens (demo mode); the household then approves in the app."""
    if not config.SECRET_KEY:
        return None
    tok = sign({"k": "apr", "v": str(visit_id), "h": str(hid), "p": slug, "e": int(time.time()) + config.APPROVAL_DAYS * 86400})
    return f"{site_base()}/{slug}?approve={tok}"


async def send_approval(c, prop, slug, visit_id, h):
    """Email the household's account holder the request with an approve/decline link (also shown on the Messages page)."""
    d = await c.fetchrow(
        """SELECT v.seq, d.visitor_name, d.purpose, d.visit_at, d.typed_host, d.arrival_method,
                  (SELECT count(*) FROM village_visit_people p WHERE p.visit_id=v.id) AS n
           FROM visits v JOIN village_visit_details d ON d.visit_id=v.id WHERE v.id=$1""", visit_id)
    ref = f"VS-{d['seq']:04d}"
    link = approval_link(slug, visit_id, h["id"])
    who = d["visitor_name"] + (f" and {d['n'] - 1} other{'s' if d['n'] > 2 else ''}" if d["n"] > 1 else "")
    when = d["visit_at"].astimezone(TZ).strftime("%b %d, %H:%M") if d["visit_at"] else "not stated"
    body = (f"{who} would like to visit {d['typed_host'] or 'your household'}.\n"
            f"Purpose: {d['purpose'] or '-'}\nWhen: {when}\nArriving: {ARR_LABEL[d['arrival_method']]}\n\n"
            + (f"Approve or decline here (no sign-in needed):\n{link}\n\nThe link works for {config.APPROVAL_DAYS} days and only for this request. Please do not share it."
               if link else "Open the Vista app and approve or decline it under Visit requests."))
    await notify(c, prop, h["holder_name"] or "Household", f"Approval link for {ref}", h["email"], body)


MIN_PHONE_DIGITS = 7
MAX_PURPOSE = 200


def require_public_fields(d) -> None:
    """What a visitor must give on the public registration form (every problem is a 422 with a plain message):
    phone, ID or photo, purpose, and the date and time of the visit. The guard's walk-in entry does not use this:
    the guard sees the person, checks the ID at the gate and the visit is happening now."""
    phone = " ".join((d.phone or "").split())
    if not phone:
        raise HTTPException(422, "Enter your phone number")
    if sum(ch.isdigit() for ch in phone) < MIN_PHONE_DIGITS:
        raise HTTPException(422, f"Enter a valid phone number (at least {MIN_PHONE_DIGITS} digits)")
    d.phone = phone
    if not (getattr(d, "id_photo", None) or "").strip():
        raise HTTPException(422, "Add your ID or a photo of yourself")
    decode_photo(d.id_photo, "ID or photo")   # a real JPEG, not too large: refused here, before anything is saved
    d.purpose = " ".join((d.purpose or "").split())
    if not d.purpose:
        raise HTTPException(422, "Enter the purpose of your visit")
    if len(d.purpose) > MAX_PURPOSE:
        raise HTTPException(422, f"Use {MAX_PURPOSE} characters or fewer for the purpose")
    if not (d.when or "").strip():
        raise HTTPException(422, "Choose the date and time of your visit")
    if not parse_when(d.when, need_time=True):
        raise HTTPException(422, "The visit date and time could not be read. Choose the date and the time again")


async def create_visit(c, cx: Ctx, d, walk_in=False) -> int:
    h, member, restricted = await match_household(c, cx.prop, d.house, d.host)
    status = "queue" if not h else ("walkin_pending" if walk_in else "pending")
    arr = ARR_CODE.get((d.arrival or "walking").strip().lower(), "walking")
    v = await c.fetchrow("INSERT INTO visits (property_id, status, qr_token) VALUES ($1,$2,$3) RETURNING id, seq",
                         cx.prop, status, secrets.token_urlsafe(9))
    await c.execute(
        """INSERT INTO village_visit_details (visit_id, property_id, household_id, host_member_id, visitor_name,
           visitor_phone, typed_house, typed_host, purpose, visit_at, arrival_method, declared_kind, declared_color,
           declared_plate, restricted_flag, walk_in, email) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)""",
        v["id"], cx.prop, h["id"] if h else None, member["id"] if member else None, d.name.strip(), d.phone.strip(),
        d.house.strip(), (d.host or "").strip(), " ".join((d.purpose or "").split()), parse_when(d.when), arr, d.kind, d.color, d.plate,
        bool(restricted), walk_in, (getattr(d, "email", "") or "").strip().lower() or None)
    id_photo = getattr(d, "id_photo", None)
    if id_photo:   # the visitor's ID or photo from the form (api.check_visit requires it for public requests; a walk-in is checked by the guard in person)
        await c.execute(
            """INSERT INTO village_id_photos (visit_id, property_id, content, delete_after)
               VALUES ($1,$2,$3, now() + make_interval(days => $4::int))""",
            v["id"], cx.prop, decode_photo(id_photo, "ID or photo"), await setting_int(c, cx.prop, 1, 5, config.PHOTO_RETENTION_DAYS, 1, 365))
    people = [(d.name.strip(), True)] + [(f.strip(), False) for f in d.friends if f.strip()]
    for i, (n, lead) in enumerate(people):
        await c.execute("INSERT INTO village_visit_people (property_id, visit_id, full_name, is_lead, sort) "
                        "VALUES ($1,$2,$3,$4,$5)", cx.prop, v["id"], n, lead, i)
    if h and not walk_in:
        await send_approval(c, cx.prop, cx.slug, v["id"], h)
    await audit(c, cx, f"{'Walk-in' if walk_in else 'Visit request'} VS-{v['seq']:04d} created", v["id"])
    return v["seq"]


async def release_badges(c, visit_id, status="avail"):
    await c.execute("""UPDATE badges SET status=$2, holder=NULL WHERE id IN
                       (SELECT badge_id FROM village_visit_people WHERE visit_id=$1 AND badge_id IS NOT NULL)""",
                    visit_id, status)


MISSING_H = """(SELECT CASE WHEN s.value->>4 ~ '^[0-9]+$' THEN (s.value->>4)::int END
                FROM settings s WHERE s.property_id=v.property_id AND s.key='tab1')"""


async def mark_missing(pool: asyncpg.Pool, simulate_hours: int = 0, prop=None) -> int:
    """Flag visits with no house scan after the gate notice (the Admin's "Missing after" hours, default MISSING_HOURS). Run by a background loop."""
    async with pool.acquire() as c, c.transaction():
        rows = await c.fetch(
            f"""WITH c AS (SELECT v.id, v.property_id, v.seq, d.visitor_name, d.gate_notified_at,
                                  GREATEST(COALESCE({MISSING_H}, $1::int), 1) AS hrs
                           FROM visits v JOIN village_visit_details d ON d.visit_id=v.id
                           WHERE v.status='at_gate' AND d.gate_notified_at IS NOT NULL AND ($3::uuid IS NULL OR v.property_id=$3))
                UPDATE visits v SET status='missing' FROM c
                WHERE v.id=c.id AND c.gate_notified_at + make_interval(hours => c.hrs) <= now() + make_interval(hours => $2::int)
                RETURNING v.id, v.property_id, v.seq, c.visitor_name, c.hrs""", config.MISSING_HOURS, simulate_hours, prop)
        for r in rows:
            await c.execute("INSERT INTO alerts (property_id, kind, detail, visit_id) VALUES ($1,'Missing',$2,$3)",
                            r["property_id"], f"VS-{r['seq']:04d} {r['visitor_name']}: no house scan {r['hrs']} hours after the gate notice", r["id"])
            if await setting(c, r["property_id"], 2, 2, True) is not False:   # "Alert guard and Admin when a visit is Missing"
                await c.execute("INSERT INTO notifications (property_id, recipient, subject) VALUES ($1,'Guard and Admin',$2)",
                                r["property_id"], f"VS-{r['seq']:04d} flagged Missing")
            await c.execute("INSERT INTO audit_log (property_id, actor, role, action, visit_id) VALUES ($1,'System','System',$2,$3)",
                            r["property_id"], f"VS-{r['seq']:04d} flagged Missing", r["id"])
    return len(rows)


async def purge_photos(pool: asyncpg.Pool) -> int:
    """Delete entry photos past their retention date (personal data). Returns how many were removed."""
    async with pool.acquire() as c:
        gone = await c.fetch("DELETE FROM village_id_photos WHERE delete_after <= now() RETURNING visit_id")
        rows = await c.fetch("DELETE FROM village_entry_photos WHERE delete_after <= now() RETURNING visit_id")
        if rows:
            await c.execute("UPDATE village_vehicle_checks SET photo_path=NULL WHERE visit_id = ANY($1::uuid[])", [r["visit_id"] for r in rows])
    return len(rows) + len(gone)


async def missing_loop(pool):
    while True:
        try:
            await mark_missing(pool)
            await purge_photos(pool)
        except Exception:
            logging.getLogger("vista").exception("background job failed")
        await asyncio.sleep(60)
