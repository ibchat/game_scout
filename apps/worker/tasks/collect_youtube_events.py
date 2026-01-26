"""
Collect YouTube videos as raw events in trends_raw_events.
This is the proper pipeline: Collect → Events → Matching → Signals.
"""
import logging
import os
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session

logger = logging.getLogger(__name__)

QUERY_SETS = {
    'indie_radar': ["indie game trailer", "indie game demo", "upcoming indie game"],
    'genre_radar': ["cozy game", "roguelike game", "survival game"],
    'mechanic_radar': ["deckbuilder game", "automation game", "extraction shooter"]
}


@celery_app.task(name="apps.worker.tasks.collect_youtube_events.collect_youtube_events_task")
def collect_youtube_events_task(query_set='indie_radar', max_per_query=25):
    """
    Collect YouTube videos and save them as raw events in trends_raw_events.
    Events are NOT matched here - matching happens separately via entity_matcher.
    """
    db = get_db_session()
    events_collected = 0
    
    try:
        api_key = os.getenv('YOUTUBE_API_KEY')
        if not api_key:
            logger.warning("YOUTUBE_API_KEY not set, skipping YouTube collection")
            return {"status": "error", "error": "YOUTUBE_API_KEY not configured"}
        
        from apps.worker.integrations.youtube_client import YouTubeClient
        client = YouTubeClient(api_key)
        
        queries = QUERY_SETS.get(query_set, QUERY_SETS['indie_radar'])
        
        for query in queries:
            videos = client.search_videos(query, max_results=max_per_query)
            
            for video_data in videos:
                # Check if event already exists
                existing = db.execute(
                    text("""
                        SELECT id FROM trends_raw_events
                        WHERE source = 'youtube' AND external_id = :external_id
                    """),
                    {"external_id": video_data.get('video_id')}
                ).scalar()
                
                if existing:
                    continue  # Skip duplicates
                
                # Parse published_at
                published_at = datetime.now()
                if 'published_at' in video_data:
                    try:
                        published_at = datetime.fromisoformat(video_data['published_at'].replace('Z', '+00:00'))
                    except:
                        try:
                            from dateutil import parser
                            published_at = parser.parse(video_data['published_at'])
                        except:
                            pass
                
                # Prepare metrics JSON
                metrics = {
                    "view_count": video_data.get('view_count', 0),
                    "like_count": video_data.get('like_count', 0),
                    "comment_count": video_data.get('comment_count', 0),
                    "channel_id": video_data.get('channel_id', ''),
                    "channel_title": video_data.get('channel_title', ''),
                    "duration": video_data.get('duration', '')
                }
                
                # Insert as raw event (NOT matched yet)
                db.execute(
                    text("""
                        INSERT INTO trends_raw_events
                        (source, external_id, url, title, body, metrics_json, published_at, captured_at, matched_steam_app_id, match_confidence, match_reason)
                        VALUES
                        ('youtube', :external_id, :url, :title, :description, :metrics_json, :published_at, NOW(), NULL, NULL, NULL)
                    """),
                    {
                        "external_id": video_data.get('video_id', ''),
                        "url": video_data.get('url', '')[:500],
                        "title": (video_data.get('title', '') or '')[:1000],
                        "description": (video_data.get('description', '') or '')[:5000],
                        "metrics_json": json.dumps(metrics),
                        "published_at": published_at
                    }
                )
                events_collected += 1
            
            logger.info(f"Collected {len(videos)} YouTube events for query '{query}'")
        
        db.commit()
        logger.info(f"✅ Collected {events_collected} YouTube events total")
        return {"status": "success", "events_collected": events_collected}
        
    except Exception as e:
        logger.error(f"YouTube events collection error: {e}", exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def collect_youtube_events_for_apps(db: Session, app_ids: list = None, max_per_app: int = 10) -> dict:
    """
    Collect YouTube events for specific apps (by searching for game names).
    """
    events_collected = 0
    
    try:
        api_key = os.getenv('YOUTUBE_API_KEY')
        if not api_key:
            return {"status": "error", "error": "YOUTUBE_API_KEY not configured"}
        
        # Get game names for apps
        if app_ids:
            query = text("""
                SELECT steam_app_id, name
                FROM steam_app_cache
                WHERE steam_app_id = ANY(:app_ids) AND name IS NOT NULL
            """)
            games = db.execute(query, {"app_ids": app_ids}).mappings().all()
        else:
            query = text("""
                SELECT DISTINCT s.steam_app_id, c.name
                FROM trends_seed_apps s
                JOIN steam_app_cache c ON c.steam_app_id = s.steam_app_id
                WHERE s.is_active = true AND c.name IS NOT NULL
                LIMIT 50
            """)
            games = db.execute(query).mappings().all()
        
        from apps.worker.integrations.youtube_client import YouTubeClient
        client = YouTubeClient(api_key)
        
        for game in games:
            game_name = game["name"]
            steam_app_id = game["steam_app_id"]
            
            # Search YouTube for this specific game
            videos = client.search_videos(game_name, max_results=max_per_app)
            
            for video_data in videos:
                existing = db.execute(
                    text("""
                        SELECT id FROM trends_raw_events
                        WHERE source = 'youtube' AND external_id = :external_id
                    """),
                    {"external_id": video_data.get('video_id')}
                ).scalar()
                
                if existing:
                    continue
                
                published_at = datetime.now()
                if 'published_at' in video_data:
                    try:
                        published_at = datetime.fromisoformat(video_data['published_at'].replace('Z', '+00:00'))
                    except:
                        try:
                            from dateutil import parser
                            published_at = parser.parse(video_data['published_at'])
                        except:
                            pass
                
                metrics = {
                    "view_count": video_data.get('view_count', 0),
                    "like_count": video_data.get('like_count', 0),
                    "comment_count": video_data.get('comment_count', 0),
                    "channel_id": video_data.get('channel_id', ''),
                    "channel_title": video_data.get('channel_title', ''),
                    "searched_game": game_name
                }
                
                db.execute(
                    text("""
                        INSERT INTO trends_raw_events
                        (source, external_id, url, title, body, metrics_json, published_at, captured_at, matched_steam_app_id, match_confidence, match_reason)
                        VALUES
                        ('youtube', :external_id, :url, :title, :description, :metrics_json, :published_at, NOW(), NULL, NULL, NULL)
                    """),
                    {
                        "external_id": video_data.get('video_id', ''),
                        "url": video_data.get('url', '')[:500],
                        "title": (video_data.get('title', '') or '')[:1000],
                        "description": (video_data.get('description', '') or '')[:5000],
                        "metrics_json": json.dumps(metrics),
                        "published_at": published_at
                    }
                )
                events_collected += 1
        
        db.commit()
        return {"status": "success", "events_collected": events_collected}
        
    except Exception as e:
        logger.error(f"YouTube events collection for apps error: {e}", exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(e)}
