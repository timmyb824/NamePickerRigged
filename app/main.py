"""FastAPI application: routes, auth, and the spin/rig logic.

Design notes:
- The wheel display page and the spin API are intentionally unauthenticated so
  the teacher can project them for the class. Only the /admin pages require the
  per-wheel password.
- The spin result is always computed server-side. A rigged spin returns the
  exact same response shape as a random one, so the outcome rigging is
  invisible to anyone watching the page or its network traffic.
"""

import os
import random
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import database as db
from .security import hash_password, new_wheel_code, verify_password

BASE_DIR = Path(__file__).parent
MAX_NAMES = 200
MAX_NAME_LEN = 60
_rng = random.SystemRandom()


class RigUpdate(BaseModel):
    """Payload for setting or clearing a rigged outcome."""

    rig_index: int | None = Field(default=None, ge=0)
    mode: str = Field(default="once", pattern="^(once|sticky)$")


class WheelContent(BaseModel):
    """Payload for updating a wheel's title and names."""

    title: str = Field(min_length=1, max_length=100)
    names: list[str]


def _parse_names(raw: str) -> list[str]:
    """Parse a textarea of one-name-per-line into a clean, de-duplicated list."""
    names: list[str] = []
    for line in raw.splitlines():
        if (name := line.strip()[:MAX_NAME_LEN]) and name not in names:
            names.append(name)
    return names


def _is_admin(request: Request, code: str) -> bool:
    """Return True if the session is authenticated as this wheel's admin."""
    return bool(request.session.get(f"admin_{code}"))


def _require_admin(request: Request, code: str) -> None:
    """Raise 403 unless the session is authenticated as this wheel's admin."""
    if not _is_admin(request, code):
        raise HTTPException(status_code=403, detail="Not authorized")


def _get_wheel_or_404(code: str):
    """Fetch a wheel or raise 404."""
    if (wheel := db.get_wheel(code)) is None:
        raise HTTPException(status_code=404, detail="Wheel not found")
    return wheel


