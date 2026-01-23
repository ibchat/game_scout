"""
Trends Scout: Daily Aggregation & Emerging Detection
Aggregates raw signals into daily trends and computes emerging games/tags.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import json

logger = logging.getLogger(__name__)


def _latest_numeric(db, app_id: int, source: str, signal_type: str, day: date) -> Optional[float]:
    """
    Get latest numeric signal value for a given app, source, signal_type, and day.
    Returns float or None.
    """
    result = db.execute(
        text("""
            SELECT value_numeric
            FROM trends_raw_signals
            WHERE steam_app_id = :app_id
              AND source = :source
              AND signal_type = :signal_type
              AND DATE(captured_at) = :day
            ORDER BY captured_at DESC
            LIMIT 1
        """),
        {"app_id": app_id, "source": source, "signal_type": signal_type, "day": day}
    ).scalar()
    
    return float(result) if result is not None else None


def aggregate_daily_trends(db, target_date: Optional[date] = None, days_back: int = 0) -> Dict[str, Any]:
    """
    Aggregate daily trends from raw signals.
    If days_back > 0, performs backfill for past days.
    """
    if target_date is None:
        target_date = date.today()
    
    dates_to_process = [target_date - timedelta(days=i) for i in range(days_back + 1)]
    
    logger.info(f"trends_aggregate_start date={target_date} days_back={days_back} total_dates={len(dates_to_process)}")
    
    total_rows = 0
    error_msg = None
    
    for process_date in dates_to_process:
        try:
            # Get all active seed apps
            seed_apps = db.execute(
                text("""
                    SELECT steam_app_id, region_hint
                    FROM trends_seed_apps
                    WHERE is_active = true
                """)
            ).mappings().all()
            
            games_processed = 0
            
            for seed in seed_apps:
                app_id = seed["steam_app_id"]
                
                # First, ensure numeric signals are ingested from steam_review_daily
                from apps.worker.tasks.trends_collectors import ingest_review_signals_from_daily
                ingest_review_signals_from_daily(db, app_id, process_date)
                
                # Get reviews_total: first try raw signals (all_reviews_count), then fallback to steam_review_daily
                reviews_total = _latest_numeric(
                    db, app_id, 'steam_reviews', 'all_reviews_count', process_date
                )
                if reviews_total is None:
                    # Try previous day if not found
                    prev_date = process_date - timedelta(days=1)
                    reviews_total = _latest_numeric(
                        db, app_id, 'steam_reviews', 'all_reviews_count', prev_date
                    )
                
                # Fallback to steam_review_daily if still None
                if reviews_total is None:
                    review_data = db.execute(
                        text("""
                            SELECT all_reviews_count
                            FROM steam_review_daily
                            WHERE steam_app_id = :app_id AND day = :process_date
                            ORDER BY computed_at DESC
                            LIMIT 1
                        """),
                        {"app_id": app_id, "process_date": process_date}
                    ).scalar()
                    if review_data is not None:
                        reviews_total = float(review_data)
                
                # Keep NULL if missing (don't force 0 per new requirement)
                
                # Get positive_ratio: first try raw signals (all_positive_ratio), then fallback to steam_review_daily
                positive_ratio = _latest_numeric(
                    db, app_id, 'steam_reviews', 'all_positive_ratio', process_date
                )
                if positive_ratio is None:
                    # Try previous day if not found
                    prev_date = process_date - timedelta(days=1)
                    positive_ratio = _latest_numeric(
                        db, app_id, 'steam_reviews', 'all_positive_ratio', prev_date
                    )
                
                # Fallback to steam_review_daily if still None
                if positive_ratio is None:
                    review_data = db.execute(
                        text("""
                            SELECT all_positive_percent
                            FROM steam_review_daily
                            WHERE steam_app_id = :app_id AND day = :process_date
                            ORDER BY computed_at DESC
                            LIMIT 1
                        """),
                        {"app_id": app_id, "process_date": process_date}
                    ).scalar()
                    if review_data is not None:
                        positive_ratio = float(review_data) / 100.0
                    # Keep NULL if missing (don't force 0.0 per requirement)
                
                # Calculate reviews_delta_1d
                prev_date = process_date - timedelta(days=1)
                prev_reviews_total = _latest_numeric(
                    db, app_id, 'steam_reviews', 'all_reviews_count', prev_date
                )
                # Fallback to steam_review_daily for previous day
                if prev_reviews_total is None:
                    prev_review_data = db.execute(
                        text("""
                            SELECT all_reviews_count
                            FROM steam_review_daily
                            WHERE steam_app_id = :app_id AND day = :prev_date
                            ORDER BY computed_at DESC
                            LIMIT 1
                        """),
                        {"app_id": app_id, "prev_date": prev_date}
                    ).scalar()
                    if prev_review_data is not None:
                        prev_reviews_total = float(prev_review_data)
                
                reviews_delta_1d = None
                if reviews_total is not None and prev_reviews_total is not None:
                    reviews_delta_1d = int(reviews_total - prev_reviews_total)
                
                # Calculate reviews_delta_7d (7-day delta)
                seven_days_ago = process_date - timedelta(days=7)
                baseline_reviews_total = _latest_numeric(
                    db, app_id, 'steam_reviews', 'all_reviews_count', seven_days_ago
                )
                # If baseline not found, try nearest within 1 day
                if baseline_reviews_total is None:
                    six_days_ago = process_date - timedelta(days=6)
                    baseline_reviews_total = _latest_numeric(
                        db, app_id, 'steam_reviews', 'all_reviews_count', six_days_ago
                    )
                
                # Fallback to steam_review_daily for baseline
                if baseline_reviews_total is None:
                    baseline_review_data = db.execute(
                        text("""
                            SELECT all_reviews_count
                            FROM steam_review_daily
                            WHERE steam_app_id = :app_id AND day = :seven_days_ago
                            ORDER BY computed_at DESC
                            LIMIT 1
                        """),
                        {"app_id": app_id, "seven_days_ago": seven_days_ago}
                    ).scalar()
                    if baseline_review_data is not None:
                        baseline_reviews_total = float(baseline_review_data)
                    # Try 6 days ago if 7 days ago not found
                    if baseline_reviews_total is None:
                        six_days_ago = process_date - timedelta(days=6)
                        baseline_review_data = db.execute(
                            text("""
                                SELECT all_reviews_count
                                FROM steam_review_daily
                                WHERE steam_app_id = :app_id AND day = :six_days_ago
                                ORDER BY computed_at DESC
                                LIMIT 1
                            """),
                            {"app_id": app_id, "six_days_ago": six_days_ago}
                        ).scalar()
                        if baseline_review_data is not None:
                            baseline_reviews_total = float(baseline_review_data)
                
                # Calculate reviews_delta_7d: NULL when missing history, not 0
                reviews_delta_7d = None
                if reviews_total is not None and baseline_reviews_total is not None:
                    reviews_delta_7d = int(reviews_total - baseline_reviews_total)
                # If missing baseline, keep NULL (don't fake zeros)
                
                # Get discussion deltas from raw signals (keep NULL if missing)
                discussions_delta_1d = _latest_numeric(
                    db, app_id, 'steam_discussions', 'discussion_threads_7d', process_date
                )
                discussions_delta_1d = int(discussions_delta_1d) if discussions_delta_1d is not None else None
                
                # Calculate discussions_delta_7d (keep NULL until implemented)
                discussions_delta_7d = None  # Placeholder until implemented
                
                # Get tags from raw signals (text signal, may contain JSON array string)
                tags_signal = db.execute(
                    text("""
                        SELECT value_text
                        FROM trends_raw_signals
                        WHERE steam_app_id = :app_id
                          AND source = 'steam_store'
                          AND signal_type = 'tag_growth'
                          AND DATE(captured_at) = :process_date
                        ORDER BY captured_at DESC
                        LIMIT 1
                    """),
                    {"app_id": app_id, "process_date": process_date}
                ).scalar()
                
                tags = None
                if tags_signal:
                    if isinstance(tags_signal, str):
                        try:
                            tags = json.loads(tags_signal)
                        except:
                            tags = None
                    else:
                        tags = tags_signal
                
                # Compute why_flagged
                why_flagged = []
                if reviews_delta_7d and reviews_delta_7d > 100:
                    why_flagged.append(f"High review velocity: +{reviews_delta_7d} reviews in 7d")
                if discussions_delta_7d and discussions_delta_7d > 10:
                    why_flagged.append(f"Active discussions: +{discussions_delta_7d} threads in 7d")
                if positive_ratio and positive_ratio >= 0.85:
                    why_flagged.append(f"High positive ratio: {int(positive_ratio * 100)}%")
                
                # Upsert trends_game_daily (ensure non-null deltas)
                db.execute(
                    text("""
                        INSERT INTO trends_game_daily
                            (day, steam_app_id, reviews_total, reviews_delta_1d, reviews_delta_7d,
                             discussions_delta_1d, discussions_delta_7d, positive_ratio, tags, computed_at, why_flagged)
                        VALUES
                            (:day, :steam_app_id, :reviews_total, :reviews_delta_1d, :reviews_delta_7d,
                             :discussions_delta_1d, :discussions_delta_7d, :positive_ratio, CAST(:tags AS jsonb), :computed_at, CAST(:why_flagged AS jsonb))
                        ON CONFLICT (day, steam_app_id) DO UPDATE SET
                            reviews_total = EXCLUDED.reviews_total,
                            reviews_delta_1d = EXCLUDED.reviews_delta_1d,
                            reviews_delta_7d = EXCLUDED.reviews_delta_7d,
                            discussions_delta_1d = EXCLUDED.discussions_delta_1d,
                            discussions_delta_7d = EXCLUDED.discussions_delta_7d,
                            positive_ratio = EXCLUDED.positive_ratio,
                            tags = EXCLUDED.tags,
                            computed_at = EXCLUDED.computed_at,
                            why_flagged = EXCLUDED.why_flagged
                    """),
                    {
                        "day": process_date,
                        "steam_app_id": app_id,
                        "reviews_total": int(reviews_total) if reviews_total is not None else None,
                        "reviews_delta_1d": reviews_delta_1d,  # NULL when missing history
                        "reviews_delta_7d": reviews_delta_7d,  # NULL when missing history
                        "discussions_delta_1d": discussions_delta_1d,  # NULL when missing
                        "discussions_delta_7d": discussions_delta_7d,  # NULL when missing
                        "positive_ratio": positive_ratio,
                        "tags": json.dumps(tags) if tags else None,
                        "computed_at": datetime.now(),
                        "why_flagged": json.dumps(why_flagged) if why_flagged else None,
                    }
                )
                
                games_processed += 1
            
            db.commit()
            total_rows += games_processed
            logger.info(f"trends_aggregate_done date={process_date} games_processed={games_processed}")
            
        except Exception as e:
            error_msg = f"trends_aggregate_fail date={process_date} error={repr(e)}"
            logger.error(error_msg, exc_info=True)
            db.rollback()
            return {
                "ok": False,
                "rows": total_rows,
                "error": error_msg
            }
    
    return {
        "ok": True,
        "rows": total_rows,
        "error": None
    }


def compute_emerging_games(
    db,
    window_days: int = 7,
    min_reviews_delta_7d: Optional[int] = None,
    min_discussions_delta_7d: Optional[int] = None,
    min_positive_ratio: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Compute emerging games based on daily aggregates.
    Returns list of games with why_flagged explanations.
    """
    cutoff_date = date.today() - timedelta(days=window_days)
    
    # Check if we have sufficient history
    history_days = db.execute(
        text("""
            SELECT COUNT(DISTINCT day)
            FROM trends_game_daily
            WHERE day >= :cutoff_date
        """),
        {"cutoff_date": cutoff_date}
    ).scalar() or 0
    
    if history_days < 2:
        return {
            "games": [],
            "reason": "insufficient_history",
            "history_days": history_days,
            "required_days": 2,
            "message": f"Need at least 2 days of history, found {history_days}"
        }
    
    # Query emerging games
    query = text("""
        SELECT 
            tgd.steam_app_id,
            tgd.reviews_total,
            tgd.reviews_delta_7d,
            tgd.discussions_delta_1d,
            tgd.positive_ratio,
            tgd.tags,
            tgd.why_flagged,
            f.name,
            f.release_date,
            seed.region_hint
        FROM trends_game_daily tgd
        JOIN trends_seed_apps seed ON seed.steam_app_id = tgd.steam_app_id
        LEFT JOIN steam_app_facts f ON f.steam_app_id = tgd.steam_app_id
        WHERE tgd.day = CURRENT_DATE
          AND seed.is_active = true
    """)
    
    params = {}
    
    if min_reviews_delta_7d is not None:
        query = text(str(query).replace("WHERE", "WHERE tgd.reviews_delta_7d >= :min_reviews_delta_7d AND"))
        params["min_reviews_delta_7d"] = min_reviews_delta_7d
    
    if min_discussions_delta_7d is not None:
        query = text(str(query).replace("AND seed.is_active", "AND tgd.discussions_delta_1d >= :min_discussions_delta_7d AND seed.is_active"))
        params["min_discussions_delta_7d"] = min_discussions_delta_7d
    
    if min_positive_ratio is not None:
        query = text(str(query).replace("AND seed.is_active", "AND tgd.positive_ratio >= :min_positive_ratio AND seed.is_active"))
        params["min_positive_ratio"] = min_positive_ratio
    
    query = text(str(query) + " ORDER BY tgd.reviews_delta_7d DESC NULLS LAST LIMIT 100")
    
    rows = db.execute(query, params).mappings().all()
    
    games = []
    for row in rows:
        why_flagged = row["why_flagged"]
        if isinstance(why_flagged, str):
            try:
                why_flagged = json.loads(why_flagged)
            except:
                why_flagged = []
        elif why_flagged is None:
            why_flagged = []
        
        tags = row["tags"]
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except:
                tags = []
        elif tags is None:
            tags = []
        
        games.append({
            "steam_app_id": row["steam_app_id"],
            "name": row["name"],
            "reviews_total": row["reviews_total"],
            "reviews_delta_7d": row["reviews_delta_7d"],
            "discussions_delta_1d": row["discussions_delta_1d"],
            "positive_ratio": float(row["positive_ratio"]) if row["positive_ratio"] else None,
            "tags": tags,
            "why_flagged": why_flagged,
            "release_date": row["release_date"].isoformat() if row["release_date"] else None,
            "region_hint": row["region_hint"],
        })
    
    return {
        "games": games,
        "reason": "ok",
        "history_days": history_days,
        "count": len(games)
    }


