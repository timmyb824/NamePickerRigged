"""Application factory and configuration.

Reads config from the environment, wires up middleware and templates, and
includes the route router from ``app.routes``.
"""

import os
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import database as db
from .routes import router

BASE_DIR = Path(__file__).parent


def create_app() -> FastAPI:
    """Application factory — reads config from the environment at startup."""
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

    # Optional analytics (e.g. Umami). Only rendered when both env vars are set,
    # so other self-hosters don't send traffic to someone else's analytics.
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    templates.env.globals["umami_script_url"] = os.environ.get("UMAMI_SCRIPT_URL")
    templates.env.globals["umami_website_id"] = os.environ.get("UMAMI_WEBSITE_ID")
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    app.include_router(router)
    return app


app = create_app()
