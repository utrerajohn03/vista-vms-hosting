import re

from tests.conftest import H, JPEG_B64, public_visit, visit_when

VIS = {"name": "Test Visitor", "phone": "0999 111 2222", "house": "B1-L4", "host": "Maria Reyes", "purpose": "Visit",
       "arrival": "Own vehicle", "kind": "Vios", "color": "White", "plate": "XYZ 123", "friends": ["Friend One", "Friend Two"],
       "when": visit_when(), "id_photo": JPEG_B64}   # a complete public request: the form requires ID or photo, purpose and date and time


async def state(client, role, lot=None, prop=None):
    r = await client.get("/api/state", headers=H(role, lot, prop))
    assert r.status_code == 200, r.text
    return r.json()


def find(st, ref):
    return next(v for v in st["visits"] if v["ref"] == ref)


async def test_health(client):
    assert (await client.get("/api/health")).json() == {"ok": True}


async def test_neutral_reply_is_identical_for_match_and_no_match(client):
    a = await client.post("/api/visits", json=VIS)
    b = await client.post("/api/visits", json={**VIS, "name": "Nobody", "house": "B9-L9", "host": ""})
    c = await client.post("/api/visits", json={**VIS, "name": "Wrong Host", "host": "Not A Member"})
    assert a.status_code == b.status_code == c.status_code == 200
    assert a.json() == b.json() == c.json()


async def test_full_visit_lifecycle(client):
    r = await client.post("/api/visits", json={**VIS, "name": "Life Cycle", "phone": "0900 000 0001"})
    assert r.status_code == 200
    adm = await state(client, "admin")
    v = next(x for x in adm["visits"] if x["visitor"].startswith("Life Cycle"))
    ref = v["ref"]
    assert v["st"] == "Pending" and v["hid"] == "B1-L4" and len(v["people"]) == 3

    # unverified household cannot approve (B3-L2 is awaiting)
    r = await client.post("/api/visits", json={**VIS, "name": "Unver Visitor", "house": "B3-L2", "host": "Ben Cruz", "phone": "0900 000 0002"})
    adm = await state(client, "admin")
    uv = next(x for x in adm["visits"] if x["visitor"].startswith("Unver"))
    r = await client.post(f"/api/visits/{uv['ref']}/decision", json={"approve": True}, headers=H("household", "B3-L2"))
    assert r.status_code == 403

    # wrong household cannot see or approve it
    r = await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B2-L7"))
    assert r.status_code == 404

    # right household approves
    r = await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    assert r.status_code == 200 and r.json()["status"] == "approved"
    # not approvable twice
    assert (await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))).status_code == 409

    # visitor retrieves the QR, no directions before check-in
    lk = (await client.post("/api/visits/lookup", json={"name": "life cycle", "phone": "09000000001"})).json()
    assert lk[0]["status"] == "Approved" and lk[0]["qr"] and "directions" not in lk[0]

    # guard check-in rules
    g = H("guard")
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": False}, headers=g)).status_code == 422
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=g)).status_code == 422  # vehicle check required
    bad = {"id_checked": True, "vehicle": {"photo_data": JPEG_B64, "plate_ok": False, "color_ok": True, "type_ok": True}}
    assert (await client.post(f"/api/visits/{ref}/check-in", json=bad, headers=g)).status_code == 409  # mismatch needs override
    ok = {"id_checked": True, "vehicle": {"photo_data": JPEG_B64, "plate_ok": False, "color_ok": True, "type_ok": True, "override": True, "reason": "Plate is dirty"}}
    r = await client.post(f"/api/visits/{ref}/check-in", json=ok, headers=g)
    assert r.status_code == 200, r.text
    codes = r.json()["passes"]
    assert len(codes) == 3

    # directions now appear
    lk = (await client.post("/api/visits/lookup", json={"name": "Life Cycle", "phone": "0900 000 0001"})).json()
    assert lk[0]["status"] == "Checked in" and lk[0]["directions"].startswith("Main gate")

    # wrong household scan flags it
    r = await client.post(f"/api/passes/{codes[0]}/arrived", headers=H("household", "B2-L7"))
    assert r.json() == {"flag": "wrong_destination"}
    assert find(await state(client, "admin"), ref)["st"] == "Wrong destination"
    open_alerts = [a for a in (await state(client, "admin"))["alerts"] if a["type"] == "Wrong destination"]
    assert open_alerts

    # visit is still closable: exit scans, vehicle left, passes return
    for p in find(await state(client, "guard"), ref)["people"]:
        assert (await client.post(f"/api/visits/{ref}/exit-scan", json={"person": p}, headers=g)).status_code == 200
    assert (await client.post(f"/api/visits/{ref}/left", json={"vehicle_left": False}, headers=g)).status_code == 422
    assert (await client.post(f"/api/visits/{ref}/left", json={"vehicle_left": True}, headers=g)).status_code == 200
    st = await state(client, "admin")
    assert find(st, ref)["st"] == "Left"
    assert all(p["st"] == "Available" for p in st["passes"] if p["no"] in codes)


async def test_arrival_and_missing(client):
    await client.post("/api/visits", json={**VIS, "name": "Arrive Me", "phone": "0900 000 0003", "arrival": "Walking", "friends": []})
    adm = await state(client, "admin")
    ref = next(x for x in adm["visits"] if x["visitor"].startswith("Arrive"))["ref"]
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    r = await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))
    code = r.json()["passes"][0]
    # not missing yet
    assert (await client.post("/api/jobs/missing", headers=H("guard"))).json()["flagged"] == 0
    # after 3 simulated hours it is flagged
    n = (await client.post("/api/jobs/missing?simulate_hours=3", headers=H("guard"))).json()["flagged"]
    assert n >= 1
    assert find(await state(client, "guard"), ref)["st"] == "Missing"
    # resident scan resolves it to Arrived
    r = await client.post(f"/api/passes/{code}/arrived", headers=H("household", "B1-L4"))
    assert r.json() == {"arrived": True}
    assert find(await state(client, "admin"), ref)["st"] == "Arrived"


