"""FastAPI entrypoint. Run: uvicorn app.main:app --reload   (API only; the React UI is a separate app in /frontend)"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import router
from .superadmin import router as platform_router
from .core import missing_loop
from .db import create_pool, migrate

log = logging.getLogger("vista")

def check_config():
    """Refuse to start with a sign-in setup that is unsafe or cannot work. Runs before anything touches the database."""
    if config.STAFF_ACCESS_CODE and not config.SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set when STAFF_ACCESS_CODE is set")
    if config.SUPER_ADMIN_CODE and not config.SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set when SUPER_ADMIN_CODE is set")
    if config.SUPER_ADMIN_CODE and config.SUPER_ADMIN_CODE == config.STAFF_ACCESS_CODE:
        raise RuntimeError("SUPER_ADMIN_CODE must be different from STAFF_ACCESS_CODE: the staff code must never open the platform")
    if config.ON_RENDER and not config.STAFF_ACCESS_CODE and not config.ALLOW_DEMO_AUTH:
        raise RuntimeError("STAFF_ACCESS_CODE is not set: anyone could sign in as Admin by sending a role header. "
                           "Set STAFF_ACCESS_CODE (and SECRET_KEY), or ALLOW_DEMO_AUTH=1 for a throwaway demo.")
    if config.SECRET_KEY and len(config.SECRET_KEY) < 16:
        log.warning("SECRET_KEY is shorter than 16 characters: anyone who guesses it can forge sign-in tokens. Use a long random value")
    if not config.STAFF_ACCESS_CODE:
        log.warning("STAFF_ACCESS_CODE is not set: demo mode, anyone who can reach this API can act as any role. Never expose it publicly")
    if config.ON_RENDER and not config.FRONTEND_URL:
        log.warning("FRONTEND_URL is not set: household invitation links cannot be built")


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_config()
    app.state.pool = await create_pool(config.DATABASE_URL)
    if config.AUTO_MIGRATE:
        await migrate(app.state.pool)
    if config.AUTO_SEED:
        from .seed import seed
        await seed(app.state.pool)
    if config.AUTO_BOOTSTRAP and not config.AUTO_SEED:
        from .seed import bootstrap
        await bootstrap(app.state.pool, config.VILLAGE_NAME, None, config.PASS_COUNT)
    task = asyncio.create_task(missing_loop(app.state.pool))  # 3-hour Missing flag, checked every minute
    yield
    task.cancel()
    await app.state.pool.close()


app = FastAPI(title="Vista VMS: Village", lifespan=lifespan)
app.include_router(router, prefix="/api")
app.include_router(platform_router, prefix="/api/platform")


class BodyLimit:
    """Refuses a request body that is too large before the app reads it, whether or not the sender declares a length.
    Without this, one huge upload to a public endpoint (the visitor form) is read whole into memory first."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = config.MAX_MAP_BODY_BYTES if scope["path"].rstrip("/") == "/api/map" else config.MAX_BODY_BYTES
        seen, tripped = 0, False

        async def too_big():
            body = b'{"detail":"That upload is too large. Choose a smaller file."}'
            await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})

        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            return await too_big()

        async def counted():
            # No length was declared (chunked), or it was understated: count what actually arrives. The 413 goes out from here, and the app is
            # told the sender has gone, because FastAPI would turn any error raised while it reads the body into a 400.
            nonlocal seen, tripped
            if tripped:
                return {"type": "http.disconnect"}
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    tripped = True
                    await too_big()
                    return {"type": "http.disconnect"}
            return msg

        async def watched(msg):
            if not tripped:   # once the 413 is out, whatever the app tries to send after that is dropped
                await send(msg)

        try:
            await self.app(scope, counted, watched)
        except Exception:
            if not tripped:
                raise


app.add_middleware(BodyLimit)   # added before CORS, so CORS wraps it and the browser can read the 413


# The React UI is hosted separately (Vercel). It sends an Authorization header, not cookies, so no credentials are needed.
_origins = [o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=config.CORS_ORIGIN_REGEX or None,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "Vista VMS API", "health": "/api/health", "docs": "/docs"}
