from __future__ import annotations

import asyncio
import fcntl
import hmac
import logging
import time
from contextlib import asynccontextmanager, suppress
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .collector import collect
from .config import ROOT, Settings
from .control import Control, EmailSettings, NoticeSettings, initialize_token
from .guide_render import render_guides
from .guides import GuideConflict, GuideNotFound, GuideRepository, GuideRevision, GuideWrite
from .mailer import deliver_pending
from .store import Store

log = logging.getLogger("monitor")


def create_app(settings: Settings, *, run_collector=True, collector=collect, config_path: Path | None = None):
    store = Store(settings)
    initialize_token(store)
    control = Control(store, config_path)
    guides = GuideRepository(store)
    guides.initialize(ROOT / "monitor/troubleshooting-seed.json")

    async def worker():
        while True:
            started = time.monotonic()
            try:
                snapshot = await asyncio.to_thread(collector, store.settings)
                await asyncio.to_thread(store.record, snapshot)
                await asyncio.to_thread(deliver_pending, store)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Monitor cycle failed (%s)", type(exc).__name__)
            await asyncio.sleep(max(1, store.settings.poll_seconds - (time.monotonic() - started)))

    @asynccontextmanager
    async def lifespan(app):
        task = lock = None
        try:
            if run_collector:
                lock = (settings.state_dir / "collector.lock").open("a+")
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                task = asyncio.create_task(worker())
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if lock:
                lock.close()

    app = FastAPI(title="Codex LB Status", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    app.state.guides = guides
    configured_hosts = [urlsplit(settings.origin).hostname, *settings.allowed_hosts, "127.0.0.1", "localhost"]
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(
            dict.fromkeys(candidate for host in configured_hosts if host for candidate in (host, host.lower()))
        ),
    )

    def authenticated_control(request):
        try:
            local = ip_address(request.client.host).is_loopback
            file = settings.control_token_file
            if not local or file.stat().st_mode & 0o077:
                return False
            token = file.read_text().strip()
            supplied = request.headers.get("authorization", "")
            return len(token) >= 32 and hmac.compare_digest(supplied, f"Bearer {token}")
        except (ValueError, OSError, AttributeError):
            return False

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        if request.url.path.startswith("/internal/") and not authenticated_control(request):
            return JSONResponse({"detail": "Service authentication required"}, status_code=401)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON required"}, status_code=415)
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                limit = 65536 if request.url.path.startswith("/internal/guides") else 20000
                if len(raw) > limit:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            request._body = bytes(raw)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        if settings.secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"detail": "Invalid control request"}, status_code=422)

    @app.exception_handler(GuideNotFound)
    async def guide_not_found(request, exc):
        return JSONResponse({"detail": "Guide not found"}, status_code=404)

    @app.exception_handler(GuideConflict)
    async def guide_conflict(request, exc):
        return JSONResponse({"detail": "Guide changed; refresh before saving"}, status_code=409)

    @app.get("/internal/guides")
    def list_guides():
        return {"available": True, "guides": guides.list()}

    @app.post("/internal/guides", status_code=201)
    def create_guide(body: GuideWrite):
        return guides.save(body)

    @app.put("/internal/guides/{guide_id}")
    def update_guide(guide_id: int, body: GuideWrite):
        return guides.save(body, guide_id)

    @app.delete("/internal/guides/{guide_id}")
    def delete_guide(guide_id: int, body: GuideRevision):
        return guides.set_deleted(guide_id, body.revision)

    @app.post("/internal/guides/{guide_id}/restore")
    def restore_guide(guide_id: int, body: GuideRevision):
        return guides.set_deleted(guide_id, body.revision, restore=True)

    @app.get("/static/faq.html", response_class=HTMLResponse)
    def faq():
        template = (ROOT / "monitor/static/faq.html").read_text()
        return template.replace("<!-- PUBLISHED_GUIDES -->", render_guides(guides.list(public=True)))

    @app.get("/static/troubleshooting.html", include_in_schema=False)
    def legacy_troubleshooting():
        return RedirectResponse("/static/faq.html", status_code=308)

    @app.get("/health")
    def health():
        s = store.latest()
        fresh = s and time.time() - s["collected_at"] <= max(3 * settings.poll_seconds, 120)
        return JSONResponse({"status": "ok" if fresh else "stale"}, status_code=200 if fresh else 503)

    @app.get("/api/status")
    def status():
        return store.public()

    @app.get("/internal/settings")
    def overview():
        return control.overview()

    @app.put("/internal/email")
    def save_email(body: EmailSettings):
        try:
            return control.update_email(body)
        except (ValueError, OSError):
            raise HTTPException(400, "Unable to save email configuration") from None

    @app.post("/internal/notices", status_code=201)
    def create_notice(body: NoticeSettings):
        return {"id": store.save_notice(body.stored())}

    @app.put("/internal/notices/{notice_id}")
    def update_notice(notice_id: int, body: NoticeSettings):
        result = store.save_notice(body.stored(), notice_id)
        if result is None:
            raise HTTPException(404, "Announcement not found")
        return {"id": result}

    @app.get("/")
    def index():
        return FileResponse(ROOT / "monitor/static/index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "monitor/static"), name="static")
    return app
