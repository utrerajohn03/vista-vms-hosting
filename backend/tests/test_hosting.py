"""Things that only matter once the app is published: Supabase connection settings, access code, RLS, cron."""
import pytest

from app import config
from app.db import pool_args
from tests.conftest import H, public_visit, visit_when


def test_supabase_url_handling():
    u, kw = pool_args("postgresql://postgres.abc:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres")
    assert kw["ssl"] == "require" and "statement_cache_size" not in kw
    u, kw = pool_args("postgresql://postgres.abc:pw@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?pgbouncer=true")
    assert kw["ssl"] == "require" and kw["statement_cache_size"] == 0 and "pgbouncer" not in u
    u, kw = pool_args("postgresql://u:p@localhost:5432/db")
    assert "ssl" not in kw
    u, kw = pool_args("postgresql://u:p@db.example.com:5432/db?sslmode=require")
    assert kw["ssl"] == "require" and "sslmode" not in u


async def test_rls_closes_the_rest_api(app_pool):
    async with app_pool.acquire() as c:
        off = await c.fetch("SELECT tablename FROM pg_tables t JOIN pg_class k ON k.relname=t.tablename "
                            "WHERE schemaname='public' AND NOT k.relrowsecurity")
        assert off == [], f"tables without RLS: {[r['tablename'] for r in off]}"
        await c.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon_probe') THEN CREATE ROLE anon_probe NOLOGIN; END IF; END $$")
        await c.execute("GRANT SELECT ON visits, village_households TO anon_probe")
        assert await c.fetchval("SELECT count(*) FROM visits") > 0
        async with c.transaction():
            await c.execute("SET LOCAL ROLE anon_probe")
            assert await c.fetchval("SELECT count(*) FROM visits") == 0           # the REST API role sees nothing
            assert await c.fetchval("SELECT count(*) FROM village_households") == 0


@pytest.fixture
def code_mode(monkeypatch):
    monkeypatch.setattr(config, "STAFF_ACCESS_CODE", "open sesame")
    monkeypatch.setattr(config, "SECRET_KEY", "test-secret-key")


async def test_access_code_flow(client, code_mode, monkeypatch):
    assert (await client.get("/api/config")).json()["code_required"] is True
    assert (await client.get("/api/state")).status_code == 403
    assert (await client.get("/api/state", headers=H("admin"))).status_code == 403   # role headers are ignored now
    assert (await client.post("/api/session", json={"role": "admin", "code": "wrong"})).status_code == 401
    assert (await client.post("/api/session", json={"role": "admin"})).status_code == 401
    r = await client.post("/api/session", json={"role": "admin", "code": "open sesame"})
    assert r.status_code == 200 and r.json()["token"]
    tok = {"Authorization": "Bearer " + r.json()["token"]}
    assert (await client.get("/api/state", headers=tok)).status_code == 200
    assert (await client.post("/api/gates", json={"name": "Token gate"}, headers=tok)).status_code == 200
    bad = {"Authorization": "Bearer " + r.json()["token"][:-2] + "xx"}
    assert (await client.get("/api/state", headers=bad)).status_code == 403          # tampered
    # a guard token cannot do admin things
    g = (await client.post("/api/session", json={"role": "guard", "code": "open sesame"})).json()
    assert (await client.post("/api/gates", json={"name": "No"}, headers={"Authorization": "Bearer " + g["token"]})).status_code == 403
    # household token follows the household, not the typed lot
    h = (await client.post("/api/session", json={"role": "household", "household_lot": "B1-L4", "code": "open sesame"})).json()
    hs = (await client.get("/api/state", headers={"Authorization": "Bearer " + h["token"]})).json()
    assert len(hs["households"]) == 1 and hs["households"][0]["lot"] == "B1-L4"
    assert (await client.post("/api/session", json={"role": "household", "household_lot": "B3-L2", "code": "open sesame"})).status_code == 200  # awaiting is fine, invited is not
    assert (await client.post("/api/session", json={"role": "household", "household_lot": "NOPE", "code": "open sesame"})).status_code == 422
    # household list for the sign-in screen needs the code
    assert (await client.get("/api/dev/households")).status_code == 403
    ok = await client.get("/api/dev/households", headers={"X-Access-Code": "open sesame"})
    assert ok.status_code == 200 and any(x["lot"] == "B1-L4" for x in ok.json())
    # expired token
    monkeypatch.setattr(config, "SESSION_HOURS", -1)
    old = (await client.post("/api/session", json={"role": "admin", "code": "open sesame"})).json()["token"]
    assert (await client.get("/api/state", headers={"Authorization": "Bearer " + old})).status_code == 403
    # public endpoints still work without any code
    assert (await client.post("/api/visits", json=public_visit(name="Pub", phone="0900 555 0100"))).status_code == 200


