"""
FastAPI backend for MITRE data management.
APIs defined per assignment.md (APT-ONE assessment).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, mitre
from app.db import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="MITRE Backend API",
    description="Backend API for MITRE data management (vector + graph)",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(mitre.router, prefix="/api/mitre", tags=["mitre"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])


@app.get("/health")
async def health():
    """Health check for Docker/orchestration."""
    return {"status": "ok"}