async def test_queue_hoa_correct_and_reject(client):
    await client.post("/api/visits", json={**VIS, "name": "Queue Person", "phone": "0900 000 0004", "house": "B7-L7", "host": ""})
    ref = next(v for v in (await state(client, "hoa"))["visits"] if v["visitor"].startswith("Queue"))["ref"]
    assert find(await state(client, "hoa"), ref)["st"] == "In HOA queue"
    assert (await client.post(f"/api/visits/{ref}/resend", json={"house": "B0-L0", "host": ""}, headers=H("hoa"))).status_code == 422
    r = await client.post(f"/api/visits/{ref}/resend", json={"house": "B2-L7", "host": "Ana Santos"}, headers=H("hoa"))
    assert r.json()["status"] == "pending"
    await client.post("/api/visits", json={**VIS, "name": "Reject Me", "phone": "0900 000 0005", "house": "B7-L8", "host": ""})
    ref2 = next(v for v in (await state(client, "hoa"))["visits"] if v["visitor"].startswith("Reject"))["ref"]
    assert (await client.post(f"/api/visits/{ref2}/reject", json={"reason": "x"}, headers=H("hoa"))).status_code == 422
    assert (await client.post(f"/api/visits/{ref2}/reject", json={"reason": "No such address"}, headers=H("hoa"))).status_code == 200
    lk = (await client.post("/api/visits/lookup", json={"name": "Reject Me", "phone": "0900 000 0005"})).json()
    assert lk[0]["status"] == "Not approved"


async def test_red_flag_and_not_for_me(client):
    await client.post("/api/visits", json={**VIS, "name": "Red Flag", "phone": "0900 000 0006", "house": "B2-L7", "host": "Jun Santos", "arrival": "Walking", "friends": []})
    v = next(x for x in (await state(client, "guard"))["visits"] if x["visitor"].startswith("Red Flag"))
    assert v["flag"] == "Red flag"
    ref = v["ref"]
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("admin"))
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))).status_code == 422
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True, "extra_verification": True}, headers=H("guard"))).status_code == 200
    # Not for me
    await client.post("/api/visits", json={**VIS, "name": "Wrong Person", "phone": "0900 000 0007", "house": "B2-L7", "host": "Ana Santos", "arrival": "Walking", "friends": []})
    ref3 = next(x for x in (await state(client, "admin"))["visits"] if x["visitor"].startswith("Wrong Person"))["ref"]
    assert (await client.post(f"/api/visits/{ref3}/not-for-me", headers=H("household", "B2-L7"))).status_code == 200
    assert find(await state(client, "hoa"), ref3)["st"] == "In HOA queue"


async def test_walkin_needs_household_phone_approval(client):
    r = await client.post("/api/walkins", json={"visitor": "Walk Inn", "house": "B1-L4", "host": "", "arr": "Walking"}, headers=H("guard"))
    ref = r.json()["ref"]
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))).status_code == 409
    await client.post(f"/api/visits/{ref}/walkin-decision", json={"approve": True}, headers=H("guard"))
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))).status_code == 200


async def test_household_visibility_rule_minors_only(client):
    # a visit to Lito (adult, not the account holder) must be hidden from Maria; a visit to Paolo (minor) is visible
    await client.post("/api/visits", json={**VIS, "name": "ToLito", "phone": "0900 000 0008", "host": "Lito Reyes", "friends": []})
    await client.post("/api/visits", json={**VIS, "name": "ToPaolo", "phone": "0900 000 0009", "host": "Paolo Reyes", "friends": []})
    names = [v["visitor"] for v in (await state(client, "household", "B1-L4"))["visits"]]
    assert "ToLito" not in names and "ToPaolo" in names
    assert any(v["visitor"] == "ToLito" for v in (await state(client, "admin"))["visits"])


async def test_roles_are_enforced(client):
    assert (await client.get("/api/state")).status_code == 403
    assert (await client.post("/api/gates", json={"name": "X"}, headers=H("guard"))).status_code == 403
    assert (await client.post("/api/households/invite", json={"email": "a@b.ph"}, headers=H("hoa"))).status_code == 403
    assert (await client.post("/api/households/xxxx/verify", headers=H("guard"))).status_code == 403
    hh = await state(client, "household", "B1-L4")
    assert hh["staff"] == [] and hh["audit"] == [] and len(hh["households"]) == 1


async def test_property_isolation(client):
    other = "other-village-1a2b"
    mine = await state(client, "admin")
    theirs = await state(client, "admin", prop=other)
    assert {v["tok"] for v in mine["visits"]}.isdisjoint({v["tok"] for v in theirs["visits"]})
    assert (await client.post("/api/visits", json={**VIS, "name": "Iso Only", "phone": "0900 000 0010"}, headers={"X-Property": other})).status_code == 200
    assert not any(v["visitor"].startswith("Iso") for v in (await state(client, "admin"))["visits"])
    assert any(v["visitor"].startswith("Iso") for v in (await state(client, "admin", prop=other))["visits"])
    # an admin of one property cannot act on a visit that only exists in the other (seq numbers differ per global identity)
    other_only = max(int(v["ref"][3:]) for v in (await state(client, "admin", prop=other))["visits"])
    r = await client.post(f"/api/visits/VS-{other_only:04d}/status", json={"status": "arrived"}, headers=H("admin"))
    assert r.status_code == 404
    r = await client.post("/api/households/00000000-0000-0000-0000-000000000000/verify", headers=H("hoa"))
    assert r.status_code == 404


async def test_admin_setup_crud(client):
    a = H("admin")
    assert (await client.post("/api/households/invite", json={"email": "new@mail.ph"}, headers=a)).status_code == 200
    assert (await client.post("/api/gates", json={"name": "East gate", "type": "Deliveries"}, headers=a)).status_code == 200
    assert (await client.post("/api/badges", json={"code": "p99"}, headers=a)).status_code == 200
    assert (await client.post("/api/badges", json={"code": "P99"}, headers=a)).status_code == 409
    assert (await client.post("/api/staff", json={"name": "New Guard", "email": "ng@greenfield.ph", "role": "Guard"}, headers=a)).status_code == 200
    assert (await client.post("/api/lots", json={"lot": "b4-l9", "household": "lim@mail.ph"}, headers=a)).status_code == 200
    assert (await client.post("/api/lots", json={"lot": "B4-L9"}, headers=a)).status_code == 409  # duplicate lot
    assert (await client.post("/api/areas", json={"name": "Pool", "members": "Ana Santos"}, headers=a)).status_code == 200
    assert (await client.post("/api/areas", json={"name": "Bad", "members": "Nobody Here"}, headers=a)).status_code == 422
    st = await state(client, "admin")
    assert any(g["name"] == "East gate" for g in st["gates"]) and any(p["no"] == "P99" for p in st["passes"])
    assert any(h["st"] == "Invited" and h["holder"] == "new@mail.ph" for h in st["households"])
    assert any(r["area"] == "Pool" for r in st["rm"])
    # household form completes an invitation and moves it to Awaiting HOA, then HOA verifies
    inv = next(h for h in st["households"] if h["holder"] == "new@mail.ph")
    assert (await client.post(f"/api/households/{inv['id']}/verify", headers=H("hoa"))).status_code == 422  # incomplete form
    r = await client.patch(f"/api/households/{inv['id']}", json={"owner": "Newman", "lot": "B4-L1", "holder": "Nina Newman"}, headers=a)
    assert r.status_code == 200
    st = await state(client, "admin")
    assert next(h for h in st["households"] if h["id"] == inv["id"])["lot"] == "B4-L1"
    msgs = [m["subject"] for m in st["msgs"]]
    assert any("Invitation" in m for m in msgs)
    assert any("Household invited" in x["action"] for x in st["audit"])