async def test_cron_endpoint(client, monkeypatch):
    monkeypatch.setattr(config, "CRON_KEY", "")
    assert (await client.post("/api/cron/missing?key=")).status_code == 403   # disabled when no key is configured
    monkeypatch.setattr(config, "CRON_KEY", "cronkey")
    assert (await client.post("/api/cron/missing?key=nope")).status_code == 403
    r = await client.post("/api/cron/missing?key=cronkey")
    assert r.status_code == 200 and "flagged" in r.json()


async def test_bootstrap_clean_property(app_pool):
    from app.seed import bootstrap
    assert await bootstrap(app_pool, "Clean Village", "clean-village-0000", passes=5) is True
    assert await bootstrap(app_pool, "Clean Village", "clean-village-0000") is False
    async with app_pool.acquire() as c:
        pid = await c.fetchval("SELECT id FROM properties WHERE slug='clean-village-0000'")
        assert await c.fetchval("SELECT count(*) FROM badges WHERE property_id=$1", pid) == 5
        assert await c.fetchval("SELECT count(*) FROM visits WHERE property_id=$1", pid) == 0


async def test_cors_allows_the_react_app_only(client):
    ask = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
           "Access-Control-Request-Headers": "authorization,content-type,x-role"}
    r = await client.options("/api/visits", headers=ask)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r = await client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers


async def test_root_is_api_only(client):
    r = await client.get("/")
    assert r.status_code == 200 and r.json()["service"] == "Vista VMS API"


async def test_invited_household_can_sign_in_and_finish_the_flow(client, code_mode, monkeypatch):
    """Published mode on a new village: invite -> household opens its link -> fills the form -> HOA verifies -> a visit is approved."""
    monkeypatch.setattr(config, "FRONTEND_URL", "https://vista.example")
    code = {"code": "open sesame"}
    adm = (await client.post("/api/session", json={"role": "admin", **code})).json()["token"]
    A = {"Authorization": "Bearer " + adm}
    inv = await client.post("/api/households/invite", json={"email": "newfamily@example.com"}, headers=A)
    assert inv.status_code == 200 and inv.json()["link"].startswith("https://vista.example/greenfield-village-7f3a?invite=")
    token = inv.json()["link"].split("?invite=")[1]

    assert (await client.post("/api/session", json={"role": "household", "invite": "garbage"})).status_code == 401
    r = await client.post("/api/session", json={"role": "household", "invite": token})   # no staff code needed
    assert r.status_code == 200 and r.json()["household_lot"] is None
    HH = {"Authorization": "Bearer " + r.json()["token"]}

    form = {"owner": "Dela Torre", "lot": "b7-l1", "holder": "Ana Dela Torre", "email": "newfamily@example.com", "phone": "0917 555 0199",
            "members": [{"n": "Ana Dela Torre", "minor": False}, {"n": "Leo", "minor": True}]}
    assert (await client.put("/api/me/household", json=form, headers=HH)).status_code == 200
    hid = next(h["id"] for h in (await client.get("/api/state", headers=A)).json()["households"] if h["lot"] == "B7-L1")

    hoa = {"Authorization": "Bearer " + (await client.post("/api/session", json={"role": "hoa", **code})).json()["token"]}
    assert (await client.post(f"/api/households/{hid}/verify", headers=hoa)).status_code == 200

    v = await client.post("/api/visits", json=public_visit(name="Visitor X", phone="0955 000 0001", house="B7-L1"))
    assert v.status_code == 200
    ref = next(x["ref"] for x in (await client.get("/api/state", headers=HH)).json()["visits"] if x["visitor"].startswith("Visitor X"))
    d = await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=HH)
    assert d.status_code == 200

    # a link for another village or a tampered link is refused; the Admin can issue a fresh link any time
    assert (await client.post("/api/session", json={"role": "household", "invite": token[:-2] + "xx"})).status_code == 401
    L = await client.post(f"/api/households/{hid}/link", headers=A)
    assert L.status_code == 200 and "?invite=" in L.json()["link"]
    assert (await client.post(f"/api/households/{hid}/link", headers=HH)).status_code == 403   # households cannot mint links


async def test_invite_links_need_published_mode(client):
    r = await client.post("/api/session", json={"role": "household", "invite": "x"})
    assert r.status_code == 400


