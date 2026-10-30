"""Village API. Every query filters by property_id; every state change writes an audit row."""
import re
from datetime import timedelta

import asyncpg
from uuid import UUID

import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from . import config
from .core import (ACTIVE, ARR_CODE, ARR_LABEL, MAX_PURPOSE, STATUS_LABEL, TZ, parse_when, require_public_fields, resolve_property, valid_slug, Ctx, audit, code_ok, create_visit, ctx, decode_photo, site_base, get_visit, login_limit, mark_missing, match_household,
                   need, norm_lot, account_limit, check_password_async, hash_password_async, notify, public_limit, release_badges, send_approval, session_token, setting, setting_int, sign, tx)
from .core import verify as verify_token  # the HOA route below is also called verify
from .snapshot import build_state

router = APIRouter()
NEUTRAL = {"message": "Your request was sent."}  # identical reply whatever matched


# ---------------------------------------------------------------- models
class VisitIn(BaseModel):
    # Only upper limits live here. "Is it filled in?" is decided in check_visit, so a visitor reads a plain message
    # ("Enter your phone number") and never a raw schema error ("String should have at least 1 character").
    name: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    house: str = Field(default="", max_length=40)
    host: str = ""
    purpose: str = ""
    when: str | None = None
    arrival: str = "Walking"
    kind: str = ""
    color: str = ""
    plate: str = ""
    friends: list[str] = []
    id_photo: str | None = None   # base64 JPEG of the visitor's ID or photo
    email: str = Field(default="", max_length=120)   # optional: the approved QR code is emailed here


class WalkIn(BaseModel):
    visitor: str = Field(default="", max_length=120)
    house: str = Field(default="", max_length=40)
    host: str = ""
    arr: str = "Walking"
    phone: str = ""            # optional: the guard may not have it
    purpose: str = ""
    kind: str = ""             # declared vehicle, so the gate check has something to compare with
    color: str = ""
    plate: str = ""
    friends: list[str] = []    # same group rule as the visitor form: one request, one approval, a pass for each person


class Lookup(BaseModel):
    name: str
    phone: str