async def test_household_form_sync_keeps_restricted_ties(client):
    st = await state(client, "household", "B2-L7")
    h = st["households"][0]
    members = [{"n": m["n"], "minor": m["minor"]} for m in h["members"]] + [{"n": "New Kid", "minor": 1}]
    r = await client.put("/api/me/household", json={"owner": h["owner"], "lot": h["lot"], "holder": h["holder"], "email": h["email"], "phone": "0917 555 0199", "members": members}, headers=H("household", "B2-L7"))
    assert r.status_code == 200
    adm = await state(client, "admin")
    assert any(x["member"] == "Jun Santos" for x in adm["rm"])  # tie survived the form save
    assert "New Kid" in [m["n"] for m in (await state(client, "household", "B2-L7"))["households"][0]["members"]]


async def test_gate_scan_finds_visit_by_qr_token(client):
    r = await client.post("/api/visits", json={**VIS, "name": "Scan Visitor", "phone": "0900 000 0077", "friends": []})
    assert r.status_code == 200
    adm = await state(client, "admin")
    v = next(x for x in adm["visits"] if x["visitor"].startswith("Scan Visitor"))
    ref, tok = v["ref"], v["tok"]
    g = H("guard")

    # a pending visit is found, but it is not approved yet
    r = await client.post("/api/visits/scan", json={"code": "VISTA:" + tok}, headers=g)
    assert r.status_code == 200, r.text
    assert r.json()["ref"] == ref and r.json()["status"] == "Pending" and r.json()["visitor"] == "Scan Visitor"

    # approved: now it says Waiting at gate; the QR text, the bare token and the reference all work
    assert (await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))).status_code == 200
    for code in ("VISTA:" + tok, tok, f" vista:{tok} ", ref, ref.lower()):
        r = await client.post("/api/visits/scan", json={"code": code}, headers=g)
        assert r.status_code == 200 and r.json()["ref"] == ref and r.json()["status"] == "Waiting at gate", (code, r.text)

    # unknown code, wrong role, and another village cannot find it
    assert (await client.post("/api/visits/scan", json={"code": "VISTA:nope-nope"}, headers=g)).status_code == 404
    assert (await client.post("/api/visits/scan", json={"code": "VS-9999"}, headers=g)).status_code == 404
    assert (await client.post("/api/visits/scan", json={"code": tok}, headers=H("household", "B1-L4"))).status_code == 403
    assert (await client.post("/api/visits/scan", json={"code": tok}, headers=H("guard", prop="other-village-1a2b"))).status_code == 404


# ---------------------------------------------------------------- household form, HOA verification, gate photo, exit
async def put_form(client, lot_hdr, **kw):
    return await client.put("/api/me/household", json=kw, headers=H("household", lot_hdr))


def form_of(h, **over):
    f = {"owner": h["owner"], "lot": h["lot"], "holder": h["holder"], "email": h["email"], "phone": "0917 555 0100",
         "members": [{"n": m["n"], "minor": bool(m["minor"])} for m in h["members"]]}
    f.update(over)
    return f


async def test_household_form_rejects_bad_input_with_plain_messages(client):
    h = (await state(client, "household", "B3-L5"))["households"][0]
    for over, msg in [({"owner": "  "}, "owner name"), ({"holder": ""}, "account holder"), ({"lot": "###"}, "house number"), ({"lot": "  "}, "house number"),
                      ({"email": "nope"}, "valid email"), ({"phone": "abc"}, "valid phone"), ({"email": ""}, "email address"), ({"phone": ""}, "phone number"), ({"members": []}, "List the people"),
                      ({"holder": "Somebody Else"}, "one of the people listed"),
                      ({"members": [{"n": h["holder"], "minor": True}, {"n": "Gio Garcia", "minor": False}]}, "must be an adult")]:
        r = await client.put("/api/me/household", json=form_of(h, **over), headers=H("household", "B3-L5"))
        assert r.status_code == 422 and msg in r.json()["detail"], (over, r.text)
    # nothing was saved by the failed attempts, and a clean save with a loose lot format is normalised
    r = await client.put("/api/me/household", json=form_of(h, lot="b3 - l5"), headers=H("household", "B3-L5"))
    assert r.status_code == 200 and r.json()["status"] == "awaiting" and not r.json()["reverify"]


async def test_removing_a_host_from_the_form_does_not_crash_and_keeps_the_visit(client):
    h = (await state(client, "household", "B2-L2"))["households"][0]
    await client.post("/api/visits", json={**VIS, "name": "Host Gone", "phone": "0900 000 0201", "house": "B2-L2", "host": h["holder"], "friends": []})
    kept = [{"n": "Rosa Dela Rosa", "minor": False}, {"n": "New Person", "minor": False}]
    # the visit's host is the account holder; remove and re-add under a changed list (holder must stay listed, so drop another person first)
    r = await client.put("/api/me/household", json=form_of(h, holder="Rosa Dela Rosa", members=kept), headers=H("household", "B2-L2"))
    assert r.status_code == 200
    # a person who hosts a visit can now be removed (this used to be a 500)
    st = await state(client, "admin")
    other = next(x for x in st["households"] if x["lot"] == "B1-L4")
    await client.post("/api/visits", json={**VIS, "name": "Lito Guest", "phone": "0900 000 0202", "host": "Lito Reyes", "friends": []})
    keep = [m for m in other["members"] if m["n"] != "Lito Reyes"]
    r = await client.put("/api/me/household", json=form_of(other, members=[{"n": m["n"], "minor": bool(m["minor"])} for m in keep]), headers=H("household", "B1-L4"))
    assert r.status_code == 200, r.text
    v = next(x for x in (await state(client, "admin"))["visits"] if x["visitor"].startswith("Lito Guest"))
    assert v["host"] == "Lito Reyes"   # the visit still shows who was asked for