async def test_household_approves_from_the_email_link(client, code_mode, app_pool):
    """The email carries a signed link; the confirmation page needs no sign-in and only ever opens its own request."""
    from app.core import approval_link
    base = public_visit(phone="0900 000 0401", purpose="Dinner", friends=["Pal"])
    assert (await client.post("/api/visits", json={**base, "name": "Link Visitor", "email": "not-an-email"})).status_code == 422
    assert (await client.post("/api/visits", json={**base, "name": "Link Visitor", "email": "v@mail.ph"})).status_code == 200
    assert (await client.post("/api/visits", json={**base, "name": "Link Second", "phone": "0900 000 0402"})).status_code == 200

    async def ids(name):
        r = await app_pool.fetchrow("SELECT v.id, d.household_id, d.email FROM visits v JOIN village_visit_details d ON d.visit_id=v.id WHERE d.visitor_name=$1", name)
        return r
    one, two = await ids("Link Visitor"), await ids("Link Second")
    assert one["email"] == "v@mail.ph"
    tok = lambda r: approval_link("greenfield-village-7f3a", r["id"], r["household_id"]).split("?approve=")[1]   # noqa: E731

    info = await client.get(f"/api/approval/{tok(one)}")   # no sign-in at all
    assert info.status_code == 200
    j = info.json()
    assert j["visitor"] == "Link Visitor" and j["people"] == ["Link Visitor", "Pal"] and j["can_decide"] is True
    assert "restricted" not in str(j).lower()
    assert (await client.get(f"/api/approval/{tok(one)[:-2]}xx")).status_code == 401                       # tampered
    assert (await client.get(f"/api/approval/{tok(one)}", headers={"X-Property": "other-village-1a2b"})).status_code == 401   # another village
    assert (await client.post(f"/api/approval/{tok(one)}", json={"action": "maybe"})).status_code == 422

    assert (await client.post(f"/api/approval/{tok(one)}", json={"action": "approve"})).json() == {"status": "approved"}
    assert await app_pool.fetchval("SELECT status FROM visits WHERE id=$1", one["id"]) == "approved"
    assert (await client.post(f"/api/approval/{tok(one)}", json={"action": "decline"})).status_code == 409   # already answered
    assert (await client.get(f"/api/approval/{tok(one)}")).json()["can_decide"] is False
    assert await app_pool.fetchval("SELECT count(*) FROM audit_log WHERE action LIKE '%(email link)%'") >= 1
    assert await app_pool.fetchval("SELECT count(*) FROM notifications WHERE subject LIKE 'Your visit QR code%'") >= 1

    # "Not for me" from the page sends it to the HOA queue and the link stops working for this household
    assert (await client.post(f"/api/approval/{tok(two)}", json={"action": "not_for_me"})).json() == {"status": "queue"}
    assert await app_pool.fetchval("SELECT status FROM visits WHERE id=$1", two["id"]) == "queue"
    assert (await client.get(f"/api/approval/{tok(two)}")).status_code == 410


async def test_unverified_household_cannot_approve_from_the_link(client, code_mode, app_pool):
    from app.core import approval_link
    await client.post("/api/visits", json=public_visit(name="Unver Link", phone="0900 000 0403", house="B3-L2", purpose="x"))
    r = await app_pool.fetchrow("SELECT v.id, d.household_id FROM visits v JOIN village_visit_details d ON d.visit_id=v.id WHERE d.visitor_name='Unver Link'")
    t = approval_link("greenfield-village-7f3a", r["id"], r["household_id"]).split("?approve=")[1]
    assert (await client.get(f"/api/approval/{t}")).json()["can_decide"] is False
    assert (await client.post(f"/api/approval/{t}", json={"action": "approve"})).status_code == 403


@pytest.fixture
def super_mode(code_mode, monkeypatch):
    monkeypatch.setattr(config, "SUPER_ADMIN_CODE", "platform owner")
    monkeypatch.setattr(config, "FRONTEND_URL", "https://vista.example")


async def super_headers(client, name="Sol Super"):
    r = await client.post("/api/platform/session", json={"code": "platform owner", "name": name})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


async def test_super_admin_sign_in_is_separate_from_the_village_code(client, super_mode):
    assert (await client.post("/api/platform/session", json={"code": "open sesame"})).status_code == 401      # the village staff code is not enough
    assert (await client.post("/api/platform/session", json={"code": "wrong"})).status_code == 401
    assert (await client.get("/api/platform/overview")).status_code == 403
    adm = (await client.post("/api/session", json={"role": "admin", "code": "open sesame"})).json()["token"]
    assert (await client.get("/api/platform/overview", headers={"Authorization": "Bearer " + adm})).status_code == 403   # a village Admin is not a Super Admin
    S = await super_headers(client)
    assert (await client.get("/api/state", headers=S)).status_code == 403    # and a Super Admin token is not a village token
    assert (await client.get("/api/platform/overview", headers=S)).status_code == 200


async def test_super_admin_not_set_up(client, code_mode, monkeypatch):
    monkeypatch.setattr(config, "SUPER_ADMIN_CODE", "")
    assert (await client.post("/api/platform/session", json={"code": ""})).status_code == 501


