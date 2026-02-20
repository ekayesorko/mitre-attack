"""
FastAPI backend for MITRE data management.
APIs defined per assignment.md (APT-ONE assessment).
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pythonjsonlogger import jsonlogger

from app.api import chat, graph, mitre, search
from app.db import close_db, close_neo4j, init_db, init_neo4j
from app.config import settings

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logger: JSON format to stderr, level from settings (e.g. LOG_LEVEL=INFO)."""
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(settings.log_level)
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(lineno)s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)


_setup_logging()


def _log_routes(app: FastAPI) -> None:
    """Log all registered routes at startup."""
    logger.info("Registered routes:")
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                line = f"  {method} {route.path}"
                logger.info(line)
                logger.info(line)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_neo4j()
    _log_routes(app)
    yield
    await close_neo4j()
    await close_db()


app = FastAPI(
    title="MITRE Backend API",
    description="Backend API for MITRE data management (vector + graph)",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(mitre.router, prefix="/api/mitre", tags=["mitre"])
app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(search.router, prefix="/api/search", tags=["search"])


@app.get("/health")
async def health():
    """Health check for Docker/orchestration."""
    return {"status": "ok"}