async def test_verified_household_that_changes_lot_must_be_verified_again(client):
    h = (await state(client, "household", "B2-L7"))["households"][0]
    assert h["st"] == "Verified"
    r = await client.put("/api/me/household", json=form_of(h, lot="B2-L8"), headers=H("household", "B2-L7"))
    assert r.status_code == 200 and r.json()["reverify"] is True
    h2 = next(x for x in (await state(client, "admin"))["households"] if x["id"] == h["id"])
    assert h2["st"] == "Awaiting HOA" and h2["lot"] == "B2-L8" and h2["vby"] == ""
    # while unverified it cannot approve
    await client.post("/api/visits", json={**VIS, "name": "Lot Mover", "phone": "0900 000 0203", "house": "B2-L8", "host": "", "friends": []})
    ref = next(x for x in (await state(client, "admin"))["visits"] if x["visitor"].startswith("Lot Mover"))["ref"]
    assert (await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B2-L8"))).status_code == 403
    # HOA verifies it again; verifying twice is refused
    assert (await client.post(f"/api/households/{h['id']}/verify", headers=H("hoa", None))).status_code == 200
    assert (await client.post(f"/api/households/{h['id']}/verify", headers=H("hoa", None))).status_code == 409
    h3 = next(x for x in (await state(client, "admin"))["households"] if x["id"] == h["id"])
    assert h3["st"] == "Verified" and h3["vby"] and h3["vat"]


async def test_gate_check_stores_a_real_entry_photo_and_exit_can_see_it(client):
    await client.post("/api/visits", json={**VIS, "name": "Photo Car", "phone": "0900 000 0204", "friends": ["Pal"]})
    ref = next(x for x in (await state(client, "admin"))["visits"] if x["visitor"].startswith("Photo Car"))["ref"]
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    g = H("guard")
    ok = {"plate_ok": True, "color_ok": True, "type_ok": True}
    # the old "photo: true" with no picture is no longer accepted; neither is a non-JPEG or a corrupt string
    for veh in ({"photo": True, **ok}, {"photo_data": "aGVsbG8=", **ok}, {"photo_data": "%%%not base64%%%", **ok}):
        assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True, "vehicle": veh}, headers=g)).status_code == 422
    assert (await client.get(f"/api/visits/{ref}/entry-photo", headers=g)).status_code == 404
    r = await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True, "vehicle": {"photo_data": "data:image/jpeg;base64," + JPEG_B64, **ok}}, headers=g)
    assert r.status_code == 200, r.text
    p = await client.get(f"/api/visits/{ref}/entry-photo", headers=g)
    assert p.status_code == 200 and p.headers["content-type"] == "image/jpeg" and p.content.startswith(b"\xff\xd8\xff")
    assert (await client.get(f"/api/visits/{ref}/entry-photo", headers=H("household", "B1-L4"))).status_code == 403
    assert find(await state(client, "guard"), ref)["chk"]["photo"] == 1


async def test_photo_purge_removes_expired_photos(client, app_pool):
    from app.core import purge_photos
    await client.post("/api/visits", json={**VIS, "name": "Old Photo", "phone": "0900 000 0205", "friends": []})
    ref = next(x for x in (await state(client, "admin"))["visits"] if x["visitor"].startswith("Old Photo"))["ref"]
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    veh = {"photo_data": JPEG_B64, "plate_ok": True, "color_ok": True, "type_ok": True}
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True, "vehicle": veh}, headers=H("guard"))).status_code == 200
    await app_pool.execute("UPDATE village_entry_photos SET delete_after = now() - interval '1 minute'")
    assert await purge_photos(app_pool) >= 1
    assert (await client.get(f"/api/visits/{ref}/entry-photo", headers=H("guard"))).status_code == 404


async def test_exit_by_pass_number_and_pass_not_returned_only_loses_the_missing_passes(client):
    await client.post("/api/visits", json={**VIS, "name": "Exit Group", "phone": "0900 000 0206", "arrival": "Walking", "friends": ["Exit Two", "Exit Three"]})
    ref = next(x for x in (await state(client, "admin"))["visits"] if x["visitor"].startswith("Exit Group"))["ref"]
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    g = H("guard")
    codes = (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=g)).json()["passes"]
    # scan the first pass out by its number (any case); scanning it again is harmless
    r = await client.post(f"/api/visits/{ref}/exit-scan", json={"pass_code": codes[0].lower()}, headers=g)
    assert r.status_code == 200 and r.json()["already"] is False
    assert (await client.post(f"/api/visits/{ref}/exit-scan", json={"pass_code": codes[0]}, headers=g)).json()["already"] is True
    # a pass from somewhere else, or nothing at all, is refused
    assert (await client.post(f"/api/visits/{ref}/exit-scan", json={"pass_code": "NOPE"}, headers=g)).status_code == 404
    assert (await client.post(f"/api/visits/{ref}/exit-scan", json={}, headers=g)).status_code == 422
    # the other two never come back: close with "Pass not returned"
    assert (await client.post(f"/api/visits/{ref}/close", json={"reason": "Pass not returned"}, headers=g)).status_code == 200
    by = {p["no"]: p["st"] for p in (await state(client, "admin"))["passes"]}
    assert by[codes[0]] == "Available" and by[codes[1]] == "Lost" and by[codes[2]] == "Lost"


async def test_lookup_does_not_crash_for_a_lot_that_is_not_block_and_lot(client, app_pool):
    await app_pool.execute("UPDATE village_households SET lot_code='Clubhouse' WHERE lot_code='B2-L2'")
    await client.post("/api/visits", json={**VIS, "name": "Odd Lot", "phone": "0900 000 0207", "house": "Clubhouse", "host": "", "arrival": "Walking", "friends": []})
    ref = next(x for x in (await state(client, "admin"))["visits"] if x["visitor"].startswith("Odd Lot"))["ref"]
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "Clubhouse"))
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))).status_code == 200
    r = await client.post("/api/visits/lookup", json={"name": "Odd Lot", "phone": "0900 000 0207"})
    assert r.status_code == 200 and r.json()[0]["status"] == "Checked in" and "directions" not in r.json()[0]
    await app_pool.execute("UPDATE village_households SET lot_code='B2-L2' WHERE lot_code='Clubhouse'")


async def test_household_form_accepts_a_plain_house_number(client):
    h = (await state(client, "household", "B3-L5"))["households"][0]
    r = await client.put("/api/me/household", json=form_of(h, lot=" 25a "), headers=H("household", "B3-L5"))
    assert r.status_code == 200, r.text
    assert next(x for x in (await state(client, "admin"))["households"] if x["id"] == h["id"])["lot"] == "25A"
    r = await client.put("/api/me/household", json=form_of(h, lot="b3 - l5"), headers=H("household", "25A"))   # and back
    assert r.status_code == 200


# ---------------------------------------------------------------- property link and the two doors
async def test_village_page_lookup_gives_the_name_and_hides_everything_else(client):
    r = await client.get("/api/property/greenfield-village-7f3a")
    assert r.status_code == 200 and r.json() == {"name": "Greenfield Village", "slug": "greenfield-village-7f3a"}
    assert (await client.get("/api/property/GREENFIELD-VILLAGE-7F3A")).status_code == 200   # a link typed in capitals still works
    # a wrong, malformed or reserved link all look the same
    bodies = set()
    for s in ("greenfield-village-0000", "nope", "a", "api", "x" * 80, "bad_slug"):
        r = await client.get(f"/api/property/{s}")
        assert r.status_code in (404, 405), (s, r.status_code)
        if r.status_code == 404:
            bodies.add(r.text)
    assert len(bodies) == 1


