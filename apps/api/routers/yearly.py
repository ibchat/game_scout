from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(prefix="/yearly", tags=["Yearly Review"])


@router.get("/health")
def yearly_health() -> Dict[str, Any]:
    return {"status": "ok"}


@router.get("/summary")
def yearly_summary() -> Dict[str, Any]:
    return {"status": "ok", "note": "Yearly review is not implemented yet"}