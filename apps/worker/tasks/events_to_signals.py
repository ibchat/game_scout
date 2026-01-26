"""
Normalize raw events to signals.
Aggregates events by steam_app_id and time windows (24h, 7d, 30d).
"""
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def aggregate_events_to_signals(
    db: Session,
    source: str,
    target_date: Optional[date] = None
) -> Dict[str, int]:
    """
    Aggregate matched events to signals for a specific source.
    Creates signals like: {source}_posts_7d, {source}_velocity, etc.
    
    Returns: {signals_inserted, games_processed}
    """
    if target_date is None:
        target_date = date.today()
    
    logger.info(f"events_to_signals_start source={source} date={target_date}")
    
    try:
        # Get matched events for this source in last 7 days
        seven_days_ago = target_date - timedelta(days=7)
        fourteen_days_ago = target_date - timedelta(days=14)
        
        # Aggregate by steam_app_id
        current_week = db.execute(
            text("""
                SELECT 
                    matched_steam_app_id as steam_app_id,
                    COUNT(*)::int as events_count,
                    MAX(published_at) as latest_published_at
                FROM trends_raw_events
                WHERE source = :source
                  AND matched_steam_app_id IS NOT NULL
                  AND published_at >= :seven_days_ago
                  AND published_at < :target_date_end
                GROUP BY matched_steam_app_id
            """),
            {
                "source": source,
                "seven_days_ago": seven_days_ago,
                "target_date_end": target_date + timedelta(days=1)
            }
        ).mappings().all()
        
        signals_inserted = 0
        
        for row in current_week:
            steam_app_id = row["steam_app_id"]
            events_count = row["events_count"]
            latest_published = row["latest_published_at"]
            
            # Get previous week for velocity
            prev_week = db.execute(
                text("""
                    SELECT COUNT(*)::int
                    FROM trends_raw_events
                    WHERE source = :source
                      AND matched_steam_app_id = :app_id
                      AND published_at >= :fourteen_days_ago
                      AND published_at < :seven_days_ago
                """),
                {
                    "source": source,
                    "app_id": steam_app_id,
                    "fourteen_days_ago": fourteen_days_ago,
                    "seven_days_ago": seven_days_ago
                }
            ).scalar() or 0
            
            velocity = events_count - prev_week if prev_week > 0 else events_count
            
            # Calculate freshness (hours since latest event)
            freshness_hours = None
            if latest_published:
                delta = datetime.now() - latest_published.replace(tzinfo=None) if latest_published.tzinfo else datetime.now() - latest_published
                freshness_hours = int(delta.total_seconds() / 3600)
            
            # Source-specific signal aggregation
            if source == "reddit":
                # Reddit-specific signals
                # Get comments count and uniqueness (different subreddits)
                reddit_details = db.execute(
                    text("""
                        SELECT 
                            SUM((metrics_json->>'num_comments')::int)::int as total_comments,
                            COUNT(DISTINCT metrics_json->>'subreddit')::int as unique_subreddits
                        FROM trends_raw_events
                        WHERE source = 'reddit'
                          AND matched_steam_app_id = :app_id
                          AND published_at >= :seven_days_ago
                          AND published_at < :target_date_end
                    """),
                    {
                        "app_id": steam_app_id,
                        "seven_days_ago": seven_days_ago,
                        "target_date_end": target_date + timedelta(days=1)
                    }
                ).mappings().first()
                
                total_comments = reddit_details["total_comments"] or 0 if reddit_details else 0
                unique_subreddits = reddit_details["unique_subreddits"] or 0 if reddit_details else 0
                
                # reddit_posts_count_7d
                db.execute(
                    text("""
                        INSERT INTO trends_raw_signals 
                            (steam_app_id, source, signal_type, value_numeric, captured_at)
                        VALUES (:steam_app_id, 'reddit', 'reddit_posts_count_7d', :value, :captured_at)
                        ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                        SET value_numeric = EXCLUDED.value_numeric
                    """),
                    {
                        "steam_app_id": steam_app_id,
                        "value": float(events_count),
                        "captured_at": datetime.combine(target_date, datetime.min.time())
                    }
                )
                signals_inserted += 1
                
                # reddit_comments_count_7d
                if total_comments > 0:
                    db.execute(
                        text("""
                            INSERT INTO trends_raw_signals 
                                (steam_app_id, source, signal_type, value_numeric, captured_at)
                            VALUES (:steam_app_id, 'reddit', 'reddit_comments_count_7d', :value, :captured_at)
                            ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                            SET value_numeric = EXCLUDED.value_numeric
                        """),
                        {
                            "steam_app_id": steam_app_id,
                            "value": float(total_comments),
                            "captured_at": datetime.combine(target_date, datetime.min.time())
                        }
                    )
                    signals_inserted += 1
                
                # reddit_uniqueness (different subreddits)
                if unique_subreddits > 0:
                    db.execute(
                        text("""
                            INSERT INTO trends_raw_signals 
                                (steam_app_id, source, signal_type, value_numeric, captured_at)
                            VALUES (:steam_app_id, 'reddit', 'reddit_uniqueness', :value, :captured_at)
                            ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                            SET value_numeric = EXCLUDED.value_numeric
                        """),
                        {
                            "steam_app_id": steam_app_id,
                            "value": float(unique_subreddits),
                            "captured_at": datetime.combine(target_date, datetime.min.time())
                        }
                    )
                    signals_inserted += 1
                
            elif source == "youtube":
                # YouTube-specific signals
                # Get views count and channel quality
                youtube_details = db.execute(
                    text("""
                        SELECT 
                            SUM((metrics_json->>'view_count')::bigint)::bigint as total_views,
                            COUNT(DISTINCT metrics_json->>'channel_id')::int as unique_channels,
                            AVG((metrics_json->>'like_count')::int)::float as avg_likes
                        FROM trends_raw_events
                        WHERE source = 'youtube'
                          AND matched_steam_app_id = :app_id
                          AND published_at >= :seven_days_ago
                          AND published_at < :target_date_end
                    """),
                    {
                        "app_id": steam_app_id,
                        "seven_days_ago": seven_days_ago,
                        "target_date_end": target_date + timedelta(days=1)
                    }
                ).mappings().first()
                
                total_views = youtube_details["total_views"] or 0 if youtube_details else 0
                unique_channels = youtube_details["unique_channels"] or 0 if youtube_details else 0
                avg_likes = youtube_details["avg_likes"] or 0.0 if youtube_details else 0.0
                
                # youtube_videos_count_7d
                db.execute(
                    text("""
                        INSERT INTO trends_raw_signals 
                            (steam_app_id, source, signal_type, value_numeric, captured_at)
                        VALUES (:steam_app_id, 'youtube', 'youtube_videos_count_7d', :value, :captured_at)
                        ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                        SET value_numeric = EXCLUDED.value_numeric
                    """),
                    {
                        "steam_app_id": steam_app_id,
                        "value": float(events_count),
                        "captured_at": datetime.combine(target_date, datetime.min.time())
                    }
                )
                signals_inserted += 1
                
                # youtube_views_7d
                if total_views > 0:
                    db.execute(
                        text("""
                            INSERT INTO trends_raw_signals 
                                (steam_app_id, source, signal_type, value_numeric, captured_at)
                            VALUES (:steam_app_id, 'youtube', 'youtube_views_7d', :value, :captured_at)
                            ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                            SET value_numeric = EXCLUDED.value_numeric
                        """),
                        {
                            "steam_app_id": steam_app_id,
                            "value": float(total_views),
                            "captured_at": datetime.combine(target_date, datetime.min.time())
                        }
                    )
                    signals_inserted += 1
                
                # youtube_channel_quality (unique channels + avg likes as proxy)
                if unique_channels > 0:
                    channel_quality = min(10.0, unique_channels * 0.5 + (avg_likes / 100.0))
                    db.execute(
                        text("""
                            INSERT INTO trends_raw_signals 
                                (steam_app_id, source, signal_type, value_numeric, captured_at)
                            VALUES (:steam_app_id, 'youtube', 'youtube_channel_quality', :value, :captured_at)
                            ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                            SET value_numeric = EXCLUDED.value_numeric
                        """),
                        {
                            "steam_app_id": steam_app_id,
                            "value": float(channel_quality),
                            "captured_at": datetime.combine(target_date, datetime.min.time())
                        }
                    )
                    signals_inserted += 1
                
            else:
                # Generic signal for other sources (steam_news, etc.)
                signal_type_base = f"{source}_posts_7d"
                db.execute(
                    text("""
                        INSERT INTO trends_raw_signals 
                            (steam_app_id, source, signal_type, value_numeric, captured_at)
                        VALUES (:steam_app_id, :source, :signal_type, :value, :captured_at)
                        ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                        SET value_numeric = EXCLUDED.value_numeric
                    """),
                    {
                        "steam_app_id": steam_app_id,
                        "source": source,
                        "signal_type": signal_type_base,
                        "value": float(events_count),
                        "captured_at": datetime.combine(target_date, datetime.min.time())
                    }
                )
                signals_inserted += 1
            
            # Velocity signal (for all sources)
            velocity_signal_type = f"{source}_velocity"
            db.execute(
                text("""
                    INSERT INTO trends_raw_signals 
                        (steam_app_id, source, signal_type, value_numeric, captured_at)
                    VALUES (:steam_app_id, :source, :signal_type, :value, :captured_at)
                    ON CONFLICT (steam_app_id, source, signal_type, DATE(captured_at)) DO UPDATE
                    SET value_numeric = EXCLUDED.value_numeric
                """),
                {
                    "steam_app_id": steam_app_id,
                    "source": source,
                    "signal_type": velocity_signal_type,
                    "value": float(velocity),
                    "captured_at": datetime.combine(target_date, datetime.min.time())
                }
            )
            signals_inserted += 1
            
            # Freshness signal (if available)
            if freshness_hours is not None:
                db.execute(
                    text("""
                        INSERT INTO trends_raw_signals 
                            (steam_app_id, source, signal_type, value_numeric, captured_at)
                        VALUES (:steam_app_id, :source, :signal_type, :value, :captured_at)
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "steam_app_id": steam_app_id,
                        "source": source,
                        "signal_type": f"{source}_freshness_hours",
                        "value": float(freshness_hours),
                        "captured_at": datetime.combine(target_date, datetime.min.time())
                    }
                )
                signals_inserted += 1
        
        db.commit()
        
        stats = {
            "signals_inserted": signals_inserted,
            "games_processed": len(current_week)
        }
        
        logger.info(f"events_to_signals_done source={source} {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"events_to_signals_fail source={source} error={e}", exc_info=True)
        db.rollback()
        return {"signals_inserted": 0, "games_processed": 0}


def migrate_existing_to_events(
    db: Session,
    source: str,
    table_name: str,
    id_column: str,
    title_column: str,
    url_column: str,
    published_at_column: str,
    body_column: Optional[str] = None
) -> Dict[str, int]:
    """
    Migrate existing Reddit/YouTube data to trends_raw_events format.
    One-time migration function.
    """
    logger.info(f"migrate_to_events_start source={source} table={table_name}")
    
    try:
        # Build query based on table structure
        select_cols = f"{id_column}, {title_column}, {url_column}, {published_at_column}"
        if body_column:
            select_cols += f", {body_column}"
        
        query = f"""
            SELECT {select_cols}
            FROM {table_name}
            WHERE {published_at_column} >= now() - interval '30 days'
            ORDER BY {published_at_column} DESC
            LIMIT 1000
        """
        
        rows = db.execute(text(query)).mappings().all()
        
        inserted = 0
        skipped = 0
        
        for row in rows:
            external_id = str(row[id_column])
            title = row.get(title_column, "")
            url = row.get(url_column, "")
            published_at = row.get(published_at_column)
            body = row.get(body_column) if body_column else None
            
            # Check if exists
            existing = db.execute(
                text("""
                    SELECT id FROM trends_raw_events
                    WHERE source = :source AND external_id = :external_id
                """),
                {"source": source, "external_id": external_id}
            ).scalar_one_or_none()
            
            if existing:
                skipped += 1
                continue
            
            # Insert
            db.execute(
                text("""
                    INSERT INTO trends_raw_events 
                        (source, external_id, url, title, body, published_at, captured_at)
                    VALUES 
                        (:source, :external_id, :url, :title, :body, :published_at, :captured_at)
                """),
                {
                    "source": source,
                    "external_id": external_id,
                    "url": url,
                    "title": title,
                    "body": body,
                    "published_at": published_at,
                    "captured_at": datetime.now()
                }
            )
            inserted += 1
        
        db.commit()
        
        stats = {"inserted": inserted, "skipped": skipped}
        logger.info(f"migrate_to_events_done source={source} {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"migrate_to_events_fail source={source} error={e}", exc_info=True)
        db.rollback()
        return {"inserted": 0, "skipped": 0}


if __name__ == "__main__":
    from apps.db.session import get_db_session
    
    db = get_db_session()
    try:
        # Test aggregation
        stats = aggregate_events_to_signals(db, "steam_news")
        print(f"Aggregated signals: {stats}")
    finally:
        db.close()