async def test_sign_in_says_which_village_and_follows_the_x_property_header(client):
    a = (await client.post("/api/session", json={"role": "admin"}, headers={"X-Property": "other-village-1a2b"})).json()
    assert a["property"]["slug"] == "other-village-1a2b" and a["property"]["name"]
    d = (await client.post("/api/session", json={"role": "guard"})).json()       # no header: the default village
    assert d["property"]["slug"] == "greenfield-village-7f3a"
    # an unknown village cannot be signed in to
    r = await client.post("/api/session", json={"role": "admin"}, headers={"X-Property": "no-such-village-0000"})
    assert r.status_code >= 400
    # the snapshot names the village too
    assert (await state(client, "admin"))["prop"] == {"name": "Greenfield Village", "slug": "greenfield-village-7f3a"}


async def test_renaming_the_village_in_settings_changes_the_property_name(client, app_pool):
    r = await client.put("/api/settings", json={"tab0": ["Palm Grove Village", "/ignored"]}, headers=H("admin", prop="other-village-1a2b"))
    assert r.status_code == 200
    assert (await client.get("/api/property/other-village-1a2b")).json()["name"] == "Palm Grove Village"
    assert (await client.get("/api/property/greenfield-village-7f3a")).json()["name"] == "Greenfield Village"   # the other village is untouched


def test_generated_village_links_are_name_plus_random_code():
    from app.core import make_slug, valid_slug
    a, b = make_slug("Greenfield Village"), make_slug("Greenfield Village")
    assert a != b and a.startswith("greenfield-village-") and valid_slug(a) and len(a.rsplit("-", 1)[1]) == 4
    assert make_slug("Ñandú  Park!!").startswith("nandu-park-") and make_slug("   ").startswith("village-")
    assert not valid_slug("api") and not valid_slug("Has Caps") and not valid_slug("a")


# ---- visitor "ID or photo" from the form: stored, guard/admin only, deleted after retention
async def test_visitor_id_photo_stored_and_guard_only(client):
    r = await client.post("/api/visits", json={**VIS, "name": "Id Photo Person", "phone": "0900 000 7777", "id_photo": JPEG_B64})
    assert r.status_code == 200 and r.json() == {"message": "Your request was sent."}
    adm = await state(client, "admin")
    v = next(x for x in adm["visits"] if x["visitor"].startswith("Id Photo Person"))
    assert v["idp"] == 1
    ref = v["ref"]
    assert (await client.get(f"/api/visits/{ref}/id-photo", headers=H("guard"))).status_code == 200
    assert (await client.get(f"/api/visits/{ref}/id-photo", headers=H("household", "B1-L4"))).status_code == 403
    assert (await client.get(f"/api/visits/{ref}/id-photo", headers=H("guard", None, "other-village-1a2b"))).status_code == 404
    bad = await client.post("/api/visits", json={**VIS, "name": "Bad Id", "phone": "0900 000 7778", "id_photo": "bm90IGEganBlZw=="})
    assert bad.status_code == 422
    # the public form must carry the ID or photo; only the guard's walk-in entry may go without one
    no = await client.post("/api/visits", json={**VIS, "name": "No Id", "phone": "0900 000 7779", "id_photo": None})
    assert no.status_code == 422 and "ID or a photo" in no.json()["detail"]
    adm = await state(client, "admin")
    assert not any(x["visitor"].startswith("No Id") for x in adm["visits"])
    w = await client.post("/api/walkins", json={"visitor": "Walk No Id", "house": "B1-L4"}, headers=H("guard"))
    assert w.status_code == 200
    adm = await state(client, "admin")
    assert next(x for x in adm["visits"] if x["visitor"].startswith("Walk No Id"))["idp"] == 0


async def test_walkin_group_and_declared_vehicle_get_a_pass_each(client):
    for n in range(1, 4):   # earlier tests may have used up the seeded passes
        await client.post("/api/badges", json={"code": f"WK{n}"}, headers=H("admin"))
    r = await client.post("/api/walkins", json={"visitor": "Group Walker", "house": "B1-L4", "host": "", "arr": "Own vehicle",
                                                 "kind": "Vios", "color": "White", "plate": "WLK 123", "purpose": "Delivery",
                                                 "friends": ["Walker Two", "Walker Three"]}, headers=H("guard"))
    assert r.status_code == 200, r.text
    ref = r.json()["ref"]
    v = find(await state(client, "guard"), ref)
    assert v["people"] == ["Group Walker", "Walker Two", "Walker Three"]
    assert v["veh"] == {"kind": "Vios", "color": "White", "plate": "WLK 123"}
    assert v["st"] == "Pending" or v["w"] == 1
    # still no pass until the household approves by phone
    assert (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))).status_code == 409
    await client.post(f"/api/visits/{ref}/walkin-decision", json={"approve": True}, headers=H("guard"))
    out = await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True, "vehicle": {
        "photo_data": JPEG_B64, "plate_ok": True, "color_ok": True, "type_ok": True}}, headers=H("guard"))
    assert out.status_code == 200, out.text
    assert len(out.json()["passes"]) == 3


async def test_walkin_rejects_a_name_listed_twice(client):
    r = await client.post("/api/walkins", json={"visitor": "Dup Name", "house": "B1-L4", "friends": ["dup name"]}, headers=H("guard"))
    assert r.status_code == 422


async def test_hoa_todays_visits_flag_and_guard_notices(client):
    await client.post("/api/visits", json={**VIS, "name": "Today Person", "phone": "0900 111 0001", "arrival": "Walking", "friends": []})
    old = await client.post("/api/visits", json={**VIS, "name": "Next Month", "phone": "0900 111 0002", "arrival": "Walking", "friends": [],
                                                 "when": "2030-01-15T10:00"})
    assert old.status_code == 200
    vs = (await state(client, "hoa"))["visits"]
    assert next(v for v in vs if v["visitor"] == "Today Person")["today"] == 1      # no date given: requested today
    assert next(v for v in vs if v["visitor"] == "Next Month")["today"] == 0         # scheduled for another day
    # the guard gets the arrival notices in their own state, the household and HOA do not
    ref = next(v for v in vs if v["visitor"] == "Today Person")["ref"]
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    code = (await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))).json()["passes"][0]
    await client.post(f"/api/passes/{code}/arrived", headers=H("household", "B1-L4"))
    notes = (await state(client, "guard"))["msgs"]
    assert any("Today Person" in m["subject"] and "arrived at the house" in m["subject"] for m in notes)
    assert all(m["to"] in ("Guard", "Guard and Admin") for m in notes)
    assert (await state(client, "hoa"))["msgs"] == []
    assert (await state(client, "household", "B1-L4"))["msgs"] == []