def create_app() -> FastAPI:
    """Application factory — reads config from the environment at build time."""
    app = FastAPI(title="Name Picker", docs_url=None, redoc_url=None, openapi_url=None)
    db.init_db()

    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        secret = secrets.token_urlsafe(32)
        print(
            "WARNING: SESSION_SECRET is not set; using a random secret. "
            "Admin logins will not survive restarts."
        )
    app.add_middleware(SessionMiddleware, secret_key=secret, https_only=False)

    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

    # ---------- public pages ----------

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """Landing page with the create-a-wheel form."""
        return templates.TemplateResponse(request, "index.html")

    @app.post("/wheels")
    async def create_wheel(
        request: Request,
        title: str = Form(..., max_length=100),
        password: str = Form(..., min_length=4, max_length=128),
        names: str = Form(...),
    ) -> Response:
        """Create a wheel and log the creator in as its admin."""
        if len(parsed := _parse_names(names)) < 2:
            return templates.TemplateResponse(
                request,
                "index.html",
                {"error": "Please enter at least 2 names."},
                status_code=400,
            )
        if len(parsed) > MAX_NAMES:
            parsed = parsed[:MAX_NAMES]
        code = new_wheel_code()
        db.create_wheel(
            code, title.strip() or "Name Picker", hash_password(password), parsed
        )
        request.session[f"admin_{code}"] = True
        return RedirectResponse(f"/w/{code}/admin?created=1", status_code=303)

    @app.get("/w/{code}", response_class=HTMLResponse)
    async def wheel_page(request: Request, code: str) -> HTMLResponse:
        """The public wheel page — safe to project for the class."""
        wheel = _get_wheel_or_404(code)
        return templates.TemplateResponse(
            request, "wheel.html", {"code": code, "title": wheel["title"]}
        )

    @app.get("/w/{code}/api/wheel")
    async def wheel_data(code: str) -> dict:
        """Public wheel data (title + names) for rendering the canvas."""
        wheel = _get_wheel_or_404(code)
        return {"title": wheel["title"], "names": db.wheel_names(wheel)}

    @app.post("/w/{code}/api/spin")
    async def spin(code: str) -> JSONResponse:
        """Compute a spin result. Rigged spins are indistinguishable from random ones."""
        wheel = _get_wheel_or_404(code)
        names = db.wheel_names(wheel)
        if len(names) < 2:
            raise HTTPException(status_code=400, detail="Wheel needs at least 2 names")

        rig_index = wheel["rig_index"]
        rig_mode = wheel["rig_mode"]
        if rig_index is not None and 0 <= rig_index < len(names):
            winner = rig_index
            if rig_mode == "once":
                db.clear_rig(code)
        else:
            winner = _rng.randrange(len(names))

        return JSONResponse({"winner_index": winner, "winner_name": names[winner]})

    # ---------- admin pages ----------

    @app.get("/w/{code}/admin", response_class=HTMLResponse)
    async def admin_page(request: Request, code: str, created: int = 0) -> HTMLResponse:
        """Admin login form, or the admin panel if already authenticated."""
        wheel = _get_wheel_or_404(code)
        if not _is_admin(request, code):
            return templates.TemplateResponse(
                request, "admin_login.html", {"code": code, "title": wheel["title"]}
            )
        names = db.wheel_names(wheel)
        rig_index = wheel["rig_index"]
        rig_name = (
            names[rig_index]
            if rig_index is not None and rig_index < len(names)
            else None
        )
        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                "code": code,
                "title": wheel["title"],
                "names": names,
                "rig_name": rig_name,
                "rig_mode": wheel["rig_mode"],
                "created": created,
            },
        )

    @app.post("/w/{code}/admin/login")
    async def admin_login(
        request: Request, code: str, password: str = Form(...)
    ) -> RedirectResponse:
        """Authenticate as a wheel's admin via its password."""
        wheel = _get_wheel_or_404(code)
        if not verify_password(password, wheel["password_hash"]):
            return RedirectResponse(f"/w/{code}/admin?error=1", status_code=303)
        request.session[f"admin_{code}"] = True
        return RedirectResponse(f"/w/{code}/admin", status_code=303)

    @app.post("/w/{code}/admin/logout")
    async def admin_logout(request: Request, code: str) -> RedirectResponse:
        """Clear this wheel's admin session."""
        request.session.pop(f"admin_{code}", None)
        return RedirectResponse(f"/w/{code}", status_code=303)

    @app.post("/w/{code}/admin/content")
    async def update_content(
        request: Request, code: str, content: WheelContent
    ) -> dict:
        """Replace a wheel's title and name list (admin only)."""
        _require_admin(request, code)
        _get_wheel_or_404(code)
        names = [n.strip()[:MAX_NAME_LEN] for n in content.names if n.strip()]
        names = list(dict.fromkeys(names))[:MAX_NAMES]
        if len(names) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 names")
        db.update_title(code, content.title.strip())
        db.update_names(code, names)
        db.clear_rig(
            code
        )  # indexes shift when the list changes; never keep a stale rig
        return {"ok": True, "names": names}

    @app.post("/w/{code}/admin/rig")
    async def update_rig(request: Request, code: str, rig: RigUpdate) -> dict:
        """Set or clear the rigged outcome (admin only)."""
        _require_admin(request, code)
        wheel = _get_wheel_or_404(code)
        if rig.rig_index is None:
            db.clear_rig(code)
            return {"ok": True, "rigged": False}
        names = db.wheel_names(wheel)
        if rig.rig_index >= len(names):
            raise HTTPException(status_code=400, detail="Invalid name index")
        db.set_rig(code, rig.rig_index, rig.mode)
        return {
            "ok": True,
            "rigged": True,
            "rig_name": names[rig.rig_index],
            "mode": rig.mode,
        }

    @app.post("/w/{code}/admin/delete")
    async def delete_wheel(request: Request, code: str) -> RedirectResponse:
        """Delete a wheel entirely (admin only)."""
        _require_admin(request, code)
        db.delete_wheel(code)
        request.session.pop(f"admin_{code}", None)
        return RedirectResponse("/", status_code=303)

    return app


app = create_app()
