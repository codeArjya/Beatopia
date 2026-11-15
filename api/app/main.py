"""FastAPI app factory.

USE_FIXTURES=1: every CONTRACT §6 endpoint answers from shared/fixtures (no DB, no CLAP, no Gemini).
Real mode: real routers are mounted; endpoints without a real implementation yet still answer from fixtures, and
startup logs which ones (that list must be empty before the H12 deploy).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import fixture_routes
from app.core import db, embed, gemini
from app.core.chips import load_chips
from app.core.errors import install_error_handlers
from app.core.freesound import Freesound
from app.core.planner import vocab_tags
from app.core.settings import Settings, get_settings, origin_regex
from app.core.timing import configure_logging, install_timing
from app.fixture_routes import fixture
from app.routes import assist, chips, events, imports, jobs, search, tracks, why

__all__ = ["app", "create_app", "fixture"]

log = logging.getLogger("app")
REVISION_HEADER = "X-Beatopia-Revision"


def clap_identity() -> tuple[str, str]:
    """(model, revision) that common.clap loads; read without importing torch-heavy code twice."""
    from common import clap

    return clap.CLAP_MODEL, getattr(clap, "CLAP_REVISION", "main")


# Real routers, mounted in real mode. Each task adds its router here.
REAL_ROUTERS: list[APIRouter] = [
    chips.router,
    tracks.router,
    search.router,
    why.router,
    jobs.router,
    imports.router,
    events.router,
    assist.router,
]


def _route_keys(router: APIRouter) -> set[tuple[str, str]]:
    return {(m, r.path) for r in router.routes if isinstance(r, APIRoute) for m in r.methods}


def _lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.pool = None
        app.state.clap_ready = False
        app.state.gemini = None
        app.state.freesound = None
        if not settings.use_fixtures:
            # Fail loudly: a real-mode API without a database, storage URL or vocab is a broken deploy.
            missing = settings.missing("supabase_url")
            if missing:
                raise RuntimeError(f"real mode needs {', '.join(missing)} (or set USE_FIXTURES=1)")
            load_chips(settings.vocab_path)
            app.state.pool = await asyncio.to_thread(db.open_pool, settings)
            app.state.clap_ready = await asyncio.to_thread(embed.warm)
            app.state.gemini = gemini.from_settings(settings)
            if settings.freesound_api_key:
                app.state.freesound = Freesound(settings.freesound_api_key, vocab=vocab_tags(settings.vocab_path))
            else:
                log.warning("FREESOUND_API_KEY is not set: the search fallback is off")
        clap_model, clap_rev = clap_identity() if not settings.use_fixtures else ("-", "-")
        log.info(
            "identity: revision=%s mode=%s clap=%s@%s clap_ready=%s gemini=%s",
            settings.revision,
            "fixtures" if settings.use_fixtures else "real",
            clap_model,
            clap_rev,
            app.state.clap_ready,
            settings.gemini_model,
        )
        try:
            yield
        finally:
            if app.state.freesound is not None:
                app.state.freesound.close()
                app.state.freesound = None
            if app.state.pool is not None:
                await asyncio.to_thread(app.state.pool.close)
                app.state.pool = None

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    app = FastAPI(title="Beatopia API", version="0.1.0", lifespan=_lifespan(settings))
    app.state.settings = settings

    install_timing(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in settings.web_origins if "*" not in o],
        allow_origin_regex=origin_regex(settings.web_origins),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Server-Timing", REVISION_HEADER],
    )
    install_error_handlers(app)

    @app.middleware("http")
    async def _revision(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers[REVISION_HEADER] = settings.revision
        return response

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    implemented: set[tuple[str, str]] = set()
    if not settings.use_fixtures:
        for router in REAL_ROUTERS:
            app.include_router(router)
            implemented |= _route_keys(router)

    stand_ins = APIRouter()
    for route in fixture_routes.router.routes:
        if isinstance(route, APIRoute) and not {(m, route.path) for m in route.methods} <= implemented:
            stand_ins.routes.append(route)
    app.include_router(stand_ins)

    if not settings.use_fixtures and stand_ins.routes:
        names = ", ".join(f"{m} {r.path}" for r in stand_ins.routes if isinstance(r, APIRoute) for m in r.methods)
        log.warning("real mode: still serving fixtures for %s", names)
    return app


app = create_app()