async def test_admin_edits_household_people_and_contact(client):
    a = H("admin")
    st = await state(client, "admin")
    h = next(x for x in st["households"] if x["lot"] == "B2-L2")
    r = await client.patch(f"/api/households/{h['id']}", json={"lot": "b2 - l2", "phone": "0917 000 1111", "members": [
        {"n": "Rosa Dela Rosa", "minor": False}, {"n": "Tito Dela Rosa", "minor": True}]}, headers=a)
    assert r.status_code == 200, r.text
    st = await state(client, "admin")
    h2 = next(x for x in st["households"] if x["id"] == h["id"])
    assert h2["lot"] == "B2-L2" and h2["ph"] == "0917 000 1111" and [m["n"] for m in h2["members"]] == ["Rosa Dela Rosa", "Tito Dela Rosa"]
    assert "Tito Dela Rosa (minor)" in next(l for l in st["lots"] if l["lot"] == "B2-L2")["people"]
    # the account holder must stay on the list as an adult
    r = await client.patch(f"/api/households/{h['id']}", json={"members": [{"n": "Tito Dela Rosa", "minor": True}]}, headers=a)
    assert r.status_code == 422
    r = await client.patch(f"/api/households/{h['id']}", json={"lot": "###"}, headers=a)
    assert r.status_code == 422


async def test_invite_twice_and_invited_owner_is_blank(client):
    a = H("admin")
    assert (await client.post("/api/households/invite", json={"email": "twice@mail.ph"}, headers=a)).status_code == 200
    assert (await client.post("/api/households/invite", json={"email": "Twice@mail.ph"}, headers=a)).status_code == 409
    st = await state(client, "admin")
    inv = next(x for x in st["households"] if x["email"] == "twice@mail.ph")
    assert inv["owner"] == ""


async def test_settings_are_validated_and_applied(client):
    a = H("admin")
    ok = ["Only visits to minors", "HOA office", "Same pass as a normal visit", "Red banner with host details and extra verification tick", "3", "30"]
    for bad in (["x"] * 4 + ["0", "30"], ["x"] * 4 + ["abc", "30"], ["x"] * 4 + ["3", "9999"]):
        assert (await client.put("/api/settings", json={"tab1": bad}, headers=a)).status_code == 422
    # Who verifies households: with "Admin" the HOA office is refused
    h = (await state(client, "admin"))["households"]
    pend = next(x for x in h if x["lot"] == "B3-L2")
    assert (await client.put("/api/settings", json={"tab1": [ok[0], "Admin"] + ok[2:]}, headers=a)).status_code == 200
    r = await client.post(f"/api/households/{pend['id']}/verify", headers=H("hoa"))
    assert r.status_code == 403 and "Admin verifies" in r.json()["detail"]
    # Primary adult sees all visits: a non-holder adult's visitor shows up for the holder only after the setting changes.
    # Earlier tests rename lots and remove members, so look up a verified household that still has such an adult.
    hh = next(x for x in h if x["st"] == "Verified" and any(not m["minor"] and m["n"] != x["holder"] for m in x["members"]))
    adult = next(m["n"] for m in hh["members"] if not m["minor"] and m["n"] != hh["holder"])
    seen = lambda st: [v for v in st["visits"] if v["visitor"].startswith("Seen By Holder")]
    r0 = await client.post("/api/visits", json={**VIS, "name": "Seen By Holder", "phone": "0900 000 0301", "house": hh["lot"], "host": adult, "friends": []})
    assert r0.status_code == 200, r0.text
    assert not seen(await state(client, "household", hh["lot"]))
    assert (await client.put("/api/settings", json={"tab1": ["All visits", "HOA office"] + ok[2:]}, headers=a)).status_code == 200
    assert seen(await state(client, "household", hh["lot"]))
    assert (await client.put("/api/settings", json={"tab1": ok}, headers=a)).status_code == 200   # back to the defaults for the other tests


async def test_missing_after_uses_the_admin_hours(client):
    a = H("admin")
    ok = ["Only visits to minors", "HOA office", "Same pass as a normal visit", "Red banner with host details and extra verification tick", "3", "30"]
    await client.put("/api/settings", json={"tab1": ok[:4] + ["6", "30"]}, headers=a)
    await client.post("/api/visits", json={**VIS, "name": "Six Hours", "phone": "0900 000 0302", "arrival": "Walking", "friends": []})
    st = await state(client, "admin")
    ref = next(v["ref"] for v in st["visits"] if v["visitor"].startswith("Six Hours"))
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    chk = await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))
    assert chk.status_code == 200, chk.text
    assert (await client.post("/api/jobs/missing?simulate_hours=4", headers=a)).json()["flagged"] == 0   # 6 h setting: 4 h is not enough
    assert (await client.post("/api/jobs/missing?simulate_hours=7", headers=a)).json()["flagged"] >= 1
    st = await state(client, "admin")
    assert any("6 hours" in x["detail"] for x in st["alerts"])
    await client.put("/api/settings", json={"tab1": ok}, headers=a)


async def test_lot_and_household_stay_in_step(client):
    a = H("admin")
    st = await state(client, "admin")
    lot = next(l for l in st["lots"] if l["lot"] == "B2-L2")
    # renaming a linked lot renames the household's lot too
    assert (await client.patch(f"/api/lots/{lot['id']}", json={"lot": "b2 - l3", "household": ""}, headers=a)).status_code == 200
    st = await state(client, "admin")
    assert next(h for h in st["households"] if h["owner"] == "Dela Rosa")["lot"] == "B2-L3"
    assert (await client.patch(f"/api/lots/{lot['id']}", json={"lot": "B2-L2", "household": ""}, headers=a)).status_code == 200
    # a household that already has a lot cannot be linked to a second one, an unknown name is explained
    r = await client.post("/api/lots", json={"lot": "B9-L9", "household": "Reyes"}, headers=a)
    assert r.status_code == 409 and "already lives" in r.json()["detail"]
    r = await client.post("/api/lots", json={"lot": "B9-L9", "household": "Nobody Here"}, headers=a)
    assert r.status_code == 422
    assert (await client.post("/api/lots", json={"lot": "###"}, headers=a)).status_code == 422


