from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/youtube", tags=["YouTube"])


@router.get("/health")
def youtube_health() -> Dict[str, Any]:
    return {"status": "ok"}


@router.get("/summary")
def youtube_summary() -> Dict[str, Any]:
    # Пока пусто, но это реальный endpoint — вкладка “живая”
    return {"status": "ok", "items": []}