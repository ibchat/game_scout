from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/health")
def analytics_health() -> Dict[str, Any]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/summary")
def analytics_summary(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    def safe_count(table: str) -> int:
        try:
            return int(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
        except Exception:
            return -1

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "counts": {
            "relaunch_apps": safe_count("relaunch_apps"),
            "relaunch_scores": safe_count("relaunch_scores"),
            "relaunch_app_snapshots": safe_count("relaunch_app_snapshots"),
            "relaunch_reviews": safe_count("relaunch_reviews"),
            "relaunch_ccu_snapshots": safe_count("relaunch_ccu_snapshots"),
        },
    }