async def test_wayfinding_route_position_and_gate_edit(client):
    a = H("admin")
    st = await state(client, "admin")
    rt = next(r for r in st["routes"] if r["lot"] == "B1-L4")
    assert rt["route"].startswith("Main gate") and not rt["custom"]
    assert (await client.put(f"/api/lots/{rt['id']}/route", json={"route": "Main gate, turn left at the clubhouse, third house"}, headers=a)).status_code == 200
    st = await state(client, "admin")
    rt = next(r for r in st["routes"] if r["lot"] == "B1-L4")
    assert rt["custom"] and "clubhouse" in rt["route"]
    assert (await client.put(f"/api/lots/{rt['id']}/route", json={"route": ""}, headers=a)).status_code == 200   # back to automatic
    assert (await client.put(f"/api/lots/{rt['id']}/pos", json={"x": 40.5, "y": 22}, headers=a)).status_code == 200
    assert (await client.put(f"/api/lots/{rt['id']}/pos", json={"x": 140, "y": 22}, headers=a)).status_code == 422
    g = next(g for g in st["gates"] if g["name"] == "East gate")
    assert (await client.put(f"/api/gates/{g['id']}/pos", json={"x": 50, "y": 95}, headers=a)).status_code == 200
    assert (await client.patch(f"/api/gates/{g['id']}", json={"name": "East gate 2"}, headers=a)).status_code == 200
    st = await state(client, "admin")
    g2 = next(x for x in st["gates"] if x["id"] == g["id"])
    assert g2["name"] == "East gate 2" and g2["st"] == "Active" and g2["x"] == 50
    assert next(l for l in st["lots"] if l["lot"] == "B1-L4")["x"] == 40.5
    assert (await client.patch(f"/api/gates/{g['id']}", json={"name": "East gate"}, headers=a)).status_code == 200


async def test_village_map_is_stored_on_the_server(client):
    a = H("admin")
    import base64
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
    assert (await client.get("/api/map", headers=a)).status_code == 404
    assert (await client.put("/api/map", json={"data": "data:image/png;base64," + png}, headers=a)).status_code == 200
    r = await client.get("/api/map", headers=a)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(b"\x89PNG")
    assert (await state(client, "admin"))["map"]["has"] is True
    assert (await client.put("/api/map", json={"data": base64.b64encode(b"just text").decode()}, headers=a)).status_code == 422
    assert (await client.put("/api/map", json={"data": png}, headers=H("guard"))).status_code == 403
    assert (await client.put("/api/map", json={"data": base64.b64encode(b"%PDF-1.4 x").decode()}, headers=a)).status_code == 200
    assert (await client.get("/api/map", headers=a)).headers["content-type"] == "application/pdf"
    assert (await client.delete("/api/map", headers=a)).status_code == 200
    assert (await state(client, "admin"))["map"]["has"] is False


async def test_reports_come_from_real_visits(client):
    st = await state(client, "admin")
    rep = st["report"]
    assert len(rep["days"]) == 7 and sum(n for _, n in rep["days"]) == rep["week"] and rep["week"] >= 1
    assert rep["today"] >= 1 and rep["people"] >= rep["week"]
    assert {k for k, _ in rep["arr"]} == {"Walking", "Own vehicle", "Ride"} and sum(n for _, n in rep["arr"]) == rep["week"]
    assert any(k == "Passes lost" for k, _ in rep["exc"])
    assert "report" not in await state(client, "guard")


async def test_visit_forms_reject_bad_input_with_plain_messages(client):
    base = {**VIS, "phone": "0900 777 0001", "friends": []}
    for over, msg in [({"name": "   "}, "visitor's name"), ({"house": "  "}, "house number"), ({"arrival": "teleport"}, "arriving"),
                      ({"when": "not a date"}, "date and time"), ({"friends": ["Ann", "ann"]}, "listed twice"),
                      ({"name": "Ann", "friends": ["ANN"]}, "listed twice"), ({"friends": [f"P{i}" for i in range(25)]}, "at most 20")]:
        r = await client.post("/api/visits", json={**base, **over})
        assert r.status_code == 422 and msg in r.json()["detail"], (over, r.text)
    # a blank friend row is just ignored; a good request still goes through
    assert (await client.post("/api/visits", json={**base, "name": "Tidy Group", "friends": ["Ok One", "  "]})).status_code == 200
    # the guard's walk-in form: a too-short phone is a 422, never a server error
    r = await client.post("/api/walkins", json={"visitor": "Short Phone", "house": "B1-L4", "phone": "12"}, headers=H("guard"))
    assert r.status_code == 422 and "phone" in r.json()["detail"]
    r = await client.post("/api/walkins", json={"visitor": "Twin", "house": "B1-L4", "friends": ["twin"]}, headers=H("guard"))
    assert r.status_code == 422 and "listed twice" in r.json()["detail"]


async def test_admin_forms_reject_bad_input(client):
    a = H("admin")
    assert (await client.post("/api/households/invite", json={"email": "a@b"}, headers=a)).status_code == 422
    assert (await client.post("/api/staff", json={"name": "Gus", "email": "gus@mail.ph", "role": "Guard"}, headers=a)).status_code == 200
    assert (await client.post("/api/staff", json={"name": "Gus Two", "email": "GUS@mail.ph", "role": "Guard"}, headers=a)).status_code == 409
    assert (await client.post("/api/staff", json={"name": "No Mail", "email": "nomail", "role": "Guard"}, headers=a)).status_code == 422
    uid = next(x["id"] for x in (await state(client, "admin"))["staff"] if x["email"] == "gus@mail.ph")
    assert (await client.patch(f"/api/staff/{uid}", json={"email": "edgar@greenfield.ph"}, headers=a)).status_code == 409   # taken by another account
    assert (await client.patch(f"/api/staff/{uid}", json={"name": "  "}, headers=a)).status_code == 422
    assert (await client.post("/api/gates", json={"name": "   "}, headers=a)).status_code == 422
    assert (await client.post("/api/areas", json={"name": "Pool", "members": ""}, headers=a)).status_code == 200
    aid = next(x["id"] for x in (await state(client, "admin"))["areas"] if x["area"] == "Pool")
    assert (await client.patch(f"/api/areas/{aid}", json={"name": " "}, headers=a)).status_code == 422
    for junk in ({"zz": [1]}, {"tab1": "abc"}, {"tab0": [{"a": 1}]}, {"tab2": [True] * 40}):
        assert (await client.put("/api/settings", json=junk, headers=a)).status_code == 422


