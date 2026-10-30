r"""Sends one test email so you can see right away if your email setup works (it shows the real error if not).
   Windows:  cd backend  then  .venv\Scripts\python mailtest.py you@gmail.com
   Mac/Linux: cd backend && .venv/bin/python mailtest.py you@gmail.com
The test email carries a real QR code, the same kind visitors and households get after an approval."""
import asyncio
import sys

from app import config, mailer


async def main(to: str):
    if mailer.emailjs_ready():
        print("Using EmailJS")
    elif mailer.smtp_ready():
        print(f"Using SMTP: {config.SMTP_HOST}:{config.SMTP_PORT} ({config.SMTP_SECURITY}) as {config.SMTP_USER or config.SMTP_FROM}")
    else:
        print("NO EMAIL SET UP. Open backend/.env and fill in the EMAILJS_* values (or SMTP_USER and SMTP_PASSWORD on a laptop). See EMAIL-SETUP.md.")
        return 1
    try:
        await mailer.send_email_strict(to, "Vista VMS test: your QR code", "This is a test from Vista VMS.\n\nIf you can see a QR code picture below, emailing QR codes works.", "VISTA:test-qr-code")
    except Exception as x:
        print(f"FAILED: {type(x).__name__}: {x}")
        if "535" in str(x) or "Username and Password" in str(x):
            print("-> Wrong login. For Gmail use an App Password (not your normal password), with 2-Step Verification turned on.")
        return 1
    print(f"SENT to {to}. Check the inbox (and the Spam folder).")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python mailtest.py you@example.com")
    sys.exit(asyncio.run(main(sys.argv[1])))