async def test_super_admin_creates_a_property_and_connects_the_admin(client, super_mode, app_pool):
    S = await super_headers(client)
    bad = await client.post("/api/platform/properties", json={"name": "Palm Grove Village", "type": "castle", "admin_name": "Pat", "admin_email": "pat@palm.ph"}, headers=S)
    assert bad.status_code == 422
    r = await client.post("/api/platform/properties", json={"name": "Palm Grove Village", "type": "village", "admin_name": "Pat Palm", "admin_email": "Pat@Palm.ph"}, headers=S)
    assert r.status_code == 200, r.text
    j = r.json()
    import re
    assert re.fullmatch(r"palm-grove-village-[0-9a-f]{4}", j["slug"]) and j["village_link"] == f"https://vista.example/{j['slug']}"
    assert j["admin_link"].startswith("https://vista.example/?admin=")
    # one Admin, one gate, a pass inventory, nothing else
    assert await app_pool.fetchval("SELECT count(*) FROM users u JOIN properties p ON p.id=u.property_id WHERE p.slug=$1 AND u.role='admin'", j["slug"]) == 1
    assert await app_pool.fetchval("SELECT count(*) FROM gates g JOIN properties p ON p.id=g.property_id WHERE p.slug=$1", j["slug"]) == 1

    # the village page is live, and the Admin signs in with the link that was sent
    assert (await client.get(f"/api/property/{j['slug']}")).status_code == 200
    adm_tok = j["admin_link"].split("?admin=")[1]
    s = await client.post("/api/session", json={"role": "admin", "admin_link": adm_tok})
    assert s.status_code == 200 and s.json()["name"] == "Pat Palm" and s.json()["property"]["slug"] == j["slug"]
    A = {"Authorization": "Bearer " + s.json()["token"]}
    st = (await client.get("/api/state", headers=A)).json()
    assert st["prop"]["slug"] == j["slug"] and st["households"] == [] and len(st["gates"]) == 1
    assert (await client.post("/api/session", json={"role": "admin", "admin_link": adm_tok[:-2] + "xx"})).status_code == 401
    assert any("Signed in with the Admin link" in a["action"] and a["role"] == "Admin" for a in st["audit"])
    assert any("Property created" in a["action"] and a["role"] == "Super Admin" for a in st["audit"])

    # reassigning replaces the one Admin; the old link stops working
    r2 = await client.put(f"/api/platform/properties/{j['id']}/admin", json={"name": "Quin Palm", "email": "quin@palm.ph"}, headers=S)
    assert r2.status_code == 200
    assert (await client.post("/api/session", json={"role": "admin", "admin_link": adm_tok})).status_code == 401
    assert await app_pool.fetchval("SELECT count(*) FROM users u JOIN properties p ON p.id=u.property_id WHERE p.slug=$1 AND u.role='admin'", j["slug"]) == 1
    new_tok = r2.json()["admin_link"].split("?admin=")[1]
    assert (await client.post("/api/session", json={"role": "admin", "admin_link": new_tok})).status_code == 200
    fresh = await client.post(f"/api/platform/properties/{j['id']}/admin-link", headers=S)
    assert fresh.status_code == 200 and fresh.json()["admin_link"].startswith("https://vista.example/?admin=")

    # overview and platform audit
    ov = (await client.get("/api/platform/overview", headers=S)).json()
    mine = next(p for p in ov["properties"] if p["slug"] == j["slug"])
    assert mine["admin"] == "Quin Palm" and mine["households"] == 0 and mine["active"] is True and ov["totals"]["properties"] >= 3
    assert any("Created Palm Grove Village" in a["action"] for a in ov["audit"])


async def test_super_admin_enters_a_property_and_it_is_audited(client, super_mode, app_pool):
    S = await super_headers(client, "Sol Super")
    ov = (await client.get("/api/platform/overview", headers=S)).json()
    p = next(x for x in ov["properties"] if x["slug"] == "greenfield-village-7f3a")
    e = await client.post(f"/api/platform/properties/{p['id']}/enter", headers=S)
    assert e.status_code == 200 and e.json()["role"] == "admin" and e.json()["property"]["slug"] == "greenfield-village-7f3a"
    A = {"Authorization": "Bearer " + e.json()["token"]}
    st = (await client.get("/api/state", headers=A)).json()
    assert st["me"]["role"] == "admin" and any(h["lot"] == "B1-L4" for h in st["households"])
    assert any(a["role"] == "Super Admin" and a["actor"] == "Sol Super" and "signed in to this property" in a["action"] for a in st["audit"])
    # whatever the Super Admin does inside is also logged as Super Admin
    assert (await client.post("/api/gates", json={"name": "Super gate"}, headers=A)).status_code == 200
    st = (await client.get("/api/state", headers=A)).json()
    assert any(a["role"] == "Super Admin" and "Gate added" in a["action"] for a in st["audit"])
    # the token only works in its own village
    assert (await client.get("/api/state", headers={**A, "X-Property": "other-village-1a2b"})).json()["prop"]["slug"] == "greenfield-village-7f3a"
    assert any("Signed in to the property" in a["action"] for a in (await client.get("/api/platform/overview", headers=S)).json()["audit"])