class Scan(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class Session(BaseModel):
    role: str = ""
    household_lot: str | None = None
    name: str | None = None
    code: str | None = None
    invite: str | None = None   # signed household link from the invitation email
    admin_link: str | None = None   # signed link the Super Admin sends to the village Admin
    email: str | None = None        # personal account sign-in (guard, HOA office, Admin) ...
    password: str | None = None     # ... with the password the Admin or the person set


class Decision(BaseModel):
    approve: bool


class Fix(BaseModel):
    house: str
    host: str = ""


class Reject(BaseModel):
    reason: str = Field(min_length=3)


class Vehicle(BaseModel):
    photo: bool = False          # kept for older clients; the photo itself is photo_data
    photo_data: str | None = None   # base64 JPEG (or a data: URL) of the vehicle at the gate
    plate_ok: bool = False
    color_ok: bool = False
    type_ok: bool = False
    override: bool = False
    reason: str | None = None


class CheckIn(BaseModel):
    id_checked: bool
    extra_verification: bool = False
    vehicle: Vehicle | None = None


class Person(BaseModel):
    person: str | None = None      # scan out by name ...
    pass_code: str | None = None   # ... or by the pass number printed on the badge


class Left(BaseModel):
    vehicle_left: bool = False


class Close(BaseModel):
    reason: str = Field(pattern="^(Vehicle not left|Overstay|Pass not returned)$")


class StatusIn(BaseModel):
    status: str = Field(pattern="^(arrived|wrong_destination)$")


class HouseholdForm(BaseModel):   # checked by clean_household() so every problem gets a plain message
    owner: str = ""
    lot: str = ""
    holder: str = ""
    email: str = ""
    phone: str = ""
    members: list[dict] = []


class HouseholdPatch(BaseModel):
    owner: str | None = None
    lot: str | None = None
    holder: str | None = None
    email: str | None = None
    phone: str | None = None
    members: list[dict] | None = None   # the people listed; None leaves them as they are


# ---------------------------------------------------------------- public / session
def invite_link(slug: str, hid) -> str | None:
    """Signed, stateless sign-in link for one household (no extra table). None when the server cannot sign tokens."""
    if not config.SECRET_KEY:
        return None
    base = (config.FRONTEND_URL or (config.CORS_ORIGINS.split(",")[0] if config.CORS_ORIGINS else "")).strip().rstrip("/")
    tok = sign({"k": "inv", "h": str(hid), "p": slug, "e": int(time.time()) + config.INVITE_DAYS * 86400})
    return f"{base}/{slug}?invite={tok}"   # the village's own page: the path tells the site which village this is


@router.get("/property/{slug}", dependencies=[Depends(public_limit)])
async def property_page(slug: str, request: Request):
    """Public: what a village's own page needs before anyone signs in (its name). An unknown link looks the same as a wrong one."""
    r = await request.app.state.pool.fetchrow("SELECT name, slug FROM properties WHERE slug=$1 AND active", slug.lower()) if valid_slug(slug.lower()) else None
    if not r:
        raise HTTPException(404, "This village link is not valid")
    return {"name": r["name"], "slug": r["slug"]}


@router.get("/health")
async def health(request: Request):
    await request.app.state.pool.fetchval("SELECT 1")
    return {"ok": True}


MAX_GROUP = 20   # people in one request, the visitor included


def check_visit(d: VisitIn, public: bool = False) -> VisitIn:
    """The rules both forms share. Every problem is a 422 with a plain message.
    public=True is the visitor's own registration form: it must also carry the phone number, the ID or photo, the purpose
    and the date and time (core.require_public_fields). public=False is the guard's walk-in entry: name and house are
    enough, because the guard sees the person, checks the ID at the gate and the visit is happening now."""
    d.name, d.house, d.host = " ".join(d.name.split()), " ".join(d.house.split()), " ".join((d.host or "").split())
    if not d.name:
        raise HTTPException(422, "Enter the visitor's name")
    if not d.house:
        raise HTTPException(422, "Enter the house number or block and lot")
    if public:
        require_public_fields(d)
    if (d.arrival or "Walking").strip().lower() not in ARR_CODE:
        raise HTTPException(422, "Choose how the visitor is arriving: Walking, Own vehicle or Ride")
    for label, val, cap in (("person visited", d.host, 120), ("vehicle type", d.kind, 60), ("vehicle color", d.color, 40), ("plate number", d.plate, 20)):
        if len(val or "") > cap:
            raise HTTPException(422, f"The {label} is too long (at most {cap} characters)")
    if not public:
        d.purpose = " ".join((d.purpose or "").split())   # optional for a walk-in, but tidy and bounded
        if len(d.purpose) > MAX_PURPOSE:
            raise HTTPException(422, f"Use {MAX_PURPOSE} characters or fewer for the purpose")
        if d.when and d.when.strip() and not parse_when(d.when):
            raise HTTPException(422, "The visit date and time could not be read. Choose it again")
    friends, seen = [], {d.name.lower()}
    for f in d.friends:
        f = " ".join(str(f).split())
        if not f:
            continue
        if len(f) > 120:
            raise HTTPException(422, "A name in the group is too long")
        if f.lower() in seen:
            raise HTTPException(422, f"{f} is listed twice. Write each person once")
        seen.add(f.lower())
        friends.append(f)
    if len(friends) + 1 > MAX_GROUP:
        raise HTTPException(422, f"A request can include at most {MAX_GROUP} people. Send a second request for the others")
    d.friends = friends
    return d


@router.post("/visits", dependencies=[Depends(public_limit)])
async def request_visit(body: VisitIn, request: Request, cx: Ctx = Depends(ctx)):
    if body.email.strip() and not EMAIL_RE.match(body.email.strip()):
        raise HTTPException(422, "Enter a valid email address")
    check_visit(body, public=True)
    async with tx(request) as c:
        await create_visit(c, cx, body)
    return NEUTRAL


@router.get("/qr/{token}.png", dependencies=[Depends(public_limit)])
async def qr_image(token: str, request: Request):
    """The QR picture of an approved visit (used by the EmailJS template, <img src="{{qr_url}}">). The token is the secret."""
    from .mailer import qr_png
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", token):
        raise HTTPException(404, "Not found")
    st = await request.app.state.pool.fetchval("SELECT status FROM visits WHERE qr_token=$1", token)
    if st not in ("approved",) + ACTIVE:
        raise HTTPException(404, "Not found")
    return Response(qr_png(f"VISTA:{token}"), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/visits/lookup", dependencies=[Depends(public_limit)])
async def lookup(body: Lookup, request: Request, cx: Ctx = Depends(ctx)):
    digits = re.sub(r"\D", "", body.phone)
    rows = await request.app.state.pool.fetch(
        """SELECT v.seq, v.status, v.qr_token, d.typed_house, h.lot_code,
                  (SELECT l.route FROM village_lots l WHERE l.household_id=h.id AND l.property_id=v.property_id LIMIT 1) AS route,
                  to_char(COALESCE(d.visit_at, v.created_at) AT TIME ZONE $4,'Mon DD HH24:MI') AS w,
                  (SELECT count(*) FROM village_visit_people p WHERE p.visit_id=v.id) AS n
           FROM visits v JOIN village_visit_details d ON d.visit_id=v.id LEFT JOIN village_households h ON h.id=d.household_id
           WHERE v.property_id=$1 AND lower(d.visitor_name)=lower($2)
             AND regexp_replace(d.visitor_phone,'\\D','','g')=$3 ORDER BY v.seq DESC""",
        cx.prop, body.name.strip(), digits, config.TIMEZONE)
    label = {"pending": "Request sent", "queue": "Request sent", "walkin_pending": "Request sent", "rejected": "Not approved",
             "declined": "Declined", "approved": "Approved", "at_gate": "Checked in", "arrived": "Checked in",
             "missing": "Checked in", "wrong_destination": "Checked in", "left": "Visit complete", "closed": "Visit closed"}
    out = []
    for r in rows:
        item = {"house": r["typed_house"], "when": r["w"], "people": r["n"], "status": label[r["status"]]}
        if r["status"] in ("approved",) + ACTIVE:
            item["qr"] = r["qr_token"]
        if r["status"] in ACTIVE and r["lot_code"]:  # directions only after check-in, never restricted areas
            m = re.fullmatch(r"B(\d+)-L(\d+)", r["lot_code"], re.I)   # a lot that is not B<n>-L<n> gets directions only if the Admin wrote them
            if r["route"]:
                item["directions"] = r["route"]
            elif m:
                item["directions"] = f"Main gate, Village Road, Block {m.group(1)}, Lot {m.group(2)}"
        out.append(item)
    return out


@router.post("/visits/scan")
async def scan_visit(body: Scan, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    """Gate: find the visit for a scanned QR code. Accepts the QR text (VISTA:<token>), the bare token, or a VS-0001 reference.
    Read-only: it only says which visit and status the code belongs to. Check-in still goes through the gate checks."""
    code = body.code.strip()
    if code.upper().startswith("VISTA:"):
        code = code[6:].strip()
    m = re.fullmatch(r"(?i)VS-(\d+)", code)
    q = """SELECT v.seq, v.status, d.visitor_name, d.typed_house,
                  (SELECT count(*) FROM village_visit_people p WHERE p.visit_id=v.id) AS n
           FROM visits v JOIN village_visit_details d ON d.visit_id=v.id
           WHERE v.property_id=$1 AND """ + ("v.seq=$2" if m else "v.qr_token=$2")
    r = await request.app.state.pool.fetchrow(q, cx.prop, int(m.group(1)) if m else code)
    if not r:
        raise HTTPException(404, "No visit matches that QR code")
    return {"ref": f"VS-{r['seq']:04d}", "status": STATUS_LABEL[r["status"]], "visitor": r["visitor_name"],
            "house": r["typed_house"], "people": r["n"]}


@router.get("/config")
async def public_config():
    return {"code_required": bool(config.STAFF_ACCESS_CODE and config.STAFF_CODE_LOGIN), "accounts": bool(config.SECRET_KEY), "auth_mode": "code" if config.STAFF_ACCESS_CODE else config.AUTH_MODE}


@router.get("/dev/households", dependencies=[Depends(login_limit)])
async def dev_households(request: Request, x_access_code: str | None = Header(None), cx: Ctx = Depends(ctx)):
    """Sign-in helper: household choices. Needs the staff access code when one is set."""
    if config.STAFF_ACCESS_CODE:
        if not code_ok(x_access_code):
            raise HTTPException(403, "Enter the staff access code first")
    elif config.AUTH_MODE != "dev":
        raise HTTPException(404)
    rows = await request.app.state.pool.fetch(
        "SELECT lot_code, holder_name FROM village_households WHERE property_id=$1 AND status<>'invited' ORDER BY lot_code", cx.prop)
    return [{"lot": r["lot_code"], "holder": r["holder_name"]} for r in rows]


async def prop_info(request: Request, cx: Ctx) -> dict:
    r = await request.app.state.pool.fetchrow("SELECT name, slug FROM properties WHERE id=$1", cx.prop)
    return {"name": r["name"], "slug": r["slug"]}


@router.post("/session", dependencies=[Depends(login_limit)])
async def session(body: Session, request: Request, x_property: str | None = Header(None)):
    """Staff sign-in. With STAFF_ACCESS_CODE set the code is checked and a signed token is returned.
    Without it (dev mode) nothing is checked and the UI just sends role headers."""
    cx = None
    if not body.admin_link:   # the Admin link names its own village; every other sign-in uses the village page it came from
        slug = (x_property or config.DEFAULT_PROPERTY).lower()
        cx = Ctx((await resolve_property(request.app.state.pool, slug))["id"], slug, None, None)
    if body.admin_link:  # the village Admin signs in with the link the Super Admin sent: this is the assigned Admin account
        if not config.SECRET_KEY:
            raise HTTPException(400, "Sign-in links need SECRET_KEY on the server")
        tok = verify_token(body.admin_link)
        if not tok or tok.get("k") != "adm":
            raise HTTPException(401, "This link is invalid or has expired. Ask the platform administrator for a new one.")
        u = await request.app.state.pool.fetchrow(
            """SELECT u.id AS uid, u.name, u.vista_token_version AS v, p.id AS pid, p.slug, p.name AS pname, p.active
               FROM users u JOIN properties p ON p.id=u.property_id
               WHERE u.id=$1 AND u.role='admin' AND u.active AND p.slug=$2""", UUID(tok["u"]), tok["p"])
        if not u:
            raise HTTPException(401, "This link is no longer valid. The Admin may have been changed. Ask the platform administrator.")
        if u["v"] != int(tok.get("v") or 0):   # the Admin has set or changed a password since this link was made: it is spent
            raise HTTPException(401, "This link has already been replaced by a password. Sign in with your email and password, or ask the platform administrator for a new link.")
        if not u["active"]:
            raise HTTPException(403, "This village is switched off. Please contact the platform administrator.")
        async with tx(request) as c:
            await audit(c, Ctx(u["pid"], u["slug"], "admin", u["name"]), "Signed in with the Admin link")
        t = session_token("admin", u["name"], u["slug"], uid=u["uid"], version=u["v"])
        return {"role": "admin", "name": u["name"], "household_lot": None, "token": t, "property": {"name": u["pname"], "slug": u["slug"]}}
    if body.email:   # a person signs in as themselves: their own account, their own role
        if not config.SECRET_KEY:
            raise HTTPException(400, "Personal sign-in needs SECRET_KEY on the server")
        account_limit(request, body.email)
        u = await request.app.state.pool.fetchrow(
            "SELECT id, name, role, active, password_hash, vista_token_version AS v FROM users WHERE property_id=$1 AND lower(email)=lower($2) AND role IN ('admin','guard','hoa')",
            cx.prop, body.email.strip())
        ok = await check_password_async(body.password or "", u["password_hash"] if u else None)
        if not (u and ok and u["active"]):
            raise HTTPException(401, "Wrong email or password")
        async with tx(request) as c:
            await audit(c, Ctx(cx.prop, cx.slug, u["role"], u["name"]), "Signed in")
        t = session_token(u["role"], u["name"], cx.slug, uid=u["id"], version=u["v"])
        return {"role": u["role"], "name": u["name"], "household_lot": None, "token": t, "property": await prop_info(request, cx)}
    if body.invite:  # a household signs in with its own link, no staff code
        if not (config.STAFF_ACCESS_CODE and config.SECRET_KEY):
            raise HTTPException(400, "Invitation links need STAFF_ACCESS_CODE and SECRET_KEY on the server")
        tok = verify_token(body.invite)
        if not tok or tok.get("k") != "inv" or tok.get("p") != cx.slug:
            raise HTTPException(401, "This link is invalid or has expired. Ask the Admin for a new one.")
        h = await request.app.state.pool.fetchrow(
            "SELECT id, lot_code, holder_name FROM village_households WHERE property_id=$1 AND id=$2", cx.prop, UUID(tok["h"]))
        if not h:
            raise HTTPException(401, "This household no longer exists")
        name = h["holder_name"]
        async with tx(request) as c:
            await audit(c, Ctx(cx.prop, cx.slug, "household", name), "Signed in with invitation link")
        t = sign({"r": "household", "n": name, "h": str(h["id"]), "p": cx.slug, "e": int(time.time()) + config.SESSION_HOURS * 3600})
        return {"role": "household", "name": name, "household_lot": None if h["lot_code"] == "-" else h["lot_code"], "token": t,
                "property": await prop_info(request, cx)}
    if config.STAFF_ACCESS_CODE:
        if not config.SECRET_KEY:
            raise HTTPException(500, "SECRET_KEY is not set on the server")
        if not config.STAFF_CODE_LOGIN:
            raise HTTPException(403, "Sign in with your own email and password")
        if not code_ok(body.code):
            raise HTTPException(401, "Wrong access code")
    elif config.AUTH_MODE != "dev":
        raise HTTPException(501)
    if body.role not in ("admin", "guard", "hoa", "household"):
        raise HTTPException(422, "Unknown role")
    name, hid = body.name, None
    if body.role == "household":
        h = await request.app.state.pool.fetchrow(
            "SELECT id, holder_name FROM village_households WHERE property_id=$1 AND lower(lot_code)=lower($2) AND status<>'invited'",
            cx.prop, body.household_lot or "")
        if not h:
            raise HTTPException(422, "Choose a household")
        name, hid = name or h["holder_name"], str(h["id"])
    name = name or {"admin": "Village Admin", "guard": "Ramon Dela Cruz", "hoa": "HOA desk"}.get(body.role)
    async with tx(request) as c:
        await audit(c, Ctx(cx.prop, cx.slug, body.role, name), "Signed in")
    out = {"role": body.role, "name": name, "household_lot": body.household_lot, "property": await prop_info(request, cx)}
    if config.STAFF_ACCESS_CODE:
        out["token"] = session_token(body.role, name, cx.slug, hid=hid, code=True)
    return out


@router.post("/cron/missing")
async def cron_missing(request: Request, key: str = ""):
    """For a free host that sleeps: an external cron (cron-job.org, Render cron) calls this every few minutes."""
    import hmac as _h
    if not config.CRON_KEY or not _h.compare_digest(key.encode(), config.CRON_KEY.encode()):
        raise HTTPException(403, "Bad key")
    return {"flagged": await mark_missing(request.app.state.pool)}


@router.get("/state")
async def state(request: Request, cx: Ctx = Depends(need("admin", "guard", "hoa", "household"))):
    return await build_state(request.app.state.pool, cx)


# ---------------------------------------------------------------- household decisions
async def email_qr(c, cx: Ctx, v, ref: str):
    """When a request is approved, email the QR code to (1) the visitor, if they gave an email and the Admin has
    'Email QR codes to visitors' on, and (2) the household's account holder, so they have a copy too."""
    code = f"VISTA:{v['qr_token']}"
    base = site_base()
    again = f"You can also see your QR code again at {base}/{cx.slug} under Retrieve your QR pass, using your name and phone number." if base else ""
    when = v["visit_at"].astimezone(TZ).strftime("%b %d, %H:%M") if v["visit_at"] else None
    if (v["email"] or "").strip() and await setting(c, cx.prop, 2, 3, True) is not False:   # "Email QR codes to visitors"
        await notify(c, cx.prop, v["visitor_name"], f"Your visit QR code for {ref}", v["email"],
                     f"Good news: your visit {ref} was approved.\n\nShow this QR code at the gate. If the picture does not show, give the guard this code: {code}\n\n" + again, code)
    if v["household_id"]:
        h = await c.fetchrow("SELECT holder_name, email FROM village_households WHERE id=$1 AND property_id=$2", v["household_id"], cx.prop)
        if h and (h["email"] or "").strip():
            await notify(c, cx.prop, h["holder_name"] or "Household", f"Approved: {v['visitor_name']} ({ref}), QR code", h["email"],
                         f"You approved {v['visitor_name']}'s visit {ref}" + (f" ({when})" if when else "") + ".\n\n"
                         f"This is the visit's QR code. The visitor shows it at the gate. If the picture does not show, the code is: {code}", code)


async def do_decision(c, cx: Ctx, v, ref: str, approve: bool, how: str = ""):
    """The household's answer to a request. Used by the app and by the link in the email, so both follow the same rules."""
    if v["status"] != "pending":
        raise HTTPException(409, "This request is no longer waiting for approval")
    if cx.role == "household":
        st = await c.fetchval("SELECT status FROM village_households WHERE id=$1 AND property_id=$2", cx.hid, cx.prop)
        if st != "verified":
            raise HTTPException(403, "Your household is not verified by the HOA office yet")
    new = "approved" if approve else "declined"
    await c.execute("UPDATE visits SET status=$1 WHERE id=$2", new, v["id"])
    if approve:
        await email_qr(c, cx, v, ref)
    await audit(c, cx, f"{'Approved' if approve else 'Declined'} {ref}{how}", v["id"])
    return new


async def do_not_for_me(c, cx: Ctx, v, ref: str, how: str = ""):
    if v["status"] != "pending":
        raise HTTPException(409, "This request is no longer waiting for approval")
    await c.execute("UPDATE village_visit_details SET household_id=NULL, host_member_id=NULL, restricted_flag=false WHERE visit_id=$1", v["id"])
    await c.execute("UPDATE visits SET status='queue' WHERE id=$1", v["id"])
    await audit(c, cx, f"Not for me: {ref} sent to the HOA queue{how}", v["id"])


@router.post("/visits/{ref}/decision")
async def decision(ref: str, body: Decision, request: Request, cx: Ctx = Depends(need("household", "admin"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        new = await do_decision(c, cx, v, ref, body.approve)
    return {"status": new}


@router.post("/visits/{ref}/not-for-me")
async def not_for_me(ref: str, request: Request, cx: Ctx = Depends(need("household"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        await do_not_for_me(c, cx, v, ref)
    return {"status": "queue"}


# ---------------------------------------------------------------- household approval by the link in the email
class LinkAnswer(BaseModel):
    action: str = Field(pattern="^(approve|decline|not_for_me)$")


async def link_target(c, cx: Ctx, tok: str, lock: bool = False):
    """Check the email link and return (household context, visit row, ref). The link only ever opens its own request, in its own village."""
    t = verify_token(tok)
    if not t or t.get("k") != "apr" or t.get("p") != cx.slug:
        raise HTTPException(401, "This link is invalid or has expired. Ask the visitor to send a new request, or sign in to the app.")
    h = await c.fetchrow("SELECT id, lot_code, holder_name FROM village_households WHERE id=$1 AND property_id=$2", UUID(t["h"]), cx.prop)
    seq = await c.fetchval("SELECT seq FROM visits WHERE id=$1 AND property_id=$2", UUID(t["v"]), cx.prop)
    if not h or not seq:
        raise HTTPException(404, "This request no longer exists")
    hx = Ctx(cx.prop, cx.slug, "household", h["holder_name"], h["id"], h["lot_code"])
    ref = f"VS-{seq:04d}"
    try:
        v = await get_visit(c, hx, ref, lock=lock)
    except HTTPException:   # "Not for me" or a correction moved it to another household
        raise HTTPException(410, "This request is not for your household any more. Nothing more to do.")
    return hx, v, ref


@router.get("/approval/{tok}", dependencies=[Depends(public_limit)])
async def approval_info(tok: str, request: Request, cx: Ctx = Depends(ctx)):
    """What the confirmation page shows. Only what the household needs to decide; never restricted-area details."""
    async with request.app.state.pool.acquire() as c:
        hx, v, ref = await link_target(c, cx, tok)
        people = [r["full_name"] for r in await c.fetch("SELECT full_name FROM village_visit_people WHERE visit_id=$1 ORDER BY sort", v["id"])]
        verified = await c.fetchval("SELECT status='verified' FROM village_households WHERE id=$1", hx.hid)
        village = await c.fetchval("SELECT name FROM properties WHERE id=$1", cx.prop)
        when = v["visit_at"].astimezone(TZ).strftime("%b %d, %H:%M") if v["visit_at"] else ""
    return {"ref": ref, "village": village, "visitor": v["visitor_name"], "people": people, "purpose": v["purpose"] or "", "when": when,
            "visiting": v["typed_host"] or "Any household member", "arrival": ARR_LABEL[v["arrival_method"]],
            "status": STATUS_LABEL[v["status"]], "can_decide": v["status"] == "pending" and bool(verified), "verified": bool(verified)}


@router.post("/approval/{tok}", dependencies=[Depends(public_limit)])
async def approval_answer(tok: str, body: LinkAnswer, request: Request, cx: Ctx = Depends(ctx)):
    async with tx(request) as c:
        hx, v, ref = await link_target(c, cx, tok, lock=True)
        if body.action == "not_for_me":
            await do_not_for_me(c, hx, v, ref, " (email link)")
            return {"status": "queue"}
        new = await do_decision(c, hx, v, ref, body.action == "approve", " (email link)")
    return {"status": new}


@router.post("/passes/{code}/arrived")
async def arrived(code: str, request: Request, cx: Ctx = Depends(need("household"))):
    """Resident scans the pass at the house. A pass from another household is flagged as a wrong destination."""
    async with tx(request) as c:
        r = await c.fetchrow(
            """SELECT pe.id, pe.visit_id, pe.full_name, v.seq, v.status, d.household_id FROM village_visit_people pe
               JOIN badges b ON b.id=pe.badge_id JOIN visits v ON v.id=pe.visit_id
               JOIN village_visit_details d ON d.visit_id=v.id
               WHERE pe.property_id=$1 AND b.code=$2 AND v.status IN ('at_gate','arrived','missing') FOR UPDATE OF v""", cx.prop, code)
        if not r:
            raise HTTPException(404, "That pass is not active")
        ref = f"VS-{r['seq']:04d}"
        if r["household_id"] != cx.hid:
            await c.execute("UPDATE visits SET status='wrong_destination' WHERE id=$1", r["visit_id"])
            await c.execute("INSERT INTO alerts (property_id, kind, detail, visit_id) VALUES ($1,'Wrong destination',$2,$3)",
                            cx.prop, f"{ref} pass {code} scanned at the wrong household", r["visit_id"])
            await audit(c, cx, f"Wrong destination on {ref}", r["visit_id"])
            return {"flag": "wrong_destination"}
        await c.execute("UPDATE village_visit_people SET arrived_at=COALESCE(arrived_at, now()) WHERE id=$1", r["id"])
        left = await c.fetchval("SELECT count(*) FROM village_visit_people WHERE visit_id=$1 AND arrived_at IS NULL", r["visit_id"])
        if left == 0:
            await c.execute("UPDATE visits SET status='arrived' WHERE id=$1", r["visit_id"])
        if await setting(c, cx.prop, 2, 1, True) is not False:   # "Notify the guard when a visitor arrives at the house"
            await notify(c, cx.prop, "Guard", f"{ref}: {r['full_name']} arrived at the house" + (" (everyone has arrived)" if left == 0 else ""))
        await audit(c, cx, f"Arrival scan on {ref}", r["visit_id"])
    return {"arrived": True}


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_contact(email: str, phone: str) -> tuple[str, str]:
    """The account holder's email (approval links go there) and phone (the guard calls it for walk-ins) are both required."""
    email, phone = (email or "").strip(), (phone or "").strip()
    if not email:
        raise HTTPException(422, "Enter the account holder's email address")
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address")
    if not phone:
        raise HTTPException(422, "Enter the account holder's phone number")
    if not 7 <= len(re.sub(r"\D", "", phone)) <= 15:
        raise HTTPException(422, "Enter a valid phone number")
    return email, phone


def clean_members(raw: list[dict]) -> list[dict]:
    members, seen = [], set()
    for m in raw:
        n = " ".join(str(m.get("n") or "").split())
        if n and n.lower() not in seen:
            seen.add(n.lower())
            members.append({"n": n[:120], "minor": bool(m.get("minor"))})
    return members


def clean_household(body: HouseholdForm) -> dict:
    """Validate the household form. Every problem is a 422 with a message the person can act on."""
    owner, holder = " ".join(body.owner.split()), " ".join(body.holder.split())
    if not owner:
        raise HTTPException(422, "Enter the owner name")
    if not holder:
        raise HTTPException(422, "Enter the account holder's name")
    lot = norm_lot(body.lot)
    if not lot:
        raise HTTPException(422, "Enter the block and lot (like B1-L4) or the house number")
    email, phone = check_contact(body.email, body.phone)
    members = clean_members(body.members)
    if not members:
        raise HTTPException(422, "List the people living here (at least the account holder)")
    me = next((m for m in members if m["n"].lower() == holder.lower()), None)
    if not me:
        raise HTTPException(422, "The account holder must be one of the people listed")
    if me["minor"]:
        raise HTTPException(422, "The account holder must be an adult")
    return {"owner": owner, "holder": holder, "lot": lot, "email": email, "phone": phone, "members": members}


@router.put("/me/household")
async def household_form(body: HouseholdForm, request: Request, cx: Ctx = Depends(need("household"))):
    f = clean_household(body)
    async with tx(request) as c:
        cur = await c.fetchrow("SELECT lot_code, status FROM village_households WHERE id=$1 AND property_id=$2 FOR UPDATE", cx.hid, cx.prop)
        dup = await c.fetchval("SELECT 1 FROM village_households WHERE property_id=$1 AND lower(lot_code)=lower($2) AND id<>$3",
                               cx.prop, f["lot"], cx.hid)
        if dup:
            raise HTTPException(409, "That lot already belongs to another household")
        status = "awaiting" if cur["status"] == "invited" else cur["status"]
        moved = cur["status"] == "verified" and (cur["lot_code"] or "").lower() != f["lot"].lower()
        if moved:   # a different lot is a different household to the HOA: it must be verified again
            status = "awaiting"
        await c.execute("""UPDATE village_households SET owner_name=$3, lot_code=$4, holder_name=$5, email=$6, phone=$7, status=$8,
                           verified_at=CASE WHEN $9 THEN NULL ELSE verified_at END, verified_by=CASE WHEN $9 THEN NULL ELSE verified_by END
                           WHERE id=$1 AND property_id=$2""",
                        cx.hid, cx.prop, f["owner"], f["lot"], f["holder"], f["email"], f["phone"], status, moved)
        await sync_members(c, cx, cx.hid, f["members"])
        await link_lot(c, cx.prop, f["lot"], cx.hid)
        await audit(c, cx, f"Household form saved for {f['owner']}" + (f" (lot changed to {f['lot']}, needs HOA verification again)" if moved else ""))
    return {"ok": True, "status": status, "reverify": moved}


async def sync_members(c, cx, hid, members):
    """Keep existing members (and their restricted-area ties) by name; add new ones; remove the rest."""
    want = {(m.get("n") or "").strip(): bool(m.get("minor")) for m in members if (m.get("n") or "").strip()}
    have = {r["full_name"]: r for r in await c.fetch("SELECT id, full_name FROM village_members WHERE household_id=$1", hid)}
    for n, r in have.items():
        if n not in want:
            await c.execute("DELETE FROM village_members WHERE id=$1", r["id"])
    for n, minor in want.items():
        if n in have:
            await c.execute("UPDATE village_members SET is_minor=$2 WHERE id=$1", have[n]["id"], minor)
        else:
            await c.execute("INSERT INTO village_members (property_id, household_id, full_name, is_minor) VALUES ($1,$2,$3,$4)",
                            cx.prop, hid, n, minor)


async def link_lot(c, prop, lot, hid):
    await c.execute("UPDATE village_lots SET household_id=NULL WHERE property_id=$1 AND household_id=$2 AND lower(lot_code)<>lower($3)", prop, hid, lot)
    await c.execute("""INSERT INTO village_lots (property_id, lot_code, household_id) VALUES ($1,$2,$3)
                       ON CONFLICT (property_id, lower(lot_code)) DO UPDATE SET household_id=EXCLUDED.household_id""", prop, lot, hid)


# ---------------------------------------------------------------- HOA
@router.post("/households/{hid}/verify")
async def verify(hid: UUID, request: Request, cx: Ctx = Depends(need("hoa", "admin"))):
    async with tx(request) as c:
        if cx.role == "hoa" and await setting(c, cx.prop, 1, 1, "HOA office") == "Admin":   # Settings > Who verifies households
            raise HTTPException(403, "In this village the Admin verifies households")
        h = await c.fetchrow("SELECT lot_code, owner_name, holder_name, status FROM village_households WHERE id=$1 AND property_id=$2 FOR UPDATE",
                             hid, cx.prop)
        if not h:
            raise HTTPException(404, "Household not found")
        if h["status"] == "verified":
            raise HTTPException(409, "This household is already verified")
        if not norm_lot(h["lot_code"]):
            raise HTTPException(422, "The household form must be complete before it can be verified: block and lot or house number is missing")
        people = await c.fetch("SELECT full_name, is_minor FROM village_members WHERE household_id=$1", hid)
        if not people:
            raise HTTPException(422, "The household form must be complete before it can be verified: no people are listed")
        if not any(not p["is_minor"] and p["full_name"].lower() == (h["holder_name"] or "").lower() for p in people):
            raise HTTPException(422, "The account holder must be listed among the people, as an adult")
        hc = await c.fetchrow("SELECT email, phone FROM village_households WHERE id=$1", hid)
        if not (hc["email"] or "").strip() or not (hc["phone"] or "").strip():
            raise HTTPException(422, "The household form must be complete before it can be verified: the account holder's email and phone are missing")
        await c.execute("UPDATE village_households SET status='verified', verified_at=now(), verified_by=$3 WHERE id=$1 AND property_id=$2",
                        hid, cx.prop, cx.name)
        await audit(c, cx, f"Verified household {h['lot_code']}")
    return {"ok": True}


@router.post("/visits/{ref}/resend")
async def resend(ref: str, body: Fix, request: Request, cx: Ctx = Depends(need("hoa", "admin"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] not in ("queue", "pending", "walkin_pending"):
            raise HTTPException(409, "This visit can no longer be corrected")
        h, member, restricted = await match_household(c, cx.prop, body.house, body.host)
        if not h:
            raise HTTPException(422, "Still no match for that house and person")
        new = "pending" if v["status"] == "queue" and not v["walk_in"] else ("walkin_pending" if v["walk_in"] else v["status"])
        await c.execute("""UPDATE village_visit_details SET household_id=$2, host_member_id=$3, typed_house=$4, typed_host=$5,
                           restricted_flag=$6 WHERE visit_id=$1""", v["id"], h["id"], member["id"] if member else None,
                        body.house.strip(), body.host.strip(), bool(restricted))
        await c.execute("UPDATE visits SET status=$2 WHERE id=$1", v["id"], new)
        await send_approval(c, cx.prop, cx.slug, v["id"], h)
        await audit(c, cx, f"Corrected and resent {ref}", v["id"])
    return {"status": new}


@router.post("/visits/{ref}/reject")
async def reject(ref: str, body: Reject, request: Request, cx: Ctx = Depends(need("hoa", "admin"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] not in ("queue", "pending"):
            raise HTTPException(409, "This visit can no longer be rejected")
        await c.execute("UPDATE visits SET status='rejected' WHERE id=$1", v["id"])
        await c.execute("UPDATE village_visit_details SET reject_reason=$2 WHERE visit_id=$1", v["id"], body.reason)
        await audit(c, cx, f"Rejected {ref}: {body.reason}", v["id"])
    return {"status": "rejected"}


# ---------------------------------------------------------------- guard
@router.post("/walkins")
async def walkin(body: WalkIn, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    if body.phone.strip() and len(body.phone.strip()) < 3:   # optional for a walk-in, but a number the guard did type must be usable
        raise HTTPException(422, "The phone number is not valid")
    try:
        d = VisitIn(name=body.visitor, phone=body.phone.strip() or "walk-in", house=body.house, host=body.host, purpose=body.purpose,
                    arrival=body.arr, kind=body.kind, color=body.color, plate=body.plate, friends=body.friends)
    except ValidationError as e:   # e.g. a phone number that is too short: a plain 422, not a server error
        bad = e.errors()[0]
        field = {"phone": "phone number", "name": "visitor name", "house": "house"}.get(str(bad["loc"][-1]), str(bad["loc"][-1]))
        raise HTTPException(422, f"The {field} is not valid")
    check_visit(d, public=False)   # guard-created: no ID photo, date or phone required
    async with tx(request) as c:
        seq = await create_visit(c, cx, d, walk_in=True)
    return {"ref": f"VS-{seq:04d}"}


@router.post("/visits/{ref}/walkin-decision")
async def walkin_decision(ref: str, body: Decision, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] != "walkin_pending":
            raise HTTPException(409, "Not a walk-in waiting for the household")
        new = "approved" if body.approve else "declined"
        await c.execute("UPDATE visits SET status=$2 WHERE id=$1", v["id"], new)
        await audit(c, cx, f"Household {'approved' if body.approve else 'declined'} walk-in {ref} by phone", v["id"])
    return {"status": new}


@router.post("/visits/{ref}/check-in")
async def check_in(ref: str, body: CheckIn, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    """ID check, red-flag verification, vehicle check, then one pass per person."""
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] != "approved":
            raise HTTPException(409, "Visit is not approved and waiting at the gate")
        if not body.id_checked:
            raise HTTPException(422, "Check the visitor's ID first")
        if v["restricted_flag"] and not body.extra_verification:
            raise HTTPException(422, "Red flag: extra verification is required")
        if v["arrival_method"] == "own_vehicle":
            vh = body.vehicle
            if not vh:
                raise HTTPException(422, "Take the entry photo for the vehicle check")
            img = decode_photo(vh.photo_data)
            keep_days = await setting_int(c, cx.prop, 1, 5, config.PHOTO_RETENTION_DAYS, 1, 365)   # Admin's entry photo retention
            mismatch = not (vh.plate_ok and vh.color_ok and vh.type_ok)
            if mismatch and not (vh.override and (vh.reason or "").strip()):
                raise HTTPException(409, "Vehicle mismatch: override with a reason to continue")
            await c.execute(
                """INSERT INTO village_vehicle_checks (visit_id, property_id, photo_path, plate_ok, color_ok, type_ok,
                   override_used, override_reason, checked_by, delete_after)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, now() + make_interval(days => $10::int))
                   ON CONFLICT (visit_id) DO UPDATE SET plate_ok=EXCLUDED.plate_ok, color_ok=EXCLUDED.color_ok,
                   type_ok=EXCLUDED.type_ok, override_used=EXCLUDED.override_used, override_reason=EXCLUDED.override_reason""",
                v["id"], cx.prop, f"entry-photos/{v['id']}.jpg", vh.plate_ok, vh.color_ok, vh.type_ok,
                mismatch and vh.override, vh.reason, cx.name, keep_days)
            await c.execute(
                """INSERT INTO village_entry_photos (visit_id, property_id, content, delete_after)
                   VALUES ($1,$2,$3, now() + make_interval(days => $4::int))
                   ON CONFLICT (visit_id) DO UPDATE SET content=EXCLUDED.content, delete_after=EXCLUDED.delete_after""",
                v["id"], cx.prop, img, keep_days)
            if mismatch:
                await audit(c, cx, f"Vehicle mismatch override on {ref}: {vh.reason}", v["id"])
        people = await c.fetch("SELECT id, full_name FROM village_visit_people WHERE visit_id=$1 ORDER BY sort", v["id"])
        badges = await c.fetch("SELECT id, code FROM badges WHERE property_id=$1 AND status='avail' ORDER BY code LIMIT $2 FOR UPDATE SKIP LOCKED",
                               cx.prop, len(people))
        if len(badges) < len(people):
            raise HTTPException(409, "Not enough passes available")
        for p, b in zip(people, badges):
            await c.execute("UPDATE badges SET status='issued', holder=$2 WHERE id=$1", b["id"], p["full_name"])
            await c.execute("UPDATE village_visit_people SET badge_id=$2 WHERE id=$1", p["id"], b["id"])
        await c.execute("UPDATE visits SET status='at_gate' WHERE id=$1", v["id"])
        await c.execute("UPDATE village_visit_details SET gate_notified_at=now() WHERE visit_id=$1", v["id"])
        h = await c.fetchrow("SELECT holder_name, email FROM village_households WHERE id=$1", v["household_id"])
        if h and await setting(c, cx.prop, 2, 0, True) is not False:   # "Notify the household when a visitor enters"
            await notify(c, cx.prop, h["holder_name"] or "Household", f"{v['visitor_name']} entered the village", h["email"])
        await audit(c, cx, f"Passes issued for {ref} ({len(people)})", v["id"])
    return {"passes": [b["code"] for b in badges], "note": "Open the barrier by hand. Scans are records only."}


@router.get("/visits/{ref}/id-photo")
async def id_photo(ref: str, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    async with request.app.state.pool.acquire() as c:
        v = await get_visit(c, cx, ref)
        r = await c.fetchrow("SELECT content, content_type FROM village_id_photos WHERE visit_id=$1 AND property_id=$2", v["id"], cx.prop)
    if not r:
        raise HTTPException(404, "No ID photo on file")
    return Response(bytes(r["content"]), media_type=r["content_type"], headers={"Cache-Control": "private, no-store"})


@router.get("/visits/{ref}/entry-photo")
async def entry_photo(ref: str, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    async with request.app.state.pool.acquire() as c:
        v = await get_visit(c, cx, ref)
        r = await c.fetchrow("SELECT content, content_type FROM village_entry_photos WHERE visit_id=$1", v["id"])
    if not r:
        raise HTTPException(404, "No entry photo on file")
    return Response(bytes(r["content"]), media_type=r["content_type"], headers={"Cache-Control": "private, no-store"})


@router.post("/visits/{ref}/exit-scan")
async def exit_scan(ref: str, body: Person, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    """Scan one person out, by the pass number on their badge or by name."""
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] not in ACTIVE:
            raise HTTPException(409, "Visitor is not inside")
        if body.pass_code and body.pass_code.strip():
            row = await c.fetchrow("""SELECT p.id, p.full_name, p.left_at FROM village_visit_people p JOIN badges b ON b.id=p.badge_id
                                      WHERE p.visit_id=$1 AND lower(b.code)=lower($2)""", v["id"], body.pass_code.strip())
            if not row:
                raise HTTPException(404, "That pass is not on this visit")
        elif body.person and body.person.strip():
            row = await c.fetchrow("SELECT id, full_name, left_at FROM village_visit_people WHERE visit_id=$1 AND full_name=$2 ORDER BY left_at NULLS FIRST LIMIT 1",
                                   v["id"], body.person)
            if not row:
                raise HTTPException(404, "Person not in this visit")
        else:
            raise HTTPException(422, "Scan a pass or choose a person")
        if row["left_at"] is None:
            await c.execute("UPDATE village_visit_people SET left_at=now() WHERE id=$1", row["id"])
            await audit(c, cx, f"Exit scan on {ref}: {row['full_name']}", v["id"])
    return {"ok": True, "person": row["full_name"], "already": row["left_at"] is not None}


@router.post("/visits/{ref}/left")
async def mark_left(ref: str, body: Left, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] not in ACTIVE:
            raise HTTPException(409, "Visitor is not inside")
        if cx.role == "guard":
            if await c.fetchval("SELECT count(*) FROM village_visit_people WHERE visit_id=$1 AND left_at IS NULL", v["id"]):
                raise HTTPException(409, "Not everyone has been scanned out")
            if v["arrival_method"] == "own_vehicle" and not body.vehicle_left:
                raise HTTPException(422, "Confirm the vehicle left")
        await c.execute("UPDATE village_visit_people SET left_at=COALESCE(left_at, now()) WHERE visit_id=$1", v["id"])
        await release_badges(c, v["id"])
        await c.execute("UPDATE village_visit_details SET vehicle_left=$2 WHERE visit_id=$1", v["id"], body.vehicle_left or v["arrival_method"] != "own_vehicle")
        await c.execute("UPDATE visits SET status='left' WHERE id=$1", v["id"])
        await audit(c, cx, f"Visit {ref} left, passes returned", v["id"])
    return {"status": "left"}


@router.post("/visits/{ref}/close")
async def close(ref: str, body: Close, request: Request, cx: Ctx = Depends(need("guard", "admin"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] not in ACTIVE:
            raise HTTPException(409, "Visitor is not inside")
        if body.reason == "Pass not returned":   # people already scanned out handed their pass back; only the others are lost
            await c.execute("""UPDATE badges b SET status=CASE WHEN p.left_at IS NULL THEN 'lost' ELSE 'avail' END,
                               holder=CASE WHEN p.left_at IS NULL THEN b.holder ELSE NULL END
                               FROM village_visit_people p WHERE p.badge_id=b.id AND p.visit_id=$1""", v["id"])
        else:
            await release_badges(c, v["id"])
        await c.execute("UPDATE village_visit_details SET close_reason=$2 WHERE visit_id=$1", v["id"], body.reason)
        await c.execute("UPDATE visits SET status='closed' WHERE id=$1", v["id"])
        await c.execute("INSERT INTO alerts (property_id, kind, detail, status, visit_id) VALUES ($1,'Visit closed',$2,'resolved',$3)",
                        cx.prop, f"{ref} closed: {body.reason}", v["id"])
        await audit(c, cx, f"Closed {ref}: {body.reason}", v["id"])
    return {"status": "closed"}


@router.post("/visits/{ref}/status")
async def set_status(ref: str, body: StatusIn, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        v = await get_visit(c, cx, ref, lock=True)
        if v["status"] not in ACTIVE:
            raise HTTPException(409, "Visitor is not inside")
        await c.execute("UPDATE visits SET status=$2 WHERE id=$1", v["id"], body.status)
        await audit(c, cx, f"Marked {ref} {body.status.replace('_', ' ')}", v["id"])
    return {"status": body.status}


@router.post("/jobs/missing")
async def run_missing(request: Request, simulate_hours: int = 0, cx: Ctx = Depends(need("guard", "admin"))):
    """simulate_hours lets the demo 'advance the clock'. The real scheduler runs this with 0 every minute."""
    # Advancing the clock is a demo tool. On a published site (staff code set) it would let any guard flag real visitors Missing.
    sim = 0 if config.STAFF_ACCESS_CODE else min(max(simulate_hours, 0), 48)
    n = await mark_missing(request.app.state.pool, sim, cx.prop)
    return {"flagged": n}


# ---------------------------------------------------------------- admin setup
class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)


def invite_mail(link: str | None, village: str) -> str:
    return (f"You have been invited to set up your household in {village}.\n\nOpen this link, fill in the household form, "
            f"and wait for the HOA office to verify it:\n{link}\n\nThe link is personal. Please do not share it." if link
            else f"You have been invited to set up your household in {village}. The Admin will send you your sign-in link.")


@router.post("/households/invite")
async def invite(body: InviteIn, request: Request, cx: Ctx = Depends(need("admin"))):
    if not EMAIL_RE.match(body.email.strip()):
        raise HTTPException(422, "Enter a valid email address")
    async with tx(request) as c:
        if await c.fetchval("SELECT 1 FROM village_households WHERE property_id=$1 AND lower(email)=lower($2)", cx.prop, body.email.strip()):
            raise HTTPException(409, "A household with that email already exists. Use Resend invitation or Copy sign-in link instead")
        hid = await c.fetchval("INSERT INTO village_households (property_id, email, holder_name) VALUES ($1,$2,$2) RETURNING id", cx.prop, body.email.strip())
        link = invite_link(cx.slug, hid)
        village = await c.fetchval("SELECT name FROM properties WHERE id=$1", cx.prop)
        await notify(c, cx.prop, body.email, f"Invitation to the {village} household form", body.email, invite_mail(link, village))
        await audit(c, cx, f"Household invited: {body.email}")
    return {"id": str(hid), "link": link}


@router.post("/households/{hid}/resend-invite")
async def resend_invite(hid: UUID, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        e = await c.fetchval("SELECT email FROM village_households WHERE id=$1 AND property_id=$2 AND status='invited'", hid, cx.prop)
        if not e:
            raise HTTPException(404, "No pending invitation")
        link = invite_link(cx.slug, hid)
        village = await c.fetchval("SELECT name FROM properties WHERE id=$1", cx.prop)
        await notify(c, cx.prop, e, "Reminder: complete your household form", e, invite_mail(link, village))
        await audit(c, cx, f"Invitation re-sent: {e}")
    return {"ok": True, "link": link}


@router.post("/households/{hid}/link")
async def household_link(hid: UUID, request: Request, cx: Ctx = Depends(need("admin"))):
    """A fresh sign-in link for any household (the account holder's way back in). Not emailed, the Admin hands it over."""
    async with tx(request) as c:
        h = await c.fetchrow("SELECT lot_code, holder_name FROM village_households WHERE id=$1 AND property_id=$2", hid, cx.prop)
        if not h:
            raise HTTPException(404, "Household not found")
        await audit(c, cx, f"Sign-in link issued for {h['holder_name']}")
    return {"link": invite_link(cx.slug, hid)}


@router.patch("/households/{hid}")
async def patch_household(hid: UUID, body: HouseholdPatch, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        h = await c.fetchrow("SELECT * FROM village_households WHERE id=$1 AND property_id=$2 FOR UPDATE", hid, cx.prop)
        if not h:
            raise HTTPException(404, "Household not found")
        lot = h["lot_code"]
        if (body.lot or "").strip():   # same lot format as the household form, so visitors can still match it
            lot = norm_lot(body.lot)
            if not lot:
                raise HTTPException(422, "Enter the block and lot (like B1-L4) or the house number")
        if lot and await c.fetchval("SELECT 1 FROM village_households WHERE property_id=$1 AND lower(lot_code)=lower($2) AND id<>$3", cx.prop, lot, hid):
            raise HTTPException(409, "That lot already belongs to another household")
        owner = " ".join(body.owner.split()) if body.owner and body.owner.strip() else None
        holder = " ".join(body.holder.split()) if body.holder and body.holder.strip() else None
        email = (body.email or "").strip() or None
        phone = (body.phone or "").strip() or None
        if email and not EMAIL_RE.match(email):
            raise HTTPException(422, "Enter a valid email address")
        if phone and not 7 <= len(re.sub(r"\D", "", phone)) <= 15:
            raise HTTPException(422, "Enter a valid phone number")
        members = clean_members(body.members) if body.members is not None else None
        if members:
            who = (holder or h["holder_name"] or "").lower()
            me = next((m for m in members if m["n"].lower() == who), None)
            if not me:
                raise HTTPException(422, "The account holder must be one of the people listed")
            if me["minor"]:
                raise HTTPException(422, "The account holder must be an adult")
        await c.execute("""UPDATE village_households SET owner_name=COALESCE($3,owner_name), lot_code=$4, holder_name=COALESCE($5,holder_name),
                           email=COALESCE($6,email), phone=COALESCE($7,phone) WHERE id=$1 AND property_id=$2""",
                        hid, cx.prop, owner, lot, holder, email, phone)
        if members is not None:
            await sync_members(c, cx, hid, members)
        if lot:
            await link_lot(c, cx.prop, lot, hid)
        await audit(c, cx, f"Household edited: {lot or h['email']}")
    return {"ok": True}


class LotIn(BaseModel):
    lot: str = Field(min_length=1)
    household: str = ""


class RouteIn(BaseModel):
    route: str = Field(default="", max_length=300)


class PosIn(BaseModel):
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)


async def lot_target(c, prop, name):
    if not name or name.strip() in ("", "-"):
        return None
    hid = await c.fetchval("""SELECT id FROM village_households WHERE property_id=$1 AND (lower(owner_name)=lower($2) OR lower(holder_name)=lower($2))
                              ORDER BY created_at LIMIT 1""", prop, name.strip())
    if not hid:
        raise HTTPException(422, f"No household named {name.strip()}. Invite the household first, or leave this blank")
    return hid


async def link_household_to_lot(c, prop, lid, lot, hid):
    """A lot and its household always agree: the household's lot code is the lot, and a household has one lot."""
    taken = await c.fetchval("SELECT household_id FROM village_lots WHERE id=$1", lid)
    if taken and taken != hid:
        raise HTTPException(409, "That lot is already linked to another household")
    if await c.fetchval("SELECT 1 FROM village_households WHERE property_id=$1 AND lower(lot_code)=lower($2) AND id<>$3", prop, lot, hid):
        raise HTTPException(409, "That lot already belongs to another household")
    own = await c.fetchval("SELECT lot_code FROM village_households WHERE id=$1 AND property_id=$2", hid, prop)
    if own and own.lower() != lot.lower():
        raise HTTPException(409, f"That household already lives at {own}. Move it from Households, Edit")
    await c.execute("UPDATE village_lots SET household_id=$2 WHERE id=$1", lid, hid)
    await c.execute("UPDATE village_households SET lot_code=$3 WHERE id=$1 AND property_id=$2", hid, prop, lot)


@router.post("/lots")
async def add_lot(body: LotIn, request: Request, cx: Ctx = Depends(need("admin"))):
    lot = norm_lot(body.lot)
    if not lot:
        raise HTTPException(422, "Enter the lot like B2-L3, or a house number")
    async with tx(request) as c:
        hid = await lot_target(c, cx.prop, body.household)
        if await c.fetchval("SELECT 1 FROM village_lots WHERE property_id=$1 AND lower(lot_code)=lower($2)", cx.prop, lot):
            raise HTTPException(409, "That lot already exists")
        lid = await c.fetchval("INSERT INTO village_lots (property_id, lot_code) VALUES ($1,$2) RETURNING id", cx.prop, lot)
        if hid:
            await link_household_to_lot(c, cx.prop, lid, lot, hid)
        await audit(c, cx, f"Lot added: {lot}")
    return {"ok": True}


@router.patch("/lots/{lid}")
async def patch_lot(lid: UUID, body: LotIn, request: Request, cx: Ctx = Depends(need("admin"))):
    lot = norm_lot(body.lot)
    if not lot:
        raise HTTPException(422, "Enter the lot like B2-L3, or a house number")
    async with tx(request) as c:
        cur = await c.fetchrow("SELECT lot_code, household_id FROM village_lots WHERE id=$1 AND property_id=$2 FOR UPDATE", lid, cx.prop)
        if not cur:
            raise HTTPException(404, "Lot not found")
        if await c.fetchval("SELECT 1 FROM village_lots WHERE property_id=$1 AND lower(lot_code)=lower($2) AND id<>$3", cx.prop, lot, lid):
            raise HTTPException(409, "That lot already exists")
        hid = await lot_target(c, cx.prop, body.household)
        if hid is None and cur["household_id"]:
            hid = cur["household_id"]   # a blank name keeps the link; moving a household is done by linking it to its new lot
        if hid and hid != cur["household_id"]:
            await c.execute("UPDATE village_lots SET lot_code=$2 WHERE id=$1", lid, lot)
            await link_household_to_lot(c, cx.prop, lid, lot, hid)
        else:
            if hid and await c.fetchval("SELECT 1 FROM village_households WHERE property_id=$1 AND lower(lot_code)=lower($2) AND id<>$3", cx.prop, lot, hid):
                raise HTTPException(409, "That lot already belongs to another household")
            await c.execute("UPDATE village_lots SET lot_code=$2 WHERE id=$1", lid, lot)
            if hid:
                await c.execute("UPDATE village_households SET lot_code=$3 WHERE id=$1 AND property_id=$2", hid, cx.prop, lot)
        await audit(c, cx, f"Lot edited: {lot}")
    return {"ok": True}


@router.put("/lots/{lid}/route")
async def lot_route(lid: UUID, body: RouteIn, request: Request, cx: Ctx = Depends(need("admin"))):
    """Directions from the gate to this lot, shown to the visitor only after check-in. Blank = the automatic route."""
    async with tx(request) as c:
        n = await c.fetchval("UPDATE village_lots SET route=NULLIF($3,'') WHERE id=$1 AND property_id=$2 RETURNING 1",
                             lid, cx.prop, " ".join(body.route.split()))
        if not n:
            raise HTTPException(404, "Lot not found")
        await audit(c, cx, "Wayfinding route edited")
    return {"ok": True}


@router.put("/lots/{lid}/pos")
async def lot_pos(lid: UUID, body: PosIn, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        n = await c.fetchval("UPDATE village_lots SET pos_x=$3, pos_y=$4 WHERE id=$1 AND property_id=$2 RETURNING 1", lid, cx.prop, body.x, body.y)
        if not n:
            raise HTTPException(404, "Lot not found")
        await audit(c, cx, "Lot placed on the village map")
    return {"ok": True}


@router.put("/gates/{gid}/pos")
async def gate_pos(gid: UUID, body: PosIn, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        n = await c.fetchval("UPDATE gates SET pos_x=$3, pos_y=$4 WHERE id=$1 AND property_id=$2 RETURNING 1", gid, cx.prop, body.x, body.y)
        if not n:
            raise HTTPException(404, "Gate not found")
        await audit(c, cx, "Gate placed on the village map")
    return {"ok": True}


MAP_MAX = 8 * 1024 * 1024
MAP_TYPES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg", b"%PDF-": "application/pdf"}


class MapIn(BaseModel):
    data: str   # base64, a data: URL prefix is fine


@router.put("/map")
async def put_map(body: MapIn, request: Request, cx: Ctx = Depends(need("admin"))):
    """Import the village map as an image or a PDF."""
    import base64
    raw = body.data.split(",", 1)[1] if body.data.startswith("data:") else body.data
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        raise HTTPException(422, "The map file could not be read. Choose it again")
    if len(blob) > MAP_MAX:
        raise HTTPException(413, "The map file is too large (8 MB at most)")
    kind = next((t for sig, t in MAP_TYPES.items() if blob.startswith(sig)), None)
    if not kind and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        kind = "image/webp"
    if not kind:
        raise HTTPException(422, "The map must be a PNG, JPEG, WebP image or a PDF")
    async with tx(request) as c:
        await c.execute("""INSERT INTO village_maps (property_id, content, content_type) VALUES ($1,$2,$3)
                           ON CONFLICT (property_id) DO UPDATE SET content=EXCLUDED.content, content_type=EXCLUDED.content_type, updated_at=now()""",
                        cx.prop, blob, kind)
        await audit(c, cx, "Village map imported")
    return {"ok": True, "type": kind}


@router.get("/map")
async def get_map(request: Request, cx: Ctx = Depends(need("admin"))):
    r = await request.app.state.pool.fetchrow("SELECT content, content_type FROM village_maps WHERE property_id=$1", cx.prop)
    if not r:
        raise HTTPException(404, "No map imported yet")
    return Response(bytes(r["content"]), media_type=r["content_type"], headers={"Cache-Control": "private, no-store"})


@router.delete("/map")
async def delete_map(request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        await c.execute("DELETE FROM village_maps WHERE property_id=$1", cx.prop)
        await audit(c, cx, "Village map removed")
    return {"ok": True}


class GateIn(BaseModel):
    name: str = Field(min_length=1)
    type: str = "Entry and exit"


class GatePatch(BaseModel):
    active: bool | None = None
    name: str | None = Field(default=None, min_length=1)
    type: str | None = None


@router.post("/gates")
async def add_gate(body: GateIn, request: Request, cx: Ctx = Depends(need("admin"))):
    body.name = " ".join(body.name.split())
    if not body.name:
        raise HTTPException(422, "Enter the gate name")
    async with tx(request) as c:
        await c.execute("INSERT INTO gates (property_id, name, kind) VALUES ($1,$2,$3)", cx.prop, body.name.strip(), body.type)
        await audit(c, cx, f"Gate added: {body.name}")
    return {"ok": True}


@router.patch("/gates/{gid}")
async def patch_gate(gid: UUID, body: GatePatch, request: Request, cx: Ctx = Depends(need("admin"))):
    if body.name is not None and not body.name.strip():
        raise HTTPException(422, "Enter the gate name")
    async with tx(request) as c:
        n = await c.fetchval("""UPDATE gates SET active=COALESCE($3,active), name=COALESCE($4,name), kind=COALESCE($5,kind)
                                WHERE id=$1 AND property_id=$2 RETURNING 1""", gid, cx.prop, body.active, (body.name or "").strip() or None, body.type)
        if not n:
            raise HTTPException(404, "Gate not found")
        await audit(c, cx, "Gate " + ("activated" if body.active else "deactivated") if body.active is not None else "Gate edited")
    return {"ok": True}


class ActiveIn(BaseModel):
    active: bool


class BadgeIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class BadgeStatus(BaseModel):
    status: str = Field(pattern="^(avail|lost)$")


@router.post("/badges")
async def add_badge(body: BadgeIn, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        try:
            await c.execute("INSERT INTO badges (property_id, code) VALUES ($1,$2)", cx.prop, body.code.strip().upper())
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "That pass number already exists")
        await audit(c, cx, f"Pass added: {body.code.upper()}")
    return {"ok": True}


@router.post("/badges/{bid}/status")
async def badge_status(bid: UUID, body: BadgeStatus, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        n = await c.fetchval("UPDATE badges SET status=$3, holder=NULL WHERE id=$1 AND property_id=$2 AND status<>'issued' RETURNING 1",
                             bid, cx.prop, body.status)
        if not n:
            raise HTTPException(409, "A pass that is issued cannot be changed here")
        await audit(c, cx, f"Pass marked {'lost' if body.status == 'lost' else 'found'}")
    return {"ok": True}


async def check_new_password(pw: str | None) -> str | None:
    if pw is None or pw == "":
        return None
    if len(pw) < config.MIN_PASSWORD or len(pw) > 200:
        raise HTTPException(422, f"The password must be at least {config.MIN_PASSWORD} characters")
    return await hash_password_async(pw)


class PasswordIn(BaseModel):
    current: str = ""
    new: str = Field(max_length=200)


class StaffIn(BaseModel):
    password: str | None = Field(default=None, max_length=200)   # optional first password; the person can change it
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=120)
    role: str = Field(pattern="^(Guard|HOA office)$")


class StaffPatch(BaseModel):
    password: str | None = Field(default=None, max_length=200)   # reset the person's password
    name: str | None = None
    email: str | None = None
    active: bool | None = None


@router.post("/staff")
async def add_staff(body: StaffIn, request: Request, cx: Ctx = Depends(need("admin"))):
    body.name, body.email = " ".join(body.name.split()), body.email.strip()
    if not body.name:
        raise HTTPException(422, "Enter the person's name")
    if not EMAIL_RE.match(body.email):
        raise HTTPException(422, "Enter a valid email address")
    ph = await check_new_password(body.password)
    async with tx(request) as c:
        try:
            await c.execute("INSERT INTO users (property_id, email, name, role, password_hash) VALUES ($1,$2,$3,$4,$5)", cx.prop, body.email,
                            body.name, "guard" if body.role == "Guard" else "hoa", ph)
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "An account with that email already exists")
        await audit(c, cx, f"Account created: {body.name} ({body.role})")
    return {"ok": True}


@router.patch("/staff/{uid}")
async def patch_staff(uid: UUID, body: StaffPatch, request: Request, cx: Ctx = Depends(need("admin"))):
    name = " ".join(body.name.split()) if body.name is not None else None
    email = body.email.strip() if body.email is not None else None
    if name is not None and not name:
        raise HTTPException(422, "Enter the person's name")
    if email is not None and not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address")
    ph = await check_new_password(body.password)
    async with tx(request) as c:
        try:
            # a new password, or switching the account off or on, ends every sign-in the person already holds (vista_token_version + 1)
            n = await c.fetchval("""UPDATE users SET name=COALESCE($3,name), email=COALESCE($4,email), active=COALESCE($5,active),
                                    password_hash=COALESCE($6,password_hash),
                                    vista_token_version = vista_token_version
                                      + CASE WHEN $6::text IS NOT NULL OR ($5::boolean IS NOT NULL AND $5::boolean IS DISTINCT FROM active) THEN 1 ELSE 0 END
                                    WHERE id=$1 AND property_id=$2 AND role IN ('guard','hoa') RETURNING 1""",
                                 uid, cx.prop, name, email, body.active, ph)
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, "An account with that email already exists")
        if not n:
            raise HTTPException(404, "Account not found")
        await audit(c, cx, "Account updated" + (", password reset" if ph else "") + (", switched " + ("on" if body.active else "off") if body.active is not None else ""))
    return {"ok": True}


@router.put("/me/password")
async def my_password(body: PasswordIn, request: Request, cx: Ctx = Depends(need("admin", "guard", "hoa")), authorization: str | None = Header(None)):
    """A signed-in person changes their own password. An Admin who arrived by the Super Admin's link and has no password yet needs no current one.
    Every other sign-in the account holds (other phones, a stolen token, the old Admin link) stops working; the reply carries a new token
    for this device so the person stays signed in."""
    tok = verify_token((authorization or "")[7:]) or {}
    if not tok.get("u"):
        raise HTTPException(403, "Sign in with your own account to set a password")
    account_limit(request, "pw:" + str(tok["u"]))   # guesses at the current password are slowed down like sign-in guesses
    new = await check_new_password(body.new or None)
    if not new:
        raise HTTPException(422, f"The password must be at least {config.MIN_PASSWORD} characters")
    async with tx(request) as c:
        row = await c.fetchrow("SELECT password_hash, vista_token_version AS v FROM users WHERE id=$1 AND property_id=$2 FOR UPDATE", UUID(tok["u"]), cx.prop)
        if not row or row["v"] != int(tok.get("v") or 0):   # another change got in first
            raise HTTPException(401, "Your session has ended because the password or the account changed. Sign in again.")
        if row["password_hash"] and not await check_password_async(body.current, row["password_hash"]):
            raise HTTPException(403, "The current password is wrong")
        v = await c.fetchval("UPDATE users SET password_hash=$2, vista_token_version=vista_token_version+1 WHERE id=$1 RETURNING vista_token_version",
                             UUID(tok["u"]), new)
        await audit(c, cx, "Password changed")
    return {"ok": True, "token": session_token(cx.role, cx.name, cx.slug, uid=tok["u"], version=v)}


class AreaIn(BaseModel):
    name: str | None = None
    members: str | list[str] | None = None
    active: bool | None = None


async def tie_members(c, prop, aid, members):
    names = members if isinstance(members, list) else [m.strip() for m in (members or "").split(",")]
    for n in [x for x in names if x]:
        m = await c.fetchval("SELECT id FROM village_members WHERE property_id=$1 AND lower(full_name)=lower($2) LIMIT 1", prop, n)
        if not m:
            raise HTTPException(422, f"No household member named {n}")
        await c.execute("INSERT INTO restricted_area_members (property_id, area_id, member_id) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING", prop, aid, m)


@router.post("/areas")
async def add_area(body: AreaIn, request: Request, cx: Ctx = Depends(need("admin"))):
    if not (body.name or "").strip():
        raise HTTPException(422, "Area name is required")
    async with tx(request) as c:
        aid = await c.fetchval("INSERT INTO restricted_areas (property_id, name) VALUES ($1,$2) RETURNING id", cx.prop, body.name.strip())
        await tie_members(c, cx.prop, aid, body.members)
        await audit(c, cx, f"Restricted area added: {body.name}")
    return {"ok": True}


@router.patch("/areas/{aid}")
async def patch_area(aid: UUID, body: AreaIn, request: Request, cx: Ctx = Depends(need("admin"))):
    name = " ".join(body.name.split()) if body.name is not None else None
    if name is not None and not name:
        raise HTTPException(422, "Area name is required")
    async with tx(request) as c:
        n = await c.fetchval("UPDATE restricted_areas SET name=COALESCE($3,name), active=COALESCE($4,active) WHERE id=$1 AND property_id=$2 RETURNING 1",
                             aid, cx.prop, name, body.active)
        if not n:
            raise HTTPException(404, "Area not found")
        if body.members is not None:
            await c.execute("DELETE FROM restricted_area_members WHERE area_id=$1", aid)
            await tie_members(c, cx.prop, aid, body.members)
        await audit(c, cx, "Restricted area updated")
    return {"ok": True}


@router.delete("/areas/{aid}/members/{mid}")
async def untie(aid: UUID, mid: UUID, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        await c.execute("DELETE FROM restricted_area_members WHERE area_id=$1 AND member_id=$2 AND property_id=$3", aid, mid, cx.prop)
        await audit(c, cx, "Restricted area member removed")
    return {"ok": True}


@router.post("/alerts/{aid}/resolve")
async def resolve_alert(aid: int, request: Request, cx: Ctx = Depends(need("admin", "guard"))):
    async with tx(request) as c:
        n = await c.fetchval("UPDATE alerts SET status='resolved' WHERE id=$1 AND property_id=$2 RETURNING 1", aid, cx.prop)
        if not n:
            raise HTTPException(404, "Alert not found")
        await audit(c, cx, "Alert resolved")
    return {"ok": True}


@router.post("/messages/{mid}/resend")
async def resend_message(mid: int, request: Request, cx: Ctx = Depends(need("admin"))):
    async with tx(request) as c:
        m = await c.fetchrow("SELECT recipient, subject FROM notifications WHERE id=$1 AND property_id=$2", mid, cx.prop)
        if not m:
            raise HTTPException(404, "Message not found")
        await notify(c, cx.prop, m["recipient"], m["subject"])
        await audit(c, cx, f"Message re-sent: {m['subject']}")
    return {"ok": True}


@router.get("/settings")
async def get_settings(request: Request, cx: Ctx = Depends(need("admin"))):
    rows = await request.app.state.pool.fetch("SELECT key, value FROM settings WHERE property_id=$1", cx.prop)
    import json
    return {r["key"]: json.loads(r["value"]) if isinstance(r["value"], str) else r["value"] for r in rows}


@router.put("/settings")
async def put_settings(body: dict, request: Request, cx: Ctx = Depends(need("admin"))):
    import json
    for k, v in body.items():   # only the three Settings tabs exist; each is a short list of text, yes/no or numbers
        if k not in ("tab0", "tab1", "tab2") or not isinstance(v, list) or len(v) > 30 \
                or any(not (x is None or isinstance(x, (bool, int, float)) or (isinstance(x, str) and len(x) <= 300)) for x in v):
            raise HTTPException(422, "Those settings could not be saved. Reload the page and try again")
    t1 = body.get("tab1")
    if isinstance(t1, list) and len(t1) >= 6:   # the two numbers must be real numbers, or the Missing job and the photo purge would misbehave
        for i, (lo, hi, what) in {4: (1, 48, "Missing after (hours)"), 5: (1, 365, "Entry photo retention (days)")}.items():
            if not re.fullmatch(r"\d{1,4}", str(t1[i]).strip()) or not lo <= int(str(t1[i]).strip()) <= hi:
                raise HTTPException(422, f"{what} must be a whole number from {lo} to {hi}")
    async with tx(request) as c:
        for k, v in body.items():
            if k == "tab0" and isinstance(v, list) and v and str(v[0]).strip():   # the village name on the General tab is the property's name
                await c.execute("UPDATE properties SET name=$2 WHERE id=$1", cx.prop, " ".join(str(v[0]).split())[:80])
            await c.execute("INSERT INTO settings (property_id, key, value) VALUES ($1,$2,$3::jsonb) "
                            "ON CONFLICT (property_id, key) DO UPDATE SET value=EXCLUDED.value", cx.prop, str(k)[:60], json.dumps(v))
        await audit(c, cx, "Settings changed")
    return {"ok": True}
