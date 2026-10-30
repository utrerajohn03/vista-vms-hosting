"""Password setup and change, account deactivation, and token invalidation for personal (email + password) accounts."""
from app import config
from tests.test_hosting import code_mode, super_headers, super_mode  # noqa: F401  (fixtures)

PW = "first-long-password"


def bearer(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


async def admin_headers(client):
    r = await client.post("/api/session", json={"role": "admin", "code": "open sesame"})
    assert r.status_code == 200, r.text
    return bearer(r.json()["token"])


async def make_guard(client, adm, email, password=PW, role="Guard"):
    r = await client.post("/api/staff", json={"name": "Test " + role, "email": email, "role": role, "password": password}, headers=adm)
    assert r.status_code == 200, r.text
    state = (await client.get("/api/state", headers=adm)).json()
    return next(x["id"] for x in state["staff"] if x["email"] == email)


async def sign_in(client, email, password, **kw):
    return await client.post("/api/session", json={"email": email, "password": password}, **kw)


# ------------------------------------------------------------------ password setup
async def test_account_without_a_password_cannot_sign_in_until_one_is_set(client, code_mode):
    adm = await admin_headers(client)
    uid = await make_guard(client, adm, "nopw@life.ph", password=None)
    assert (await sign_in(client, "nopw@life.ph", "")).status_code == 401
    assert (await sign_in(client, "nopw@life.ph", "anything-at-all")).status_code == 401
    assert (await client.patch(f"/api/staff/{uid}", json={"password": "short"}, headers=adm)).status_code == 422     # too short: refused, nothing saved
    assert (await sign_in(client, "nopw@life.ph", "short")).status_code == 401
    assert (await client.patch(f"/api/staff/{uid}", json={"password": PW}, headers=adm)).status_code == 200
    assert (await sign_in(client, "nopw@life.ph", PW)).status_code == 200


async def test_staff_password_is_stored_hashed_never_plain(client, code_mode, app_pool):
    adm = await admin_headers(client)
    await make_guard(client, adm, "hash@life.ph")
    stored = await app_pool.fetchval("SELECT password_hash FROM users WHERE lower(email)='hash@life.ph'")
    assert stored.startswith("scrypt$") and PW not in stored


# ------------------------------------------------------------------ password change
async def test_changing_your_password_ends_your_other_sessions_and_keeps_this_one(client, code_mode):
    adm = await admin_headers(client)
    await make_guard(client, adm, "chg@life.ph")
    t1 = (await sign_in(client, "chg@life.ph", PW)).json()["token"]      # the phone
    t2 = (await sign_in(client, "chg@life.ph", PW)).json()["token"]      # the stolen laptop
    assert (await client.put("/api/me/password", json={"current": "wrong-current-pw", "new": "second-long-password"}, headers=bearer(t1))).status_code == 403
    assert (await client.get("/api/state", headers=bearer(t1))).status_code == 200            # a refused change changes nothing
    assert (await client.put("/api/me/password", json={"current": PW, "new": "short"}, headers=bearer(t1))).status_code == 422
    assert (await sign_in(client, "chg@life.ph", PW)).status_code == 200                      # still the old password
    r = await client.put("/api/me/password", json={"current": PW, "new": "second-long-password"}, headers=bearer(t1))
    assert r.status_code == 200 and r.json()["token"]
    assert (await client.get("/api/state", headers=bearer(t2))).status_code == 401            # the other session is cut off
    assert (await client.get("/api/state", headers=bearer(t1))).status_code == 401            # so is the token that made the change ...
    assert (await client.get("/api/state", headers=bearer(r.json()["token"]))).status_code == 200   # ... the person keeps working with the new one
    assert (await sign_in(client, "chg@life.ph", PW)).status_code == 401                      # the old password is dead
    assert (await sign_in(client, "chg@life.ph", "second-long-password")).status_code == 200


async def test_admin_reset_ends_that_persons_sessions(client, code_mode):
    adm = await admin_headers(client)
    uid = await make_guard(client, adm, "reset@life.ph")
    g = bearer((await sign_in(client, "reset@life.ph", PW)).json()["token"])
    assert (await client.get("/api/state", headers=g)).status_code == 200
    assert (await client.patch(f"/api/staff/{uid}", json={"password": "reset-long-password"}, headers=adm)).status_code == 200
    assert (await client.get("/api/state", headers=g)).status_code == 401
    assert (await sign_in(client, "reset@life.ph", PW)).status_code == 401
    assert (await sign_in(client, "reset@life.ph", "reset-long-password")).status_code == 200


async def test_editing_only_the_name_does_not_log_the_person_out(client, code_mode):
    adm = await admin_headers(client)
    uid = await make_guard(client, adm, "rename@life.ph")
    g = bearer((await sign_in(client, "rename@life.ph", PW)).json()["token"])
    assert (await client.patch(f"/api/staff/{uid}", json={"name": "Renamed Person"}, headers=adm)).status_code == 200
    assert (await client.get("/api/state", headers=g)).status_code == 200


async def test_guessing_the_current_password_is_limited(client, code_mode):
    adm = await admin_headers(client)
    await make_guard(client, adm, "guess@life.ph")
    g = bearer((await sign_in(client, "guess@life.ph", PW)).json()["token"])
    codes = [(await client.put("/api/me/password", json={"current": f"wrong-guess-{i}", "new": "never-applied-pw"}, headers=g)).status_code for i in range(14)]
    assert codes[:10] == [403] * 10 and 429 in codes[10:]
    assert (await sign_in(client, "guess@life.ph", PW)).status_code == 200           # nothing was changed


async def test_a_shared_code_session_cannot_set_a_personal_password(client, code_mode):
    adm = await admin_headers(client)
    assert (await client.put("/api/me/password", json={"new": "some-long-password"}, headers=adm)).status_code == 403


async def test_households_cannot_use_the_staff_password_endpoint(client, code_mode):
    h = (await client.post("/api/session", json={"role": "household", "household_lot": "B1-L4", "code": "open sesame"})).json()
    assert (await client.put("/api/me/password", json={"new": "some-long-password"}, headers=bearer(h["token"]))).status_code == 403


# ------------------------------------------------------------------ deactivation
async def test_deactivated_account_is_cut_off_and_reactivating_does_not_revive_old_tokens(client, code_mode):
    adm = await admin_headers(client)
    uid = await make_guard(client, adm, "off@life.ph")
    old = bearer((await sign_in(client, "off@life.ph", PW)).json()["token"])
    assert (await client.patch(f"/api/staff/{uid}", json={"active": False}, headers=adm)).status_code == 200
    assert (await client.get("/api/state", headers=old)).status_code == 401
    assert (await sign_in(client, "off@life.ph", PW)).status_code == 401
    assert (await client.put("/api/me/password", json={"current": PW, "new": "after-off-password"}, headers=old)).status_code == 401
    assert (await client.patch(f"/api/staff/{uid}", json={"active": True}, headers=adm)).status_code == 200
    assert (await client.get("/api/state", headers=old)).status_code == 401           # the token from before stays dead
    fresh = await sign_in(client, "off@life.ph", PW)
    assert fresh.status_code == 200 and (await client.get("/api/state", headers=bearer(fresh.json()["token"]))).status_code == 200


async def test_deactivated_message_does_not_reveal_whether_the_account_exists(client, code_mode):
    adm = await admin_headers(client)
    uid = await make_guard(client, adm, "quiet@life.ph")
    await client.patch(f"/api/staff/{uid}", json={"active": False}, headers=adm)
    a = await sign_in(client, "quiet@life.ph", PW)
    b = await sign_in(client, "never-existed@life.ph", PW)
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


async def test_one_village_admin_cannot_change_another_villages_staff(client, code_mode):
    adm = await admin_headers(client)
    uid = await make_guard(client, adm, "mine@life.ph")
    # a real Admin token of the OTHER village (the token, not the X-Property header, decides which village a request is for)
    other = bearer((await client.post("/api/session", json={"role": "admin", "code": "open sesame"}, headers={"X-Property": "other-village-1a2b"})).json()["token"])
    r = await client.patch(f"/api/staff/{uid}", json={"active": False, "password": "hijack-long-password"}, headers=other)
    assert r.status_code == 404
    assert (await sign_in(client, "mine@life.ph", PW)).status_code == 200      # untouched: same password, still active
    # and a header cannot move a token to another village
    assert (await client.get("/api/state", headers={**adm, "X-Property": "other-village-1a2b"})).json()["prop"]["slug"] == "greenfield-village-7f3a"


# ------------------------------------------------------------------ shared staff code and Admin link
async def test_shared_code_sessions_end_when_the_shared_code_is_switched_off(client, code_mode, monkeypatch):
    adm = await admin_headers(client)
    g = bearer((await client.post("/api/session", json={"role": "guard", "code": "open sesame"})).json()["token"])
    assert (await client.get("/api/state", headers=g)).status_code == 200
    monkeypatch.setattr(config, "STAFF_CODE_LOGIN", False)
    assert (await client.get("/api/state", headers=g)).status_code == 401
    assert (await client.get("/api/state", headers=adm)).status_code == 401


async def test_personal_sessions_survive_switching_the_shared_code_off(client, code_mode, monkeypatch):
    adm = await admin_headers(client)
    await make_guard(client, adm, "keep@life.ph")
    g = bearer((await sign_in(client, "keep@life.ph", PW)).json()["token"])
    monkeypatch.setattr(config, "STAFF_CODE_LOGIN", False)
    assert (await client.get("/api/state", headers=g)).status_code == 200


async def test_household_invitation_session_survives_switching_the_shared_code_off(client, super_mode, monkeypatch):
    adm = await admin_headers(client)
    inv = await client.post("/api/households/invite", json={"email": "family@life.ph"}, headers=adm)
    assert inv.status_code == 200, inv.text
    h = await client.post("/api/session", json={"role": "household", "invite": inv.json()["link"].split("?invite=")[1]})
    assert h.status_code == 200
    monkeypatch.setattr(config, "STAFF_CODE_LOGIN", False)
    assert (await client.get("/api/state", headers=bearer(h.json()["token"]))).status_code == 200


async def test_admin_link_stops_working_once_the_admin_has_set_a_password(client, super_mode):
    S = await super_headers(client)
    j = (await client.post("/api/platform/properties", json={"name": "Link Hills", "admin_name": "Lia", "admin_email": "lia@link.ph"}, headers=S)).json()
    link = j["admin_link"].split("?admin=")[1]
    s1 = await client.post("/api/session", json={"role": "admin", "admin_link": link})
    assert s1.status_code == 200
    A = bearer(s1.json()["token"])
    assert (await client.put("/api/me/password", json={"new": "lia-long-password"}, headers=A)).status_code == 200
    again = await client.post("/api/session", json={"role": "admin", "admin_link": link})
    assert again.status_code == 401                                    # the spent link no longer opens the account
    # the Super Admin can always send a fresh one
    pid = next(p["id"] for p in (await client.get("/api/platform/overview", headers=S)).json()["properties"] if p["slug"] == j["slug"])
    fresh = (await client.post(f"/api/platform/properties/{pid}/admin-link", headers=S)).json()["admin_link"].split("?admin=")[1]
    assert (await client.post("/api/session", json={"role": "admin", "admin_link": fresh})).status_code == 200
    # and she signs in normally with her password
    assert (await client.post("/api/session", json={"email": "lia@link.ph", "password": "lia-long-password"}, headers={"X-Property": j["slug"]})).status_code == 200


async def test_replacing_the_admin_cuts_off_the_old_admins_session_and_link(client, super_mode):
    S = await super_headers(client)
    j = (await client.post("/api/platform/properties", json={"name": "Swap Hills", "admin_name": "Old Admin", "admin_email": "old@swap.ph"}, headers=S)).json()
    link = j["admin_link"].split("?admin=")[1]
    A = bearer((await client.post("/api/session", json={"role": "admin", "admin_link": link})).json()["token"])
    assert (await client.get("/api/state", headers=A)).status_code == 200
    pid = next(p["id"] for p in (await client.get("/api/platform/overview", headers=S)).json()["properties"] if p["slug"] == j["slug"])
    assert (await client.put(f"/api/platform/properties/{pid}/admin", json={"name": "New Admin", "email": "new@swap.ph"}, headers=S)).status_code == 200
    assert (await client.get("/api/state", headers=A)).status_code == 401
    assert (await client.post("/api/session", json={"role": "admin", "admin_link": link})).status_code == 401
