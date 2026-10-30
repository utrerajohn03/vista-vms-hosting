"""GET /api/state: one role-scoped snapshot shaped exactly like the data the UI renders."""
from datetime import datetime

from . import config
import re
from datetime import timedelta

from .core import ARR_LABEL, STATUS_LABEL, TZ, Ctx, setting

HHSTATUS = {"verified": "Verified", "awaiting": "Awaiting HOA", "invited": "Invited"}
HM = "to_char({c} AT TIME ZONE $2,'HH24:MI')"


def _day(dt):
    return dt.astimezone(TZ).date() if dt else None


def _is_today(r, today) -> bool:
    """A visit belongs to today when it is scheduled for today (or was requested today with no date) or the visitor entered today."""
    return today in (_day(r["visit_at"] or r["v_created"]), _day(r["gate_notified_at"]))


def _eq(a, b):
    return (a or "").strip().lower() == (b or "").strip().lower()


async def build_state(pool, cx: Ctx) -> dict:
    prop, role, tz = cx.prop, cx.role, config.TIMEZONE
    today = datetime.now(TZ).date()
    out = {k: [] for k in ["visits", "households", "lots", "routes", "gates", "passes", "staff", "areas", "rm",
                           "alerts", "msgs", "audit", "scan"]}
    out["now"] = datetime.now(TZ).strftime("%H:%M")
    out["me"] = {"role": role, "name": cx.name, "lot": cx.hlot}
    async with pool.acquire() as c:
        pr = await c.fetchrow("SELECT name, slug FROM properties WHERE id=$1", prop)
        out["prop"] = {"name": pr["name"], "slug": pr["slug"]}
        if role in ("admin", "guard", "hoa", "household"):
            rows = await c.fetch(
                f"""SELECT v.id, v.seq, v.status, v.qr_token, v.created_at AS v_created, d.*, h.lot_code, h.holder_name, h.phone AS hh_phone,
                           hm.full_name AS host_name, hm.is_minor AS host_minor,
                           to_char(COALESCE(d.visit_at, v.created_at) AT TIME ZONE $2,'Mon DD HH24:MI') AS when_txt
                    FROM visits v JOIN village_visit_details d ON d.visit_id=v.id
                    LEFT JOIN village_households h ON h.id=d.household_id
                    LEFT JOIN village_members hm ON hm.id=d.host_member_id
                    WHERE v.property_id=$1 ORDER BY v.seq DESC""", prop, tz)
            ppl = await c.fetch(
                """SELECT pe.visit_id, pe.full_name, pe.arrived_at, pe.left_at, b.code
                   FROM village_visit_people pe LEFT JOIN badges b ON b.id=pe.badge_id
                   WHERE pe.property_id=$1 ORDER BY pe.sort, pe.id""", prop)
            chk = {r["visit_id"]: r for r in await c.fetch("SELECT * FROM village_vehicle_checks WHERE property_id=$1", prop)}
            photos = {r["visit_id"] for r in await c.fetch("SELECT visit_id FROM village_entry_photos WHERE property_id=$1", prop)}
            idps = {r["visit_id"] for r in await c.fetch("SELECT visit_id FROM village_id_photos WHERE property_id=$1", prop)}
            by = {}
            for p in ppl:
                by.setdefault(p["visit_id"], []).append(p)
            holder = (await c.fetchval("SELECT holder_name FROM village_households WHERE id=$1", cx.hid)) if role == "household" else None
            sees_all = role == "household" and await setting(c, prop, 1, 0, "Only visits to minors") == "All visits"   # Settings: primary adult
            for r in rows:
                if role == "household":  # a primary adult sees other adults' visitors only for minors
                    if r["household_id"] != cx.hid:
                        continue
                    if r["host_name"] and not (sees_all or _eq(r["host_name"], holder) or r["host_minor"]):
                        continue
                people = by.get(r["id"], [])
                names = [p["full_name"] for p in people]
                vc = chk.get(r["id"])
                out["visits"].append({
                    "id": str(r["id"]), "ref": f"VS-{r['seq']:04d}",
                    "visitor": names[0] + (f" +{len(names) - 1}" if len(names) > 1 else "") if names else r["visitor_name"],
                    "phone": r["visitor_phone"], "house": r["typed_house"], "host": r["typed_host"] or "Any household member",
                    "arr": ARR_LABEL[r["arrival_method"]], "when": r["when_txt"],
                    "today": 1 if _is_today(r, today) else 0,
                    "flag": "Red flag" if r["restricted_flag"] else "Normal", "st": STATUS_LABEL[r["status"]],
                    "hid": r["lot_code"], "people": names, "tok": r["qr_token"], "w": 1 if r["walk_in"] else 0,
                    "pass": {p["full_name"]: p["code"] for p in people if p["code"]},
                    "inn": {p["full_name"]: 1 for p in people if p["arrived_at"]},
                    "out": {p["full_name"]: 1 for p in people if p["left_at"]},
                    "call": f"{r['holder_name']} {r['hh_phone']}" if r["lot_code"] else "",
                    "veh": {"kind": r["declared_kind"] or "", "color": r["declared_color"] or "", "plate": r["declared_plate"] or ""},
                    "idp": 1 if r["id"] in idps else 0,
                    "chk": {"id": 1, "photo": 1 if r["id"] in photos else 0, "plate": vc["plate_ok"], "color": vc["color_ok"], "type": vc["type_ok"]} if vc else {},
                    "vl": r["vehicle_left"], "gate": r["gate_notified_at"].isoformat() if r["gate_notified_at"] else None,
                })
        if role in ("admin", "hoa", "household"):
            hs = await c.fetch("SELECT * FROM village_households WHERE property_id=$1 " + ("AND id=$2 " if role == "household" else "") +
                               "ORDER BY created_at, lot_code", *( [prop, cx.hid] if role == "household" else [prop]))
            mem = await c.fetch("SELECT * FROM village_members WHERE property_id=$1 ORDER BY full_name", prop)
            for h in hs:
                ms = [{"n": m["full_name"], "minor": 1 if m["is_minor"] else 0} for m in mem if m["household_id"] == h["id"]]
                out["households"].append({"id": str(h["id"]), "lot": h["lot_code"] or "-",
                                          "owner": "" if h["owner_name"] == "(invited)" else h["owner_name"],
                                          "holder": h["holder_name"] or h["email"] or "", "email": h["email"] or "",
                                          "ph": h["phone"] or "", "people": len(ms), "st": HHSTATUS[h["status"]], "members": ms,
                                          "vby": h["verified_by"] or "", "vat": h["verified_at"].astimezone(TZ).strftime("%b %d %H:%M") if h["verified_at"] else ""})
        if role in ("admin", "guard"):
            for b in await c.fetch("SELECT * FROM badges WHERE property_id=$1 ORDER BY code", prop):
                out["passes"].append({"id": str(b["id"]), "no": b["code"], "holder": b["holder"] or "-",
                                      "st": {"avail": "Available", "issued": "Issued", "lost": "Lost"}[b["status"]]})
            for a in await c.fetch(f"SELECT id, kind, detail, status, {HM.format(c='created_at')} AS t FROM alerts "
                                   "WHERE property_id=$1 ORDER BY id DESC LIMIT 200", prop, tz):
                out["alerts"].append({"id": a["id"], "time": a["t"], "type": a["kind"], "detail": a["detail"],
                                      "st": "Open" if a["status"] == "open" else "Resolved"})
        if role == "guard":   # notices addressed to the guard: arrival at the house, Missing
            for m in await c.fetch(f"SELECT id, recipient, subject, status, {HM.format(c='created_at')} AS t FROM notifications "
                                   "WHERE property_id=$1 AND recipient IN ('Guard','Guard and Admin') ORDER BY id DESC LIMIT 100", prop, tz):
                out["msgs"].append({"id": m["id"], "time": m["t"], "to": m["recipient"], "subject": m["subject"], "st": m["status"].capitalize()})
        if role == "admin":
            for l in await c.fetch("""SELECT l.id, l.lot_code, l.route, l.pos_x, l.pos_y, h.owner_name,
                                             (SELECT string_agg(m.full_name || CASE WHEN m.is_minor THEN ' (minor)' ELSE '' END, ', ' ORDER BY m.full_name)
                                                FROM village_members m WHERE m.household_id=h.id) AS n
                                      FROM village_lots l LEFT JOIN village_households h ON h.id=l.household_id
                                      WHERE l.property_id=$1 ORDER BY l.lot_code""", prop):
                linked = l["owner_name"] is not None
                owner = l["owner_name"] if l["owner_name"] not in (None, "(invited)") else "-"
                out["lots"].append({"id": str(l["id"]), "lot": l["lot_code"], "household": owner,
                                    "people": l["n"] or "-", "st": "Mapped" if linked else "Unlinked",
                                    "x": l["pos_x"], "y": l["pos_y"], "route": l["route"] or ""})
                if linked:
                    m = re.fullmatch(r"B(\d+)-L(\d+)", l["lot_code"], re.I)
                    auto = f"Main gate, Village Road, Block {m.group(1)}, Lot {m.group(2)}" if m else f"Main gate, Village Road, house {l['lot_code']}"
                    out["routes"].append({"id": str(l["id"]), "lot": l["lot_code"], "dest": f"{l['lot_code']} {owner}",
                                          "route": l["route"] or auto, "custom": bool(l["route"]),
                                          "shown": "After pass is issued", "st": "Active"})
            mp = await c.fetchrow("SELECT content_type, extract(epoch from updated_at)::bigint AS v FROM village_maps WHERE property_id=$1", prop)
            out["map"] = {"has": bool(mp), "type": mp["content_type"] if mp else "", "v": mp["v"] if mp else 0}
            for g in await c.fetch("SELECT * FROM gates WHERE property_id=$1 ORDER BY name", prop):
                out["gates"].append({"id": str(g["id"]), "name": g["name"], "type": g["kind"], "st": "Active" if g["active"] else "Inactive",
                                     "x": g["pos_x"], "y": g["pos_y"]})
            for u in await c.fetch("SELECT * FROM users WHERE property_id=$1 AND role IN ('guard','hoa') ORDER BY name", prop):
                out["staff"].append({"id": str(u["id"]), "name": u["name"], "email": u["email"],
                                     "role": "Guard" if u["role"] == "guard" else "HOA office", "st": "Active" if u["active"] else "Inactive"})
            for a in await c.fetch("SELECT * FROM restricted_areas WHERE property_id=$1 ORDER BY created_at", prop):
                ms = await c.fetch("""SELECT m.id, m.full_name, h.owner_name FROM restricted_area_members r
                                      JOIN village_members m ON m.id=r.member_id JOIN village_households h ON h.id=m.household_id
                                      WHERE r.area_id=$1""", a["id"])
                since = a["created_at"].astimezone(TZ).strftime("%b %Y")
                out["areas"].append({"id": str(a["id"]), "area": a["name"], "members": ", ".join(m["full_name"] for m in ms),
                                     "since": since, "st": "Active" if a["active"] else "Inactive"})
                for m in ms:
                    out["rm"].append({"member": m["full_name"], "household": m["owner_name"], "area": a["name"],
                                      "st": "Active" if a["active"] else "Inactive", "area_id": str(a["id"]), "member_id": str(m["id"])})
            for m in await c.fetch(f"SELECT id, recipient, subject, status, {HM.format(c='created_at')} AS t FROM notifications "
                                   "WHERE property_id=$1 ORDER BY id DESC LIMIT 200", prop, tz):
                out["msgs"].append({"id": m["id"], "time": m["t"], "to": m["recipient"], "subject": m["subject"], "st": m["status"].capitalize()})
            for a in await c.fetch(f"SELECT {HM.format(c='created_at')} AS t, actor, role, action FROM audit_log "
                                   "WHERE property_id=$1 ORDER BY id DESC LIMIT 300", prop, tz):
                out["audit"].append({"time": a["t"], "actor": a["actor"], "role": a["role"], "action": a["action"]})
        if role == "admin":
            out["report"] = await build_report(c, prop, rows, ppl, today)
        if role == "household":  # pass codes of everyone inside, names only for your own household
            mine = {v["ref"]: v for v in out["visits"]}
            for r in await c.fetch(
                    """SELECT pe.full_name, b.code, v.seq, v.status, pe.arrived_at, d.household_id
                       FROM village_visit_people pe JOIN badges b ON b.id=pe.badge_id JOIN visits v ON v.id=pe.visit_id
                       JOIN village_visit_details d ON d.visit_id=v.id
                       WHERE pe.property_id=$1 AND v.status IN ('at_gate','arrived','missing') ORDER BY v.seq, pe.sort""", prop):
                own = r["household_id"] == cx.hid
                out["scan"].append({"person": r["full_name"] if own else "(pass for another household)", "pass": r["code"],
                                    "visit": f"VS-{r['seq']:04d}" if own else "-",
                                    "st": "Arrived" if r["arrived_at"] else "Not scanned"})
    return out


