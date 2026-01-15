from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text

from apps.worker.celery_app import celery_app
from apps.worker.relaunch_scorer import RelaunchScorer

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/game_scout")
engine = create_engine(DATABASE_URL, future=True)


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return "[]"


def _get_latest_snapshot(conn, app_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        text(
            """
            SELECT
                price_eur, discount_percent, is_on_sale,
                all_reviews_count, all_reviews_positive_percent,
                recent_reviews_count, recent_reviews_positive_percent,
                tags, genres, languages, developers, publishers,
                capsule_image_url, header_image_url, trailer_url,
                release_date, last_update_date
            FROM relaunch_app_snapshots
            WHERE app_id = :app_id
            ORDER BY captured_at DESC
            LIMIT 1
            """
        ),
        {"app_id": app_id},
    ).mappings().first()
    return dict(row) if row else None


def _get_recent_reviews(conn, app_id: str, limit_reviews: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT
                steam_review_id, review_text, language, is_positive,
                playtime_forever_hours, playtime_at_review_hours,
                posted_at, votes_helpful, votes_funny, signals, sentiment_score
            FROM relaunch_reviews
            WHERE app_id = :app_id
            ORDER BY posted_at DESC
            LIMIT :lim
            """
        ),
        {"app_id": app_id, "lim": limit_reviews},
    ).mappings().all()
    return [dict(r) for r in rows]


@celery_app.task(name="apps.worker.tasks.compute_relaunch_scores.compute_relaunch_scores_task")
def compute_relaunch_scores_task(limit_apps: int = 50, limit_reviews: int = 200, limit_ccu_points: int = 120):
    """
    Compute relaunch scores for active tracked apps and store into relaunch_scores.
    MVP: uses latest snapshot + (optional) recent reviews.
    """
    scorer = RelaunchScorer()
    now = datetime.utcnow()
    computed = 0

    with engine.connect() as conn:
        apps = conn.execute(
            text(
                """
                SELECT id, steam_app_id, name
                FROM relaunch_apps
                WHERE is_active = true
                ORDER BY added_at DESC
                LIMIT :lim
                """
            ),
            {"lim": limit_apps},
        ).mappings().all()

        for a in apps:
            app_id = str(a["id"])
            steam_app_id = str(a["steam_app_id"])
            name = str(a["name"])

            snapshot = _get_latest_snapshot(conn, app_id)
            reviews = _get_recent_reviews(conn, app_id, limit_reviews)

            # If no snapshot, we cannot score.
            if not snapshot:
                continue

            # aggregated_signals can be added later by your review classifier pipeline
            aggregated_signals: Dict[str, Any] = {
                "signal_ratios": {},
                "evidence": {},
                "total_reviews": len(reviews),
            }

            result = scorer.compute_score(
                app_data={"steam_app_id": steam_app_id, "name": name},
                snapshots=[snapshot],
                reviews=reviews,
                aggregated_signals=aggregated_signals,
            )

            conn.execute(
                text(
                    """
                    INSERT INTO relaunch_scores (
                        app_id, computed_at,
                        relaunch_score, classification,
                        product_quality_score, marketing_failure_score, genre_mismatch_score,
                        latent_audience_score, dev_signal_score,
                        failure_reasons, relaunch_angles,
                        broken_game_evidence, marketing_fail_evidence,
                        genre_mismatch_evidence, underrated_evidence,
                        reviews_analyzed_count, avg_playtime_hours, review_velocity_30d,
                        reasoning_text
                    ) VALUES (
                        :app_id, :computed_at,
                        :relaunch_score, :classification,
                        :product_quality_score, :marketing_failure_score, :genre_mismatch_score,
                        :latent_audience_score, :dev_signal_score,
                        CAST(:failure_reasons AS json), CAST(:relaunch_angles AS json),
                        CAST(:broken_game_evidence AS json), CAST(:marketing_fail_evidence AS json),
                        CAST(:genre_mismatch_evidence AS json), CAST(:underrated_evidence AS json),
                        :reviews_analyzed_count, :avg_playtime_hours, :review_velocity_30d,
                        :reasoning_text
                    )
                    """
                ),
                {
                    "app_id": app_id,
                    "computed_at": now,
                    "relaunch_score": float(result.get("relaunch_score", 0.0)),
                    "classification": str(result.get("classification", "unknown")),
                    "product_quality_score": float(result.get("product_quality_score", 0.0)),
                    "marketing_failure_score": float(result.get("marketing_failure_score", 0.0)),
                    "genre_mismatch_score": float(result.get("genre_mismatch_score", 0.0)),
                    "latent_audience_score": float(result.get("latent_audience_score", 0.0)),
                    "dev_signal_score": float(result.get("dev_signal_score", 0.0)),
                    "failure_reasons": _safe_json_dumps(result.get("failure_reasons") or []),
                    "relaunch_angles": _safe_json_dumps(result.get("relaunch_angles") or []),
                    "broken_game_evidence": _safe_json_dumps(result.get("broken_game_evidence") or []),
                    "marketing_fail_evidence": _safe_json_dumps(result.get("marketing_fail_evidence") or []),
                    "genre_mismatch_evidence": _safe_json_dumps(result.get("genre_mismatch_evidence") or []),
                    "underrated_evidence": _safe_json_dumps(result.get("underrated_evidence") or []),
                    "reviews_analyzed_count": int(result.get("reviews_analyzed_count") or 0),
                    "avg_playtime_hours": float(result.get("avg_playtime_hours") or 0.0),
                    "review_velocity_30d": float(result.get("review_velocity_30d") or 0.0),
                    "reasoning_text": str(result.get("reasoning_text") or ""),
                },
            )

            conn.execute(
                text("UPDATE relaunch_apps SET last_score_at = :ts WHERE id = :app_id"),
                {"ts": now, "app_id": app_id},
            )

            computed += 1

        conn.commit()

    return {"status": "ok", "computed": computed}