async def test_published_site_ignores_the_demo_clock(client, monkeypatch):
    """simulate_hours is a demo button. With a staff code set (a real site) a guard must not be able to flag visitors Missing early."""
    from app import config
    await client.post("/api/badges", json={"code": "CLK1"}, headers=H("admin"))   # earlier tests may have used up the seeded passes
    await client.post("/api/visits", json={**VIS, "name": "Clock Test", "phone": "0900 777 0002", "arrival": "Walking", "friends": []})
    ref = next(v["ref"] for v in (await state(client, "admin"))["visits"] if v["visitor"] == "Clock Test")
    assert (await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))).status_code == 200
    ci = await client.post(f"/api/visits/{ref}/check-in", json={"id_checked": True}, headers=H("guard"))
    assert ci.status_code == 200, ci.text
    monkeypatch.setattr(config, "STAFF_ACCESS_CODE", "open sesame")
    monkeypatch.setattr(config, "SECRET_KEY", "test-secret-key-0123456789")
    tok = (await client.post("/api/session", json={"role": "guard", "code": "open sesame"})).json()["token"]
    r = await client.post("/api/jobs/missing?simulate_hours=48", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 200 and r.json()["flagged"] == 0
    monkeypatch.setattr(config, "STAFF_ACCESS_CODE", "")   # demo mode: the button still works for the walkthrough
    assert (await client.post("/api/jobs/missing?simulate_hours=48", headers=H("guard"))).json()["flagged"] >= 1


# ---- public visitor request: every documented field is required; the guard's walk-in is not held to the same list
async def _count(app_pool):
    return await app_pool.fetchval("SELECT count(*) FROM visits")


async def test_public_request_requires_every_documented_field(client, app_pool):
    before = await _count(app_pool)
    full = public_visit(name="Complete Person", phone="0917 123 4567", purpose="Family dinner")
    cases = [
        ("name missing", {"name": ""}, "visitor's name"),
        ("name blank", {"name": "   "}, "visitor's name"),
        ("phone blank", {"phone": ""}, "phone number"),
        ("phone spaces", {"phone": "     "}, "phone number"),
        ("phone too short", {"phone": "0955"}, "valid phone number"),
        ("phone without digits", {"phone": "call me please"}, "valid phone number"),
        ("house blank", {"house": "  "}, "house number"),
        ("ID missing", {"id_photo": None}, "ID or a photo"),
        ("ID blank", {"id_photo": "   "}, "ID or a photo"),
        ("ID not a JPEG", {"id_photo": "bm90IGEganBlZw=="}, "JPEG"),
        ("ID not base64", {"id_photo": "@@@not base64@@@"}, "could not be read"),
        ("purpose missing", {"purpose": ""}, "purpose"),
        ("purpose blank", {"purpose": "   "}, "purpose"),
        ("purpose too long", {"purpose": "x" * 201}, "200 characters"),
        ("date and time missing", {"when": None}, "date and time"),
        ("date and time blank", {"when": "  "}, "date and time"),
        ("date without a time", {"when": "2030-01-15"}, "date and time"),
        ("date and time unreadable", {"when": "next tuesday"}, "date and time"),
        ("arrival unknown", {"arrival": "teleport"}, "arriving"),
    ]
    for label, over, msg in cases:
        r = await client.post("/api/visits", json={**full, **over})
        assert r.status_code == 422 and msg in r.json()["detail"], (label, r.status_code, r.text)
    # the fields themselves may be left out of the request entirely, not only sent empty
    for k in ("phone", "id_photo", "purpose", "when"):
        body = {x: y for x, y in full.items() if x != k}
        r = await client.post("/api/visits", json=body)
        assert r.status_code == 422, (k, r.text)
    assert await _count(app_pool) == before          # nothing was saved by any of the refused requests
    ok = await client.post("/api/visits", json=full)
    assert ok.status_code == 200 and ok.json() == {"message": "Your request was sent."}
    assert await _count(app_pool) == before + 1


async def test_public_request_keeps_only_the_truly_optional_fields_optional(client):
    # the person visited, the email, the vehicle details and the friends may be blank
    r = await client.post("/api/visits", json=public_visit(name="Bare Minimum", phone="0917 000 1111", host="", email="", kind="", color="", plate="", friends=[]))
    assert r.status_code == 200, r.text
    st = await state(client, "admin")
    v = next(x for x in st["visits"] if x["visitor"].startswith("Bare Minimum"))
    assert v["idp"] == 1                                                   # the ID photo was stored
    r = await client.post("/api/visits", json=public_visit(name="Spaced Out", phone="  0917 000 2222  ", purpose="  Birthday   party  "))
    assert r.status_code == 200, r.text


async def test_public_request_stores_the_cleaned_values(client, app_pool):
    r = await client.post("/api/visits", json=public_visit(name="Clean Values", phone="  0917 000 3333 ", purpose="  Birthday   party ", when="2030-01-15 18:30"))
    assert r.status_code == 200, r.text
    row = await app_pool.fetchrow("SELECT visitor_phone, purpose, visit_at FROM village_visit_details WHERE visitor_name='Clean Values'")
    assert row["visitor_phone"] == "0917 000 3333" and row["purpose"] == "Birthday party"
    assert row["visit_at"] is not None and row["visit_at"].year == 2030


async def test_walkin_needs_only_what_a_guard_can_know(client, app_pool):
    before = await _count(app_pool)
    # name and house are enough: no phone, purpose, date or ID photo is asked of the guard
    r = await client.post("/api/walkins", json={"visitor": "Gate Walker", "house": "B1-L4"}, headers=H("guard"))
    assert r.status_code == 200, r.text
    row = await app_pool.fetchrow("SELECT visitor_phone, purpose, visit_at, walk_in FROM village_visit_details WHERE visitor_name='Gate Walker'")
    assert row["walk_in"] is True and row["visitor_phone"] == "walk-in" and row["purpose"] == "" and row["visit_at"] is None
    assert await app_pool.fetchval("SELECT count(*) FROM village_id_photos p JOIN village_visit_details d ON d.visit_id=p.visit_id WHERE d.visitor_name='Gate Walker'") == 0
    # what a guard does have to give is still checked
    for body, msg in [({"visitor": "  ", "house": "B1-L4"}, "name"), ({"visitor": "No House", "house": "  "}, "house"),
                      ({"visitor": "Bad Ride", "house": "B1-L4", "arr": "teleport"}, "arriving"),
                      ({"visitor": "Long One", "house": "B1-L4", "purpose": "x" * 201}, "200 characters")]:
        r = await client.post("/api/walkins", json=body, headers=H("guard"))
        assert r.status_code == 422 and msg in r.json()["detail"], (body, r.text)
    assert await _count(app_pool) == before + 1
    # a walk-in is entered by the guard or the Admin only: never by the public, a household or the HOA office
    assert (await client.post("/api/walkins", json={"visitor": "Sneaky", "house": "B1-L4"})).status_code == 403
    assert (await client.post("/api/walkins", json={"visitor": "Sneaky", "house": "B1-L4"}, headers=H("household", "B1-L4"))).status_code == 403
    assert (await client.post("/api/walkins", json={"visitor": "Sneaky", "house": "B1-L4"}, headers=H("hoa"))).status_code == 403
