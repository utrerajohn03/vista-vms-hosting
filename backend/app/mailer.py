"""Sending email. Two ways, tried in this order:

1. EmailJS (the platform's email tool, see the Village brief): set EMAILJS_*. It goes over HTTPS, so it works on Render's free plan.
   Template variables: {{to_email}}, {{subject}}, {{message}}, and for a QR email also {{qr_code}} (the text VISTA:...)
   and {{qr_url}} (a PNG picture of the code; PUBLIC_API_URL is filled in by Render itself).
2. SMTP (Gmail, Outlook, your own server ...): optional, for a laptop only (Render's free plan blocks SMTP ports). Set SMTP_HOST,
   SMTP_USER, SMTP_PASSWORD. A message that carries a QR code gets the real QR picture inside the email (and as an attached PNG).

If neither is set, nothing is emailed (the notice is still stored on the Messages page) and the log says so.
Failures are logged and never raised, so a mail problem can never undo an approval.
"""
import asyncio
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx

from . import config

log = logging.getLogger("vista")


def smtp_ready() -> bool:
    return bool(config.SMTP_HOST and (config.SMTP_FROM or config.SMTP_USER))


def emailjs_ready() -> bool:
    return bool(config.EMAILJS_SERVICE_ID and config.EMAILJS_TEMPLATE_ID and config.EMAILJS_PUBLIC_KEY)


def email_ready() -> bool:
    return emailjs_ready() or smtp_ready()


def qr_png(text: str) -> bytes:
    """A PNG picture of a QR code that the gate scanner can read."""
    import io
    import segno
    out = io.BytesIO()
    segno.make(text, error="m").save(out, kind="png", scale=8, border=4, dark="#000000", light="#ffffff")
    return out.getvalue()


def qr_url(token: str) -> str:
    """Address of the QR picture on this API (for the EmailJS template), or '' when PUBLIC_API_URL is not set."""
    base = (config.PUBLIC_API_URL or "").strip().rstrip("/")
    return f"{base}/api/qr/{token}.png" if base else ""


def _html(text: str, qr_code: str | None, img_src: str | None) -> str:
    paras = "".join(f"<p style='margin:0 0 12px'>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in text.split("\n\n") if p.strip())
    img = ""
    if qr_code and img_src:
        img = (f"<div style='text-align:center;margin:18px 0'><img src='{html.escape(img_src, quote=True)}' alt='QR code' width='240' height='240' "
               f"style='border:1px solid #ddd;padding:8px;background:#fff'><div style='font-family:monospace;font-size:13px;color:#555;margin-top:6px'>"
               f"{html.escape(qr_code)}</div></div>")
    return f"<div style='font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#222;max-width:520px'>{paras}{img}</div>"


def _build(to: str, subject: str, text: str, qr_code: str | None, png: bytes | None) -> EmailMessage:
    m = EmailMessage()
    m["From"] = formataddr((config.SMTP_FROM_NAME, config.SMTP_FROM or config.SMTP_USER))
    m["To"] = to
    m["Subject"] = subject
    m["Message-ID"] = make_msgid(domain=(config.SMTP_FROM or config.SMTP_USER).split("@")[-1] or "vista.local")
    m.set_content(text)
    m.add_alternative(_html(text, qr_code, "cid:qrcode" if png else None), subtype="html")
    if png:
        m.get_payload()[1].add_related(png, maintype="image", subtype="png", cid="<qrcode>")
        m.add_attachment(png, maintype="image", subtype="png", filename="vista-qr-code.png")
    return m


def _smtp_send(msg: EmailMessage):
    """Blocking. Raises on any problem (the caller decides whether to log or show it)."""
    mode = (config.SMTP_SECURITY or "starttls").lower()
    ctx = ssl.create_default_context()
    if mode == "ssl":
        s = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15, context=ctx)
    else:
        s = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)
    with s:
        s.ehlo()
        if mode == "starttls":
            s.starttls(context=ctx)
            s.ehlo()
        if config.SMTP_USER:
            s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        s.send_message(msg)


async def _emailjs(to: str, subject: str, message: str, qr_code: str = "", qr_link: str = ""):
    payload = {"service_id": config.EMAILJS_SERVICE_ID, "template_id": config.EMAILJS_TEMPLATE_ID, "user_id": config.EMAILJS_PUBLIC_KEY,
               "template_params": {"to_email": to, "subject": subject, "message": message, "qr_code": qr_code, "qr_url": qr_link}}
    if config.EMAILJS_PRIVATE_KEY:
        payload["accessToken"] = config.EMAILJS_PRIVATE_KEY
    async with httpx.AsyncClient(timeout=10) as h:
        r = await h.post("https://api.emailjs.com/api/v1.0/email/send", json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"EmailJS refused the email ({r.status_code}): {r.text[:200]}")


async def send_email_strict(to: str, subject: str, text: str, qr_code: str | None = None):
    """Sends one email by EmailJS, or by SMTP (laptop) if EmailJS is not set. Raises when it cannot. qr_code is the text inside the QR (VISTA:...)."""
    if emailjs_ready():
        token = (qr_code or "").removeprefix("VISTA:")
        await _emailjs(to, subject, text, qr_code or "", qr_url(token) if token else "")
    elif smtp_ready():
        png = None
        if qr_code:
            try:
                png = await asyncio.to_thread(qr_png, qr_code)
            except Exception as x:   # the email still goes out with the text code
                log.warning("Could not draw the QR picture (%s). Is the 'segno' package installed? Sending the text code only", x)
        await asyncio.to_thread(_smtp_send, _build(to, subject, text, qr_code, png))
    else:
        raise RuntimeError("No email is set up: fill in EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID, EMAILJS_PUBLIC_KEY and EMAILJS_PRIVATE_KEY (hosting), or SMTP_HOST + SMTP_USER + SMTP_PASSWORD (laptop only)")


async def send_email(to: str, subject: str, text: str, qr_code: str | None = None):
    """Same, but a failure is only written to the log."""
    try:
        await send_email_strict(to, subject, text, qr_code)
        log.info("Email sent to %s: %s", to, subject)
    except Exception as x:
        log.warning("EMAIL NOT SENT to %s (%s): %s: %s", to, subject, type(x).__name__, x)