async def test_switched_off_village_is_closed_to_everyone_but_the_super_admin(client, super_mode, app_pool):
    S = await super_headers(client)
    j = (await client.post("/api/platform/properties", json={"name": "Quiet Hills", "admin_name": "Qu", "admin_email": "qu@hills.ph"}, headers=S)).json()
    pid = await app_pool.fetchval("SELECT id FROM properties WHERE slug=$1", j["slug"])
    hdr = {"X-Property": j["slug"]}
    assert (await client.get(f"/api/property/{j['slug']}")).status_code == 200
    assert (await client.patch(f"/api/platform/properties/{pid}", json={"active": False}, headers=S)).status_code == 200
    assert (await client.get(f"/api/property/{j['slug']}")).status_code == 404                               # the village page says "not valid"
    assert (await client.post("/api/visits", json={"name": "V", "phone": "0900", "house": "B1-L1"}, headers=hdr)).status_code == 403
    adm = await client.post("/api/session", json={"role": "admin", "admin_link": j["admin_link"].split("?admin=")[1]})
    assert adm.status_code == 403
    e = await client.post(f"/api/platform/properties/{pid}/enter", headers=S)   # the Super Admin can still get in
    assert (await client.get("/api/state", headers={"Authorization": "Bearer " + e.json()["token"]})).status_code == 200
    assert (await client.patch(f"/api/platform/properties/{pid}", json={"active": True, "name": "Quiet Hills Village"}, headers=S)).status_code == 200
    assert (await client.get(f"/api/property/{j['slug']}")).status_code == 200


async def test_only_one_admin_per_property(app_pool):
    import asyncpg
    async with app_pool.acquire() as c:
        pid = await c.fetchval("SELECT id FROM properties WHERE slug='other-village-1a2b'")
        with pytest.raises(asyncpg.UniqueViolationError):
            await c.execute("INSERT INTO users (property_id, email, name, role) VALUES ($1,'second@admin.ph','Second','admin')", pid)


async def test_admin_link_works_even_if_the_default_village_is_off(client, super_mode, app_pool):
    """The Admin link names its own village. The sign-in must not depend on whichever village is the server's default."""
    S = await super_headers(client)
    j = (await client.post("/api/platform/properties", json={"name": "Link Hills", "admin_name": "Lin", "admin_email": "lin@hills.ph"}, headers=S)).json()
    tok = j["admin_link"].split("?admin=")[1]
    await app_pool.execute("UPDATE properties SET active=false WHERE slug=$1", config.DEFAULT_PROPERTY)
    try:
        r = await client.post("/api/session", json={"role": "admin", "admin_link": tok})
        assert r.status_code == 200, r.text
        assert r.json()["property"]["slug"] == j["slug"]
    finally:
        await app_pool.execute("UPDATE properties SET active=true WHERE slug=$1", config.DEFAULT_PROPERTY)


async def test_login_limit_cannot_be_dodged_with_a_made_up_forwarded_header(client, code_mode, monkeypatch):
    monkeypatch.setattr(config, "LOGIN_RATE_LIMIT_PER_MIN", 5)
    codes = []
    for i in range(8):   # the proxy appends the real address last; the client controls everything before it
        r = await client.post("/api/session", json={"role": "admin", "code": f"guess{i}"}, headers={"X-Forwarded-For": f"10.9.9.{i}, 203.0.113.7"})
        codes.append(r.status_code)
    assert codes[:5] == [401] * 5 and codes[5:] == [429] * 3
    other = await client.post("/api/session", json={"role": "admin", "code": "x"}, headers={"X-Forwarded-For": "198.51.100.2"})
    assert other.status_code == 401   # a different real address has its own allowance


