"""
FastAPI backend for MITRE data management.
APIs defined per assignment.md (APT-ONE assessment).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, graph, mitre, search
from app.db import close_db, close_neo4j, init_db, init_neo4j


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_neo4j()
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
