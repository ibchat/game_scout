from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/reddit", tags=["Reddit"])


@router.get("/health")
def reddit_health() -> Dict[str, Any]:
    return {"status": "ok"}


@router.get("/summary")
def reddit_summary() -> Dict[str, Any]:
    return {"status": "ok", "items": []}