def test_startup_refuses_unsafe_sign_in_setups(monkeypatch):
    from app.main import check_config
    for k, v in {"STAFF_ACCESS_CODE": "", "SECRET_KEY": "", "SUPER_ADMIN_CODE": "", "ON_RENDER": False, "ALLOW_DEMO_AUTH": False}.items():
        monkeypatch.setattr(config, k, v)
    check_config()                                                  # demo mode on a laptop is allowed (with a warning)
    monkeypatch.setattr(config, "SUPER_ADMIN_CODE", "owner-code")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):           # a platform code that cannot sign tokens
        check_config()
    monkeypatch.setattr(config, "SECRET_KEY", "x" * 32)
    monkeypatch.setattr(config, "STAFF_ACCESS_CODE", "owner-code")
    with pytest.raises(RuntimeError, match="different"):            # the staff code must never open the platform
        check_config()
    monkeypatch.setattr(config, "STAFF_ACCESS_CODE", "staff-code")
    check_config()
    monkeypatch.setattr(config, "STAFF_ACCESS_CODE", "")
    monkeypatch.setattr(config, "ON_RENDER", True)
    with pytest.raises(RuntimeError, match="STAFF_ACCESS_CODE"):    # published without a code
        check_config()


async def test_personal_accounts_sign_in_and_are_cut_off_at_once(client, super_mode, app_pool):
    S = await super_headers(client)
    j = (await client.post("/api/platform/properties", json={"name": "Acct Hills", "admin_name": "Ada", "admin_email": "ada@acct.ph"}, headers=S)).json()
    P = {"X-Property": j["slug"]}
    ses = await client.post("/api/session", json={"role": "admin", "admin_link": j["admin_link"].split("?admin=")[1]})
    A = {"Authorization": "Bearer " + ses.json()["token"]}
    assert (await client.put("/api/me/password", json={"new": "short"}, headers=A)).status_code == 422
    first = await client.put("/api/me/password", json={"new": "ada-long-password"}, headers=A)                         # first password: no current one needed
    assert first.status_code == 200
    assert (await client.get("/api/state", headers=A)).status_code == 401                                              # the token from before the change is spent ...
    A = {"Authorization": "Bearer " + first.json()["token"]}                                                           # ... the reply carries the one to keep using
    assert (await client.put("/api/me/password", json={"current": "nope", "new": "another-long-one"}, headers=A)).status_code == 403
    # the Admin creates a guard with a password; the guard signs in as themselves
    assert (await client.post("/api/staff", json={"name": "Gil", "email": "gil@acct.ph", "role": "Guard", "password": "gil-long-password"}, headers={**A, **P})).status_code == 200
    bad = await client.post("/api/session", json={"email": "gil@acct.ph", "password": "wrong"}, headers=P)
    nobody = await client.post("/api/session", json={"email": "who@acct.ph", "password": "wrong"}, headers=P)
    assert bad.status_code == nobody.status_code == 401 and bad.json() == nobody.json()   # same answer: emails are not revealed
    ok = await client.post("/api/session", json={"email": "GIL@acct.ph", "password": "gil-long-password"}, headers=P)
    assert ok.status_code == 200 and ok.json()["role"] == "guard"
    G = {"Authorization": "Bearer " + ok.json()["token"]}
    assert (await client.get("/api/state", headers=G)).status_code == 200
    assert (await client.get("/api/settings", headers=G)).status_code == 403                  # guard is not an Admin
    # the Admin switches Gil off: the token he already holds stops working immediately
    gid = next(x["id"] for x in (await client.get("/api/state", headers=A)).json()["staff"] if x["email"] == "gil@acct.ph")
    assert (await client.patch(f"/api/staff/{gid}", json={"active": False}, headers=A)).status_code == 200
    assert (await client.get("/api/state", headers=G)).status_code == 401
    assert (await client.post("/api/session", json={"email": "gil@acct.ph", "password": "gil-long-password"}, headers=P)).status_code == 401


async def test_shared_staff_code_can_be_switched_off(client, code_mode, monkeypatch):
    assert (await client.post("/api/session", json={"role": "guard", "code": "open sesame"})).status_code == 200
    monkeypatch.setattr(config, "STAFF_CODE_LOGIN", False)
    assert (await client.post("/api/session", json={"role": "guard", "code": "open sesame"})).status_code == 403
    assert (await client.get("/api/config")).json()["code_required"] is False


async def test_account_guessing_is_slowed_per_account(client, code_mode):
    codes = [(await client.post("/api/session", json={"email": "x@y.ph", "password": f"g{i}"}, headers={"X-Forwarded-For": f"1.1.1.{i}"})).status_code
             for i in range(12)]
    assert codes[:10] == [401] * 10 and 429 in codes[10:]   # even from changing addresses, the account's guesses run out