def compute_emerging_tags(db, window_days: int = 7) -> Dict[str, Any]:
    """
    Compute emerging tags from game daily aggregates.
    """
    cutoff_date = date.today() - timedelta(days=window_days)
    
    # Aggregate tags from trends_game_daily
    tag_aggregates = db.execute(
        text("""
            WITH tag_expanded AS (
                SELECT 
                    tgd.day,
                    jsonb_array_elements_text(tgd.tags) as tag,
                    tgd.reviews_delta_7d,
                    tgd.discussions_delta_1d
                FROM trends_game_daily tgd
                WHERE tgd.day >= :cutoff_date
                  AND tgd.tags IS NOT NULL
            )
            SELECT 
                tag,
                COUNT(DISTINCT day) as days_present,
                SUM(COALESCE(reviews_delta_7d, 0)) as total_reviews_delta_7d,
                SUM(COALESCE(discussions_delta_1d, 0)) as total_discussions_delta_7d
            FROM tag_expanded
            GROUP BY tag
            HAVING COUNT(DISTINCT day) >= 2
            ORDER BY total_reviews_delta_7d DESC
            LIMIT 50
        """),
        {"cutoff_date": cutoff_date}
    ).mappings().all()
    
    tags = []
    for row in tag_aggregates:
        why_flagged = []
        if row["total_reviews_delta_7d"] and row["total_reviews_delta_7d"] > 100:
            why_flagged.append(f"High review velocity: +{row['total_reviews_delta_7d']} in 7d")
        if row["total_discussions_delta_7d"] and row["total_discussions_delta_7d"] > 50:
            why_flagged.append(f"Active discussions: +{row['total_discussions_delta_7d']} in 7d")
        
        tags.append({
            "tag": row["tag"],
            "days_present": row["days_present"],
            "reviews_delta_7d": row["total_reviews_delta_7d"],
            "discussions_delta_7d": row["total_discussions_delta_7d"],
            "why_flagged": why_flagged,
        })
    
    return {
        "tags": tags,
        "count": len(tags)
    }


if __name__ == "__main__":
    # Standalone runner
    import os
    from apps.db.session import get_db_session
    
    db = get_db_session()
    
    result = aggregate_daily_trends(db, date.today(), days_back=7)
    print(f"Aggregation result: {result}")
    emerging = compute_emerging_games(db, window_days=7)
    print(f"Emerging games: {emerging['count']}")
    
    db.close()
