"""When a household approves a visit, the QR code is emailed to the visitor (if they gave an email) AND to the household."""
import asyncio

from app import mailer
from tests.conftest import H, public_visit


async def _sent(monkeypatch):
    sent = []

    async def fake(to, subject, text, qr_code=None):
        sent.append({"to": to, "subject": subject, "text": text, "qr": qr_code})
    monkeypatch.setattr(mailer, "send_email", fake)
    monkeypatch.setattr(mailer, "email_ready", lambda: True)
    return sent


async def _flush():
    await asyncio.sleep(0.05)   # the email is sent by a background task


async def test_approval_emails_visitor_and_household(client, monkeypatch):
    sent = await _sent(monkeypatch)
    r = await client.post("/api/visits", json=public_visit(name="Qr Mailer", phone="0917 000 7771", email="visitor@mail.ph"))
    assert r.status_code == 200
    st = (await client.get("/api/state", headers=H("household", "B1-L4"))).json()
    ref = next(v["ref"] for v in st["visits"] if v["visitor"] == "Qr Mailer")
    assert (await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))).status_code == 200
    await _flush()
    to = {m["to"]: m for m in sent if m["qr"]}   # the approval-link email sent when the request came in has no QR
    assert "visitor@mail.ph" in to, "the visitor must get the QR code"
    assert len(to) == 2, "the household's account holder must get a copy too"
    hh = next(a for a in to if a != "visitor@mail.ph")
    for m in to.values():
        assert m["qr"] and m["qr"].startswith("VISTA:") and m["qr"] in m["text"]
    assert to[hh]["qr"] == to["visitor@mail.ph"]["qr"]


async def test_household_gets_qr_even_if_visitor_gave_no_email(client, monkeypatch):
    sent = await _sent(monkeypatch)
    await client.post("/api/visits", json=public_visit(name="No Mail Visitor", phone="0917 000 7772"))
    st = (await client.get("/api/state", headers=H("household", "B1-L4"))).json()
    ref = next(v["ref"] for v in st["visits"] if v["visitor"] == "No Mail Visitor")
    await client.post(f"/api/visits/{ref}/decision", json={"approve": True}, headers=H("household", "B1-L4"))
    await _flush()
    qr = [m for m in sent if m["qr"]]
    assert len(qr) == 1 and qr[0]["to"] == "maria@mail.ph"


async def test_decline_sends_no_qr(client, monkeypatch):
    sent = await _sent(monkeypatch)
    await client.post("/api/visits", json=public_visit(name="Declined One", phone="0917 000 7773", email="d@mail.ph"))
    st = (await client.get("/api/state", headers=H("household", "B1-L4"))).json()
    ref = next(v["ref"] for v in st["visits"] if v["visitor"] == "Declined One")
    await client.post(f"/api/visits/{ref}/decision", json={"approve": False}, headers=H("household", "B1-L4"))
    await _flush()
    assert not [m for m in sent if m["qr"]]


async def test_qr_picture_only_for_approved_visits(client):
    assert (await client.get("/api/qr/not-a-real-token.png")).status_code == 404


async def test_emailjs_payload(monkeypatch):
    """Hosting path: the email goes to EmailJS over HTTPS; the template gets the QR text and a link to the QR picture."""
    import json, httpx
    from app import config
    for k, v in (("EMAILJS_SERVICE_ID", "svc"), ("EMAILJS_TEMPLATE_ID", "tpl"), ("EMAILJS_PUBLIC_KEY", "pub"), ("EMAILJS_PRIVATE_KEY", "priv"),
                 ("PUBLIC_API_URL", "https://api.example.com"), ("SMTP_HOST", "smtp.example.com"), ("SMTP_USER", "x@example.com")):
        monkeypatch.setattr(config, k, v)
    assert mailer.emailjs_ready() and mailer.email_ready()
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url); seen["body"] = json.loads(req.content)
        return httpx.Response(200, text="OK")
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    await mailer.send_email_strict("v@mail.ph", "Your QR", "Hello", "VISTA:tok123")   # EmailJS wins even when SMTP is also set
    b = seen["body"]; p = b["template_params"]
    assert seen["url"] == "https://api.emailjs.com/api/v1.0/email/send"
    assert b["service_id"] == "svc" and b["template_id"] == "tpl" and b["user_id"] == "pub" and b["accessToken"] == "priv"
    assert p["to_email"] == "v@mail.ph" and p["subject"] == "Your QR" and p["qr_code"] == "VISTA:tok123"
    assert p["qr_url"] == "https://api.example.com/api/qr/tok123.png"


async def test_emailjs_refusal_is_reported(monkeypatch):
    import httpx
    from app import config
    for k, v in (("EMAILJS_SERVICE_ID", "svc"), ("EMAILJS_TEMPLATE_ID", "tpl"), ("EMAILJS_PUBLIC_KEY", "pub")):
        monkeypatch.setattr(config, k, v)
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(403, text="forbidden")), **kw))
    try:
        await mailer.send_email_strict("v@mail.ph", "s", "t")
        assert False, "a refused email must raise"
    except RuntimeError as x:
        assert "403" in str(x)
    await mailer.send_email("v@mail.ph", "s", "t")   # the non-strict version only logs: a mail problem never undoes an approval