async def test_guard_and_hoa_accounts_sign_in_as_themselves_and_get_only_their_role(client, code_mode, app_pool):
    """Each person signs in with their own email and password. The role comes from the account, never from the request."""
    adm = {"Authorization": "Bearer " + (await client.post("/api/session", json={"role": "admin", "code": "open sesame"})).json()["token"]}
    pw_g, pw_h = "guard-long-password", "hoa-long-password"
    assert (await client.post("/api/staff", json={"name": "Gus Guard", "email": "gus.guard@role.ph", "role": "Guard", "password": pw_g}, headers=adm)).status_code == 200
    assert (await client.post("/api/staff", json={"name": "Hana HOA", "email": "hana.hoa@role.ph", "role": "HOA office", "password": pw_h}, headers=adm)).status_code == 200
    assert (await client.post("/api/staff", json={"name": "No Pass", "email": "nopass@role.ph", "role": "Guard"}, headers=adm)).status_code == 200   # no password yet

    g = await client.post("/api/session", json={"email": "gus.guard@role.ph", "password": pw_g})
    h = await client.post("/api/session", json={"email": "HANA.HOA@role.ph", "password": pw_h})
    assert g.status_code == h.status_code == 200
    assert (g.json()["role"], g.json()["name"]) == ("guard", "Gus Guard") and (h.json()["role"], h.json()["name"]) == ("hoa", "Hana HOA")
    assert g.json()["token"] and h.json()["token"] and g.json()["property"]["slug"] == "greenfield-village-7f3a"

    # whatever role the request claims, the account's own role is what comes back
    for claim in ("admin", "hoa", "household"):
        r = await client.post("/api/session", json={"email": "gus.guard@role.ph", "password": pw_g, "role": claim, "household_lot": "B1-L4"})
        assert r.status_code == 200 and r.json()["role"] == "guard" and r.json()["household_lot"] is None, claim
    r = await client.post("/api/session", json={"email": "hana.hoa@role.ph", "password": pw_h, "role": "admin", "code": "open sesame"})
    assert r.status_code == 200 and r.json()["role"] == "hoa"

    G, Hh = ({"Authorization": "Bearer " + x.json()["token"]} for x in (g, h))
    # the guard's token does the guard's work and nothing of the HOA's or the Admin's
    assert (await client.get("/api/state", headers=G)).status_code == 200
    assert (await client.get("/api/settings", headers=G)).status_code == 403
    assert (await client.post("/api/staff", json={"name": "X", "email": "x@role.ph", "role": "Guard"}, headers=G)).status_code == 403
    assert (await client.post("/api/households/00000000-0000-0000-0000-000000000000/verify", headers=G)).status_code == 403
    assert (await client.post("/api/walkins", json={"visitor": "Gate Guest", "house": "B1-L4"}, headers=G)).status_code == 200
    # the HOA token does the office's work and nothing of the guard's or the Admin's
    assert (await client.get("/api/state", headers=Hh)).status_code == 200
    assert (await client.get("/api/settings", headers=Hh)).status_code == 403
    assert (await client.post("/api/walkins", json={"visitor": "Office Guest", "house": "B1-L4"}, headers=Hh)).status_code == 403
    assert (await client.post("/api/visits/scan", json={"code": "VS-0001"}, headers=Hh)).status_code == 403
    assert (await client.post("/api/households/00000000-0000-0000-0000-000000000000/verify", headers=Hh)).status_code != 403
    assert (await client.get("/api/state", headers=Hh)).json()["visits"] is not None

    # wrong password, someone else's password, no password, no such email, an empty password: all the same plain refusal
    refusals = [await client.post("/api/session", json=b) for b in (
        {"email": "gus.guard@role.ph", "password": "wrong-password"}, {"email": "gus.guard@role.ph", "password": pw_h},
        {"email": "nopass@role.ph", "password": ""}, {"email": "nopass@role.ph", "password": "anything-at-all"},
        {"email": "nobody@role.ph", "password": pw_g}, {"email": "gus.guard@role.ph"})]
    assert all(r.status_code == 401 and r.json() == {"detail": "Wrong email or password"} for r in refusals)
    # another village does not know these accounts
    assert (await client.post("/api/session", json={"email": "gus.guard@role.ph", "password": pw_g}, headers={"X-Property": "other-village-1a2b"})).status_code == 401
    # the Admin switches the HOA account off: its token and its password both stop at once
    hid = next(x["id"] for x in (await client.get("/api/state", headers=adm)).json()["staff"] if x["email"] == "hana.hoa@role.ph")
    assert (await client.patch(f"/api/staff/{hid}", json={"active": False}, headers=adm)).status_code == 200
    assert (await client.get("/api/state", headers=Hh)).status_code == 401
    assert (await client.post("/api/session", json={"email": "hana.hoa@role.ph", "password": pw_h})).status_code == 401


async def test_personal_accounts_still_sign_in_when_the_shared_code_is_switched_off(client, code_mode, monkeypatch):
    adm = {"Authorization": "Bearer " + (await client.post("/api/session", json={"role": "admin", "code": "open sesame"})).json()["token"]}
    assert (await client.post("/api/staff", json={"name": "Off Code", "email": "offcode@role.ph", "role": "HOA office", "password": "offcode-password"}, headers=adm)).status_code == 200
    monkeypatch.setattr(config, "STAFF_CODE_LOGIN", False)
    cfg = (await client.get("/api/config")).json()
    assert cfg["code_required"] is False and cfg["accounts"] is True
    assert (await client.post("/api/session", json={"role": "hoa", "code": "open sesame"})).status_code == 403
    r = await client.post("/api/session", json={"email": "offcode@role.ph", "password": "offcode-password"})
    assert r.status_code == 200 and r.json()["role"] == "hoa"


