"""FastAPI application: pages, login/logout, background sampler."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import admin, api
from .auth import Authenticator
from .config import Config, load_config
from .db import Database
from .gpu import GPUMonitor
from .sampler import run_sampler
from .state import AppState

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
SESSION_DAYS = 7


def create_app(cfg: Config | None = None, start_sampler: bool = True) -> FastAPI:
    cfg = cfg or load_config()
    if cfg.mock:
        log.warning("MOCK MODE: fake GPUs, any username with password 'test' can log in")
    state = AppState(cfg=cfg, db=Database(cfg), monitor=GPUMonitor(cfg), auth=Authenticator(cfg))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = None
        if start_sampler:
            task = asyncio.create_task(
                run_sampler(state.db, state.monitor, cfg.sample_interval_seconds, cfg.usage_retention_days)
            )
        yield
        if task:
            task.cancel()

    app = FastAPI(title=cfg.site_title, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.app = state
    app.add_middleware(
        SessionMiddleware,
        secret_key=cfg.secret_key,
        session_cookie="usage_web_session",
        max_age=SESSION_DAYS * 86400,
        same_site="lax",
        https_only=cfg.cookie_secure,
    )

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # API writes must come from our own JS (a custom header forces a CORS preflight cross-site).
        if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-requested-with") != "fetch":
                return JSONResponse({"detail": "missing X-Requested-With header"}, status_code=403)
        return await call_next(request)

    app.include_router(api.router)
    app.include_router(admin.router)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    def page(name: str, admin_only: bool = False):
        async def handler(request: Request) -> Response:
            user = request.session.get("user")
            if not user:
                return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
            if admin_only and not user["is_admin"]:
                raise HTTPException(403, "需要管理員權限")
            return templates.TemplateResponse(
                request, f"{name}.html", {"user": user, "cfg": cfg, "page": name}
            )

        return handler

    app.add_api_route("/", page("dashboard"), methods=["GET"], include_in_schema=False)
    app.add_api_route("/calendar", page("calendar"), methods=["GET"], include_in_schema=False)
    app.add_api_route("/my", page("my"), methods=["GET"], include_in_schema=False)
    app.add_api_route("/stats", page("stats"), methods=["GET"], include_in_schema=False)
    app.add_api_route("/admin", page("admin", admin_only=True), methods=["GET"], include_in_schema=False)

    def safe_next(value: str | None) -> str:
        return value if value and value.startswith("/") and not value.startswith("//") else "/"

    @app.get("/login", include_in_schema=False)
    async def login_page(request: Request, next: str = "/"):
        return templates.TemplateResponse(
            request, "login.html", {"cfg": cfg, "next": safe_next(next), "error": None, "username": ""}
        )

    @app.post("/login", include_in_schema=False)
    def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/")):
        client_ip = request.client.host if request.client else "?"
        try:
            user = state.auth.login(username, password, client_ip)
        except HTTPException as e:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"cfg": cfg, "next": safe_next(next), "error": e.detail, "username": username},
                status_code=e.status_code,
            )
        request.session.clear()
        request.session["user"] = {"username": user.username, "is_admin": user.is_admin}
        return RedirectResponse(safe_next(next), status_code=303)

    @app.post("/logout", include_in_schema=False)
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}

    return app

