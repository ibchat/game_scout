"""
Collect Reddit posts as raw events in trends_raw_events.
This is the proper pipeline: Collect → Events → Matching → Signals.
"""
import logging
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session

logger = logging.getLogger(__name__)

QUERY_SETS = {
    'indie_radar': ["indie game", "upcoming indie", "indie game recommendation"],
    'genre_radar': ["cozy game", "roguelike", "survival game"],
}


@celery_app.task(name="apps.worker.tasks.collect_reddit_events.collect_reddit_events_task")
def collect_reddit_events_task(query_set='indie_radar', max_per_query=50):
    """
    Collect Reddit posts and save them as raw events in trends_raw_events.
    Events are NOT matched here - matching happens separately via entity_matcher.
    """
    db = get_db_session()
    events_collected = 0
    
    try:
        from apps.worker.integrations.reddit_scraper import RedditScraper
        scraper = RedditScraper()
        
        queries = QUERY_SETS.get(query_set, QUERY_SETS['indie_radar'])
        
        for query in queries:
            posts = scraper.search_posts(query, limit=max_per_query)
            
            for post_data in posts:
                # Check if event already exists
                existing = db.execute(
                    text("""
                        SELECT id FROM trends_raw_events
                        WHERE source = 'reddit' AND external_id = :external_id
                    """),
                    {"external_id": post_data['post_id']}
                ).scalar()
                
                if existing:
                    continue  # Skip duplicates
                
                # Parse published_at from Reddit data (if available)
                # Reddit API doesn't always provide created_utc, so we use current time as fallback
                published_at = datetime.now()
                if 'created_utc' in post_data:
                    try:
                        published_at = datetime.fromtimestamp(post_data['created_utc'])
                    except:
                        pass
                
                # Prepare metrics JSON
                metrics = {
                    "score": post_data.get('score', 0),
                    "num_comments": post_data.get('num_comments', 0),
                    "upvote_ratio": post_data.get('upvote_ratio', 0.0),
                    "subreddit": post_data.get('subreddit', ''),
                    "author": post_data.get('author', '')
                }
                
                # Insert as raw event (NOT matched yet)
                db.execute(
                    text("""
                        INSERT INTO trends_raw_events
                        (source, external_id, url, title, body, metrics_json, published_at, captured_at, matched_steam_app_id, match_confidence, match_reason)
                        VALUES
                        ('reddit', :external_id, :url, :title, :body, :metrics_json, :published_at, NOW(), NULL, NULL, NULL)
                    """),
                    {
                        "external_id": post_data['post_id'],
                        "url": post_data.get('url', '')[:500],
                        "title": (post_data.get('title', '') or '')[:1000],
                        "body": (post_data.get('text', '') or '')[:5000],
                        "metrics_json": json.dumps(metrics),
                        "published_at": published_at
                    }
                )
                events_collected += 1
            
            logger.info(f"Collected {len(posts)} Reddit events for query '{query}'")
        
        db.commit()
        logger.info(f"✅ Collected {events_collected} Reddit events total")
        return {"status": "success", "events_collected": events_collected}
        
    except Exception as e:
        logger.error(f"Reddit events collection error: {e}", exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def collect_reddit_events_for_apps(db: Session, app_ids: list = None, max_per_app: int = 10) -> dict:
    """
    Collect Reddit events for specific apps (by searching for game names).
    This is an alternative approach: search by game name instead of generic queries.
    """
    events_collected = 0
    
    try:
        # Get game names for apps
        if app_ids:
            query = text("""
                SELECT steam_app_id, name
                FROM steam_app_cache
                WHERE steam_app_id = ANY(:app_ids) AND name IS NOT NULL
            """)
            games = db.execute(query, {"app_ids": app_ids}).mappings().all()
        else:
            # Get all active seed apps
            query = text("""
                SELECT DISTINCT s.steam_app_id, c.name
                FROM trends_seed_apps s
                JOIN steam_app_cache c ON c.steam_app_id = s.steam_app_id
                WHERE s.is_active = true AND c.name IS NOT NULL
                LIMIT 50
            """)
            games = db.execute(query).mappings().all()
        
        from apps.worker.integrations.reddit_scraper import RedditScraper
        scraper = RedditScraper()
        
        for game in games:
            game_name = game["name"]
            steam_app_id = game["steam_app_id"]
            
            # Search Reddit for this specific game
            posts = scraper.search_posts(game_name, limit=max_per_app)
            
            for post_data in posts:
                # Check if already exists
                existing = db.execute(
                    text("""
                        SELECT id FROM trends_raw_events
                        WHERE source = 'reddit' AND external_id = :external_id
                    """),
                    {"external_id": post_data['post_id']}
                ).scalar()
                
                if existing:
                    continue
                
                published_at = datetime.now()
                if 'created_utc' in post_data:
                    try:
                        published_at = datetime.fromtimestamp(post_data['created_utc'])
                    except:
                        pass
                
                metrics = {
                    "score": post_data.get('score', 0),
                    "num_comments": post_data.get('num_comments', 0),
                    "upvote_ratio": post_data.get('upvote_ratio', 0.0),
                    "subreddit": post_data.get('subreddit', ''),
                    "author": post_data.get('author', ''),
                    "searched_game": game_name
                }
                
                db.execute(
                    text("""
                        INSERT INTO trends_raw_events
                        (source, external_id, url, title, body, metrics_json, published_at, captured_at, matched_steam_app_id, match_confidence, match_reason)
                        VALUES
                        ('reddit', :external_id, :url, :title, :body, :metrics_json, :published_at, NOW(), NULL, NULL, NULL)
                    """),
                    {
                        "external_id": post_data['post_id'],
                        "url": post_data.get('url', '')[:500],
                        "title": (post_data.get('title', '') or '')[:1000],
                        "body": (post_data.get('text', '') or '')[:5000],
                        "metrics_json": json.dumps(metrics),
                        "published_at": published_at
                    }
                )
                events_collected += 1
        
        db.commit()
        return {"status": "success", "events_collected": events_collected}
        
    except Exception as e:
        logger.error(f"Reddit events collection for apps error: {e}", exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(e)}
