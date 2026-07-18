from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
app.include_router(conversations.router)
app.include_router(metrics.router)


@app.get("/health")
async def health():
    return {"status": "ok"}