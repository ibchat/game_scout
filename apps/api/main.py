from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Game Scout API")


def include_router_safe(module_path: str, *, prefix: str = "", tags: Optional[list[str]] = None) -> None:
    """
    Import router module safely.
    If a module fails to import (SyntaxError/IndentationError/etc), do NOT crash the whole API.
    """
    try:
        mod = importlib.import_module(module_path)
        router = getattr(mod, "router", None)
        if router is None:
            print(f"[WARN] {module_path}: router not found")
            return
        app.include_router(router, prefix=prefix, tags=tags)
        print(f"[OK] included router: {module_path} prefix='{prefix}'")
    except Exception as e:
        print(f"[SKIP] failed to import {module_path}: {type(e).__name__}: {e}")


# CORE
include_router_safe("apps.api.routers.health", tags=["Health"])
include_router_safe("apps.api.routers.pitches", prefix="/pitches", tags=["Pitches"])
include_router_safe("apps.api.routers.trends", prefix="/trends", tags=["Trends"])
include_router_safe("apps.api.routers.games", prefix="/games", tags=["Games"])

# AI / Analytics (mounted under /api/v1)
include_router_safe("apps.api.routers.narrative", prefix="/api/v1", tags=["Narrative"])
include_router_safe("apps.api.routers.analytics", prefix="/api/v1", tags=["Analytics"])
include_router_safe("apps.api.routers.morning_scan", prefix="/api/v1", tags=["Morning Scan"])

# Relaunch Scout (mounted under /api/v1)
include_router_safe("apps.api.routers.relaunch", prefix="/api/v1", tags=["Relaunch Scout"])


@app.get("/")
def root():
    return {"status": "ok", "service": "game_scout_api"}


@app.get("/dashboard")
def dashboard():
    p = Path(__file__).resolve().parent / "static" / "game_scout_dashboard.html"
    if not p.exists():
        return JSONResponse({"error": "dashboard file not found", "path": str(p)}, status_code=404)
    return FileResponse(str(p), media_type="text/html")
