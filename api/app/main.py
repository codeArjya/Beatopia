"""FastAPI app factory.

USE_FIXTURES=1: every CONTRACT §6 endpoint answers from shared/fixtures (no DB, no CLAP, no Gemini).
Real mode: real routers are mounted; endpoints without a real implementation yet still answer from fixtures, and
startup logs which ones (that list must be empty before the H12 deploy).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app import fixture_routes
from app.core import db, embed
from app.core.chips import load_chips
from app.core.errors import install_error_handlers
from app.core.settings import Settings, get_settings
from app.core.timing import configure_logging, install_timing
from app.fixture_routes import fixture
from app.routes import chips, search, tracks

__all__ = ["app", "create_app", "fixture"]

log = logging.getLogger("app")

# Real routers, mounted in real mode. Each task adds its router here.
REAL_ROUTERS: list[APIRouter] = [chips.router, tracks.router, search.router]


def _route_keys(router: APIRouter) -> set[tuple[str, str]]:
    return {(m, r.path) for r in router.routes if isinstance(r, APIRoute) for m in r.methods}


def _lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.pool = None
        app.state.clap_ready = False
        if not settings.use_fixtures:
            # Fail loudly: a real-mode API without a database, storage URL or vocab is a broken deploy.
            missing = settings.missing("supabase_url")
            if missing:
                raise RuntimeError(f"real mode needs {', '.join(missing)} (or set USE_FIXTURES=1)")
            load_chips(settings.vocab_path)
            app.state.pool = await asyncio.to_thread(db.open_pool, settings)
            app.state.clap_ready = await asyncio.to_thread(embed.warm)
        try:
            yield
        finally:
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
        allow_origins=list(settings.web_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

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