async def build_report(c, prop, rows, ppl, today) -> dict:
    """Real numbers for the Reports page: the last 7 days against the 7 before, from the visits and alerts tables."""
    day = lambda r: _day(r["visit_at"] or r["v_created"])   # noqa: E731
    week = [today - timedelta(days=i) for i in range(6, -1, -1)]
    prev = {today - timedelta(days=i) for i in range(7, 14)}
    in_week = [r for r in rows if day(r) in week]
    ids = {r["id"] for r in in_week}
    n_prev = sum(1 for r in rows if day(r) in prev)
    arr = {}
    for r in in_week:
        arr[ARR_LABEL[r["arrival_method"]]] = arr.get(ARR_LABEL[r["arrival_method"]], 0) + 1
    exc = {k: n for k, n in await c.fetch(
        "SELECT kind, count(*) FROM alerts WHERE property_id=$1 AND created_at > now() - interval '7 days' GROUP BY kind", prop)}
    over = await c.fetchval("SELECT count(*) FROM village_vehicle_checks WHERE property_id=$1 AND override_used AND created_at > now() - interval '7 days'", prop)
    lost = await c.fetchval("SELECT count(*) FROM badges WHERE property_id=$1 AND status='lost'", prop)
    entered = [r for r in rows if r["gate_notified_at"] and r["gate_notified_at"] > r["v_created"]]
    waits = [(r["gate_notified_at"] - r["v_created"]).total_seconds() / 60 for r in entered if _day(r["gate_notified_at"]) in week]
    return {
        "days": [[d.strftime("%a"), sum(1 for r in in_week if day(r) == d)] for d in week],
        "week": len(in_week), "prev": n_prev,
        "people": sum(1 for p in ppl if p["visit_id"] in ids),
        "today": sum(1 for r in rows if day(r) == today),
        "missing": exc.get("Missing", 0),
        "arr": [[k, arr.get(k, 0)] for k in ARR_LABEL.values()],
        "exc": [[k, n] for k, n in sorted(exc.items())] + [["Vehicle mismatch overrides", over], ["Passes lost", lost]],
        "avg_entry_min": round(sum(waits) / len(waits)) if waits else None,
    }
