"""
Collect Steam News/Updates for seed apps.
Fetches news from Steam Store API and saves as raw events.
"""
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import requests

logger = logging.getLogger(__name__)


def fetch_steam_news(app_id: int, max_news: int = 10) -> List[Dict]:
    """
    Fetch news/updates for a Steam app.
    Uses Steam Store API: https://store.steampowered.com/news/?appids={app_id}
    
    Returns: list of news items with title, url, published_at, etc.
    """
    try:
        # Steam News API endpoint (JSON format)
        url = f"https://store.steampowered.com/news/?appids={app_id}&feed=steam_community_announcements&count={max_news}"
        
        # Try to get JSON response
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GameScout/1.0)"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Steam returns HTML with embedded JSON, need to parse
        # Alternative: use RSS feed or parse HTML
        # For now, use a simpler approach: try to extract from HTML
        
        # If response is JSON (sometimes Steam returns JSON)
        try:
            data = response.json()
            if isinstance(data, dict) and str(app_id) in data:
                app_news = data[str(app_id)]
                if isinstance(app_news, list):
                    return app_news
        except:
            pass
        
        # Fallback: return empty (will implement HTML parsing if needed)
        logger.warning(f"steam_news_fetch_fallback app_id={app_id} - HTML parsing not implemented yet")
        return []
        
    except Exception as e:
        logger.warning(f"steam_news_fetch_error app_id={app_id} error={e}")
        return []


def normalize_steam_news_item(news_item: Dict, app_id: int) -> Optional[Dict]:
    """
    Normalize Steam news item to raw event format.
    """
    try:
        # Extract fields from Steam news format
        # Format varies, but typically has: gid, title, url, author, contents, date, feedlabel
        external_id = str(news_item.get("gid", news_item.get("id", "")))
        if not external_id:
            return None
        
        title = news_item.get("title", "")
        url = news_item.get("url", f"https://store.steampowered.com/news/app/{app_id}")
        
        # Extract body/contents
        body = news_item.get("contents", "")
        if not body and news_item.get("body"):
            body = news_item.get("body")
        
        # Parse published date
        published_at = None
        date_value = news_item.get("date", news_item.get("published_at"))
        if date_value:
            try:
                if isinstance(date_value, int):
                    # Unix timestamp
                    published_at = datetime.fromtimestamp(date_value)
                elif isinstance(date_value, str):
                    # Try parsing ISO format or other formats
                    try:
                        # Try ISO format first
                        published_at = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                    except:
                        try:
                            # Try common formats
                            from dateutil import parser
                            published_at = parser.parse(date_value)
                        except:
                            published_at = None
            except:
                pass
        
        # Metrics (views, comments if available)
        metrics = {}
        if news_item.get("comment_count"):
            metrics["comments"] = news_item.get("comment_count")
        if news_item.get("views"):
            metrics["views"] = news_item.get("views")
        
        return {
            "source": "steam_news",
            "external_id": external_id,
            "url": url,
            "title": title,
            "body": body[:1000] if body else None,  # Limit body length
            "metrics_json": metrics if metrics else None,
            "published_at": published_at
        }
    
    except Exception as e:
        logger.warning(f"normalize_steam_news_error app_id={app_id} error={e}")
        return None


def collect_steam_news_for_apps(
    db: Session,
    app_ids: Optional[List[int]] = None,
    max_news_per_app: int = 10,
    days_back: int = 7
) -> Dict[str, int]:
    """
    Collect Steam news for seed apps.
    Saves events to trends_raw_events.
    
    Returns: {events_collected, events_inserted, errors}
    """
    logger.info("collect_steam_news_start")
    
    try:
        # Get seed apps
        if app_ids:
            query = """
                SELECT DISTINCT steam_app_id
                FROM trends_seed_apps
                WHERE is_active = true
                  AND steam_app_id = ANY(:app_ids)
            """
            params = {"app_ids": app_ids}
        else:
            query = """
                SELECT DISTINCT steam_app_id
                FROM trends_seed_apps
                WHERE is_active = true
                LIMIT 100
            """
            params = {}
        
        seed_apps = db.execute(text(query), params).scalars().all()
        
        events_collected = 0
        events_inserted = 0
        errors = 0
        
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for app_id in seed_apps:
            try:
                # Fetch news
                news_items = fetch_steam_news(app_id, max_news_per_app)
                events_collected += len(news_items)
                
                for news_item in news_items:
                    normalized = normalize_steam_news_item(news_item, app_id)
                    if not normalized:
                        continue
                    
                    # Filter by date
                    if normalized.get("published_at"):
                        if normalized["published_at"] < cutoff_date:
                            continue
                    
                    # Check if already exists
                    existing = db.execute(
                        text("""
                            SELECT id FROM trends_raw_events
                            WHERE source = 'steam_news'
                              AND external_id = :external_id
                        """),
                        {"external_id": normalized["external_id"]}
                    ).scalar_one_or_none()
                    
                    if existing:
                        continue
                    
                    # Insert event
                    db.execute(
                        text("""
                            INSERT INTO trends_raw_events 
                                (source, external_id, url, title, body, metrics_json, published_at, captured_at)
                            VALUES 
                                (:source, :external_id, :url, :title, :body, :metrics_json, :published_at, :captured_at)
                        """),
                        {
                            "source": normalized["source"],
                            "external_id": normalized["external_id"],
                            "url": normalized["url"],
                            "title": normalized.get("title"),
                            "body": normalized.get("body"),
                            "metrics_json": json.dumps(normalized.get("metrics_json")) if normalized.get("metrics_json") else None,
                            "published_at": normalized.get("published_at"),
                            "captured_at": datetime.now()
                        }
                    )
                    events_inserted += 1
            
            except Exception as e:
                logger.warning(f"collect_steam_news_error app_id={app_id} error={e}")
                errors += 1
                continue
        
        db.commit()
        
        stats = {
            "events_collected": events_collected,
            "events_inserted": events_inserted,
            "errors": errors,
            "apps_processed": len(seed_apps)
        }
        
        logger.info(f"collect_steam_news_done {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"collect_steam_news_fail error={e}", exc_info=True)
        db.rollback()
        return {"events_collected": 0, "events_inserted": 0, "errors": 1, "apps_processed": 0}


if __name__ == "__main__":
    from apps.db.session import get_db_session
    
    db = get_db_session()
    try:
        stats = collect_steam_news_for_apps(db, max_news_per_app=5, days_back=7)
        print(f"Collected Steam news: {stats}")
    finally:
        db.close()
