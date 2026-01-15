from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session

router = APIRouter(prefix="/relaunch", tags=["Relaunch Scout"])


# -------------------------
# Schemas
# -------------------------
class TrackAppRequest(BaseModel):
    steam_app_id: int = Field(..., ge=1)
    name: str = Field(..., min_length=1, max_length=200)
    tracking_priority: int = Field(50, ge=0, le=100)


class BulkTrackRequest(BaseModel):
    """
    Дефолтный bulk_track:
    - если передан steam_app_ids -> добавляем их в relaunch_apps (upsert)
    - если НЕ передан steam_app_ids -> возвращаем понятный ответ (не падаем)
    """
    steam_app_ids: Optional[List[int]] = None

    # оставляем поля под твой текущий вызов (limit/min_reviews/priority),
    # чтобы endpoint принимал запрос и отвечал, а не "пусто"
    limit: int = Field(200, ge=1, le=5000)
    min_reviews: int = Field(200, ge=0, le=1000000)
    tracking_priority: int = Field(50, ge=0, le=100)


# -------------------------
# Helpers
# -------------------------
def _now_utc() -> str:
    return datetime.utcnow().isoformat()


# -------------------------
# Routes
# -------------------------
@router.get("/health")
def relaunch_health(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    tracked = db.execute(
        text("SELECT COUNT(*) FROM relaunch_apps WHERE is_active = true")
    ).scalar() or 0

    return {"status": "healthy", "tracked_apps": int(tracked), "timestamp": _now_utc()}


@router.get("/candidates")
def relaunch_candidates(
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    limit: int = Query(200, ge=1, le=1000),
    classification: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    sql = """
        WITH latest_scores AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                computed_at,
                relaunch_score,
                classification,
                failure_reasons,
                relaunch_angles,
                reasoning_text
            FROM relaunch_scores
            ORDER BY app_id, computed_at DESC
        ),
        latest_snapshots AS (
            SELECT DISTINCT ON (app_id)
                app_id,
                captured_at,
                price_eur,
                discount_percent,
                is_on_sale,
                all_reviews_count,
                all_reviews_positive_percent,
                recent_reviews_count,
                recent_reviews_positive_percent,
                tags,
                genres,
                languages,
                developers,
                publishers,
                release_date,
                last_update_date
            FROM relaunch_app_snapshots
            ORDER BY app_id, captured_at DESC
        )
        SELECT
            ra.id AS app_id,
            ra.steam_app_id,
            ra.name,
            COALESCE(ls.relaunch_score, 0) AS relaunch_score,
            COALESCE(ls.classification, 'unknown') AS classification,
            ls.failure_reasons,
            ls.relaunch_angles,
            ls.reasoning_text,
            ls.computed_at,
            s.captured_at,
            s.price_eur,
            s.discount_percent,
            s.is_on_sale,
            s.all_reviews_count,
            s.all_reviews_positive_percent,
            s.recent_reviews_count,
            s.recent_reviews_positive_percent,
            s.tags,
            s.genres
        FROM relaunch_apps ra
        LEFT JOIN latest_scores ls ON ls.app_id = ra.id
        LEFT JOIN latest_snapshots s ON s.app_id = ra.id
        WHERE COALESCE(ls.relaunch_score, 0) >= :min_score
    """

    params: Dict[str, Any] = {"min_score": float(min_score), "limit": int(limit)}

    if classification:
        sql += " AND COALESCE(ls.classification, 'unknown') = :classification"
        params["classification"] = classification

    sql += " ORDER BY COALESCE(ls.relaunch_score, 0) DESC, ra.added_at DESC LIMIT :limit"

    rows = db.execute(text(sql), params).mappings().all()

    out: List[Dict[str, Any]] = []
    for r in rows:
        latest_snapshot = None
        if r.get("captured_at") is not None:
            latest_snapshot = {
                "captured_at": r.get("captured_at"),
                "price_eur": float(r.get("price_eur") or 0.0),
                "discount_percent": int(r.get("discount_percent") or 0),
                "is_on_sale": bool(r.get("is_on_sale")) if r.get("is_on_sale") is not None else False,
                "all_reviews_count": int(r.get("all_reviews_count") or 0),
                "all_reviews_positive_percent": int(r.get("all_reviews_positive_percent") or 0),
                "recent_reviews_count": int(r.get("recent_reviews_count") or 0),
                "recent_reviews_positive_percent": int(r.get("recent_reviews_positive_percent") or 0),
                "tags": r.get("tags") or [],
                "genres": r.get("genres") or [],
            }

        out.append(
            {
                "app_id": str(r["app_id"]),
                "steam_app_id": int(r["steam_app_id"]),
                "name": r["name"],
                "relaunch_score": float(r.get("relaunch_score") or 0.0),
                "classification": r.get("classification") or "unknown",
                "failure_reasons": r.get("failure_reasons") or [],
                "relaunch_angles": r.get("relaunch_angles") or [],
                "reasoning": r.get("reasoning_text") or "",
                "latest_snapshot": latest_snapshot,
                "computed_at": r.get("computed_at"),
            }
        )

    return out


@router.post("/admin/track")
def relaunch_track_app(request: TrackAppRequest, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    existing = db.execute(
        text("SELECT id FROM relaunch_apps WHERE steam_app_id = :sid"),
        {"sid": request.steam_app_id},
    ).fetchone()

    if existing:
        return {"status": "exists", "app_id": str(existing[0])}

    new_id = db.execute(
        text(
            """
            INSERT INTO relaunch_apps (steam_app_id, name, tracking_priority)
            VALUES (:sid, :name, :priority)
            RETURNING id
            """
        ),
        {"sid": request.steam_app_id, "name": request.name, "priority": request.tracking_priority},
    ).scalar()

    db.commit()
    return {"status": "ok", "app_id": str(new_id)}


@router.post("/admin/bulk_track")
def relaunch_bulk_track(request: BulkTrackRequest, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    # Дефолт: если список app_ids не передан — endpoint не падает, а отвечает.
    if not request.steam_app_ids:
        return {
            "status": "ok",
            "added": 0,
            "skipped": 0,
            "note": "bulk_track готов. Чтобы реально добавить много игр, передай steam_app_ids: [..]. "
                    "Текущий запрос (limit/min_reviews/priority) принят, но источник списка игр не настроен.",
            "timestamp": _now_utc(),
        }

    added = 0
    skipped = 0

    # Upsert по steam_app_id
    for sid in request.steam_app_ids:
        sid = int(sid)
        row = db.execute(
            text("SELECT id FROM relaunch_apps WHERE steam_app_id = :sid"),
            {"sid": sid},
        ).fetchone()

        if row:
            skipped += 1
            continue

        # имя пока можно ставить sid как строку — позже ты можешь обновлять снапшотами
        db.execute(
            text(
                """
                INSERT INTO relaunch_apps (steam_app_id, name, tracking_priority, is_active)
                VALUES (:sid, :name, :priority, true)
                """
            ),
            {"sid": sid, "name": f"Steam App {sid}", "priority": int(request.tracking_priority)},
        )
        added += 1

    db.commit()

    return {
        "status": "ok",
        "added": added,
        "skipped": skipped,
        "tracking_priority": int(request.tracking_priority),
        "timestamp": _now_utc(),
    }


@router.get("/app/{app_id}")
def relaunch_app_details(app_id: str, db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    try:
        app_uuid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid app_id format")

    app = db.execute(
        text("SELECT id, steam_app_id, name, added_at FROM relaunch_apps WHERE id = :id"),
        {"id": app_uuid},
    ).fetchone()

    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    return {
        "app_id": str(app[0]),
        "steam_app_id": int(app[1]),
        "name": app[2],
        "tracking_since": app[3],
    }