# ---- hardening: password hashing off the event loop, request size limit, free-text length limits
async def test_passwords_are_hashed_and_checked_off_the_event_loop(client, code_mode, monkeypatch):
    """scrypt is slow CPU work. On the event loop it would hold up every other request (the gate included) while one person signs in."""
    import threading
    from app import core
    seen = []
    real_check, real_hash = core.check_password, core.hash_password
    monkeypatch.setattr(core, "check_password", lambda *a: (seen.append(("check", threading.current_thread() is threading.main_thread())), real_check(*a))[1])
    monkeypatch.setattr(core, "hash_password", lambda *a: (seen.append(("hash", threading.current_thread() is threading.main_thread())), real_hash(*a))[1])
    adm = {"Authorization": "Bearer " + (await client.post("/api/session", json={"role": "admin", "code": "open sesame"})).json()["token"]}
    assert (await client.post("/api/staff", json={"name": "Thread Test", "email": "thread@role.ph", "role": "Guard", "password": "thread-long-password"}, headers=adm)).status_code == 200
    assert (await client.post("/api/session", json={"email": "thread@role.ph", "password": "thread-long-password"})).status_code == 200
    assert (await client.post("/api/session", json={"email": "nobody@role.ph", "password": "whatever-password"})).status_code == 401   # the unknown-account path does the same work
    kinds = [k for k, _ in seen]
    assert kinds.count("hash") >= 1 and kinds.count("check") >= 2
    assert all(on_main is False for _, on_main in seen), seen


async def test_a_request_body_over_the_limit_is_refused_before_it_is_read(client, monkeypatch):
    from tests.conftest import JPEG_B64
    big_photo = base64_jpeg(1_400_000)                       # just under the 1.5 MB photo limit: must still go through
    ok = await client.post("/api/visits", json=public_visit(name="Big Photo", phone="0917 555 0001", id_photo=big_photo))
    assert ok.status_code == 200, ok.text[:200]
    too_big = await client.post("/api/visits", json=public_visit(name="Huge", purpose="x" * 3_500_000))
    assert too_big.status_code == 413 and "too large" in too_big.json()["detail"]
    # a sender that does not declare a length (chunked) is stopped too, while it is still sending
    async def chunks():
        for _ in range(8):
            yield b"x" * 500_000
    streamed = await client.post("/api/visits", content=chunks(), headers={"Content-Type": "application/json"})
    assert streamed.status_code == 413 and "too large" in streamed.json()["detail"]
    # the cap is configurable
    monkeypatch.setattr(config, "MAX_BODY_BYTES", 2_000)
    small = await client.post("/api/visits", json=public_visit(name="Small Cap", purpose="x" * 3_000))
    assert small.status_code == 413
    assert (await client.get("/api/health")).status_code == 200


async def test_the_map_import_has_its_own_larger_limit(client, code_mode):
    import base64
    adm = {"Authorization": "Bearer " + (await client.post("/api/session", json={"role": "admin", "code": "open sesame"})).json()["token"]}
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 5_000_000            # 5 MB: over the normal body limit, inside the 8 MB map limit
    r = await client.put("/api/map", json={"data": base64.b64encode(png).decode()}, headers=adm)
    assert r.status_code == 200, r.text[:200]
    over = b"\x89PNG\r\n\x1a\n" + b"\0" * 8_500_000          # 8.5 MB: through the body limit, then the map's own size message
    r = await client.put("/api/map", json={"data": base64.b64encode(over).decode()}, headers=adm)
    assert r.status_code == 413 and "8 MB" in r.json()["detail"]


async def test_free_text_fields_have_plain_length_limits(client):
    for field, n, word in (("host", 121, "person visited"), ("kind", 61, "vehicle type"), ("color", 41, "vehicle color"), ("plate", 21, "plate number")):
        r = await client.post("/api/visits", json=public_visit(**{field: "x" * n}))
        assert r.status_code == 422 and word in r.json()["detail"] and "too long" in r.json()["detail"], (field, r.text)
        r = await client.post("/api/visits", json=public_visit(**{field: "x" * (n - 1)}))
        assert r.status_code == 200, (field, r.text)


def base64_jpeg(n: int) -> str:
    import base64
    return base64.b64encode(b"\xff\xd8\xff" + b"\0" * n).decode()
