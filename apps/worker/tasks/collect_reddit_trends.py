from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_youtube import RedditTrendPost
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

QUERY_SETS = {
    'indie_radar': ["indie game", "upcoming indie", "indie game recommendation"],
    'genre_radar': ["cozy game", "roguelike", "survival game"],
}

@celery_app.task(name="collect_reddit_trends")
def collect_reddit_trends_task(query_set='indie_radar', max_per_query=50):
    db = get_db_session()
    history_id = None
    try:
        result = db.execute(text("""
            INSERT INTO trend_collection_history (source, query_set, status, started_at)
            VALUES ('reddit', :query_set, 'running', NOW())
            RETURNING id
        """), {'query_set': query_set})
        history_id = result.fetchone()[0]
        db.commit()
        
        from apps.worker.integrations.reddit_scraper import RedditScraper
        scraper = RedditScraper()
        
        queries = QUERY_SETS.get(query_set, QUERY_SETS['indie_radar'])
        total = 0
        
        for query in queries:
            posts = scraper.search_posts(query, limit=max_per_query)
            
            for post_data in posts:
                # ИСПРАВЛЕНИЕ: Проверить существует ли пост
                existing = db.query(RedditTrendPost).filter_by(post_id=post_data['post_id']).first()
                
                if existing:
                    # Обновить query/query_set если нужно
                    existing.query = query
                    existing.query_set = query_set
                else:
                    # Создать новый
                    post = RedditTrendPost(
                        post_id=post_data['post_id'],
                        title=post_data['title'],
                        url=post_data['url'],
                        subreddit=post_data['subreddit'],
                        author=post_data['author'],
                        score=post_data['score'],
                        num_comments=post_data['num_comments'],
                        upvote_ratio=post_data['upvote_ratio'],
                        text=post_data['text'],
                        query=query,
                        query_set=query_set
                    )
                    db.add(post)
            
            db.commit()
            total += len(posts)
            logger.info(f"Collected {len(posts)} Reddit posts for '{query}'")
        
        db.execute(text("""
            UPDATE trend_collection_history 
            SET status = 'completed', items_collected = :count, completed_at = NOW()
            WHERE id = :id
        """), {'id': history_id, 'count': total})
        db.commit()
        
        logger.info(f"✅ Successfully collected {total} Reddit posts")
        return {"status": "success", "posts": total}
        
    except Exception as e:
        logger.error(f"Reddit collection error: {e}", exc_info=True)
        if history_id:
            db.execute(text("""
                UPDATE trend_collection_history 
                SET status = 'failed', completed_at = NOW(), error_message = :error
                WHERE id = :id
            """), {'id': history_id, 'error': str(e)[:500]})
            db.commit()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
