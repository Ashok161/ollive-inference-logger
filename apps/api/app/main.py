from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import init_db
from .routers import conversations, ingest, metrics
from .services.queue import event_queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ollive.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info("Starting API (provider=%s model=%s)", settings.default_provider, settings.default_model)
    await init_db()
    try:
        await event_queue.connect()
        await event_queue.ensure_group("workers")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis not ready at startup: %s", exc)
    yield
    await event_queue.close()


app = FastAPI(
    title="Ollive Inference Logger",
    description="Chatbot + inference logging ingestion API",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
_origins = settings.cors_origin_list or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Browsers reject allow_credentials=True with wildcard origins.
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(conversations.router)
app.include_router(metrics.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve built web UI from the same service (production single-URL deploy).
_static_dir = Path(os.getenv("STATIC_DIR", "/app/static"))
if _static_dir.is_dir() and (_static_dir / "index.html").exists():
    assets = _static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    async def spa_index():
        return FileResponse(_static_dir / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Never shadow API routes (registered above); this only handles UI paths.
        if full_path.startswith("v1/") or full_path in {"health", "docs", "openapi.json", "redoc"}:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not found")
        candidate = _static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static_dir / "index.html")
