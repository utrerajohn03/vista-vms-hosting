import os
from pathlib import Path


def _load_env_file():
    """Reads backend/.env (or a .env next to the project folder) so settings such as SMTP_* work on a laptop without exporting
    anything. A variable that is really set in the environment always wins over the file."""
    here = Path(__file__).resolve().parent.parent
    for f in (here / ".env", here.parent / ".env"):
        try:
            if not f.is_file():
                continue
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if v and v[0] in "\"'" and v.count(v[0]) >= 2:
                    v = v[1:v.index(v[0], 1)]
                else:
                    v = v.split(" #", 1)[0].strip()
                if k and v:
                    os.environ.setdefault(k, v)
        except OSError:
            pass


_load_env_file()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://vista:vista@localhost:5432/vista")
DEFAULT_PROPERTY = os.getenv("DEFAULT_PROPERTY", "greenfield-village-7f3a")
AUTH_MODE = os.getenv("AUTH_MODE", "dev")  # dev = role comes from request headers (no login check)
AUTO_MIGRATE = os.getenv("AUTO_MIGRATE", "1") == "1"
AUTO_SEED = os.getenv("AUTO_SEED", "0") == "1"
MISSING_HOURS = int(os.getenv("MISSING_HOURS", "3"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Manila")
PHOTO_RETENTION_DAYS = int(os.getenv("PHOTO_RETENTION_DAYS", "30"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
TRUST_PROXY_HOPS = int(os.getenv("TRUST_PROXY_HOPS", "1"))   # proxies in front of the API (Render = 1). 0 = ignore X-Forwarded-For
LOGIN_RATE_LIMIT_PER_MIN = int(os.getenv("LOGIN_RATE_LIMIT_PER_MIN", "20"))   # staff sign-in attempts per IP per minute; keep low in production
EMAILJS_SERVICE_ID = os.getenv("EMAILJS_SERVICE_ID", "")
EMAILJS_TEMPLATE_ID = os.getenv("EMAILJS_TEMPLATE_ID", "")
EMAILJS_PUBLIC_KEY = os.getenv("EMAILJS_PUBLIC_KEY", "")
EMAILJS_PRIVATE_KEY = os.getenv("EMAILJS_PRIVATE_KEY", "")  # needed for calls from a server (Account > Security: allow non-browser apps)

# --- email by SMTP (optional, laptop only: Render free blocks SMTP; EmailJS above is the platform tool). Gmail: smtp.gmail.com, port 587, starttls, an App Password ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").replace(" ", "")   # Gmail shows an App Password in groups of four: spaces are removed
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Vista VMS")
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls")    # starttls (port 587) | ssl (port 465) | none
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "") or os.getenv("RENDER_EXTERNAL_URL", "")   # this API's public address (on Render it is filled in by itself), e.g. https://vista-api.onrender.com (lets the EmailJS template show the QR picture)

# --- hosting (Render + Supabase) ---
STAFF_ACCESS_CODE = os.getenv("STAFF_ACCESS_CODE", "")   # set it to require a code at staff sign-in (recommended when public)
SECRET_KEY = os.getenv("SECRET_KEY", "")                 # signs session tokens; required when STAFF_ACCESS_CODE is set
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "12"))
CRON_KEY = os.getenv("CRON_KEY", "")                     # lets an external cron call /api/cron/missing while the host sleeps
DB_SSL = os.getenv("DB_SSL", "auto")                     # auto | require | disable
DB_PGBOUNCER = os.getenv("DB_PGBOUNCER", "")             # 1 = transaction pooler (disables prepared statements)
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "8"))
ENABLE_RLS = os.getenv("ENABLE_RLS", "1") == "1"
SCHEMA_CHECK = os.getenv("SCHEMA_CHECK", "1") == "1"   # 0 = skip the start-up check that tables shared with a platform have the columns and values the app needs
VILLAGE_NAME = os.getenv("VILLAGE_NAME", "Greenfield Village")
AUTO_BOOTSTRAP = os.getenv("AUTO_BOOTSTRAP", "0") == "1"  # create an empty property (one gate, 20 passes) if it does not exist
PASS_COUNT = int(os.getenv("PASS_COUNT", "20"))

# --- CORS: the React app (Vercel) calls this API from another origin ---
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")  # comma separated, or *
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", "")  # optional: also allow origins matching this regex (Vercel preview URLs)

# --- invitations and published-mode safety ---
FRONTEND_URL = os.getenv("FRONTEND_URL", "")             # the Vercel address; invitation links point here, e.g. https://vista-vms.vercel.app
INVITE_DAYS = int(os.getenv("INVITE_DAYS", "30"))        # how long a household sign-in link works
SUPER_ADMIN_CODE = os.getenv("SUPER_ADMIN_CODE", "")     # the platform owner's sign-in code (not the village staff code). Needs SECRET_KEY too
ADMIN_LINK_DAYS = int(os.getenv("ADMIN_LINK_DAYS", "14"))  # how long the Admin's first sign-in link works
APPROVAL_DAYS = int(os.getenv("APPROVAL_DAYS", "7"))     # how long the approve/decline link in the household email works
ALLOW_DEMO_AUTH = os.getenv("ALLOW_DEMO_AUTH", "0") == "1"  # Render only: allow running without STAFF_ACCESS_CODE (throwaway demos)
ON_RENDER = bool(os.getenv("RENDER"))                    # Render sets this itself
STAFF_CODE_LOGIN = os.getenv("STAFF_CODE_LOGIN", "1") == "1"   # 0 = the shared staff code no longer signs anyone in; only personal accounts do
MIN_PASSWORD = 10
MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", "3000000"))          # largest request body the API reads (a 1.5 MB photo is about 2 MB as base64)
MAX_MAP_BODY_BYTES = int(os.getenv("MAX_MAP_BODY_BYTES", "12000000"))   # the village map import (8 MB file, about 10.7 MB as base64)
SEED_PASSWORD = os.getenv("SEED_PASSWORD", "")   # demo/test only: gives the seeded Admin, guards and HOA accounts this password (10+ characters). Empty = no password
