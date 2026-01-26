from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
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
            
            # Используем raw SQL для избежания проблем с моделями SQLAlchemy
            for post_data in posts:
                # Проверить существует ли пост через raw SQL
                existing = db.execute(
                    text("SELECT id FROM reddit_trend_posts WHERE post_id = :post_id"),
                    {"post_id": post_data['post_id']}
                ).scalar()
                
                if existing:
                    # Обновить query/query_set если нужно
                    db.execute(
                        text("""
                            UPDATE reddit_trend_posts 
                            SET query = :query, query_set = :query_set
                            WHERE post_id = :post_id
                        """),
                        {
                            "post_id": post_data['post_id'],
                            "query": query,
                            "query_set": query_set
                        }
                    )
                else:
                    # Создать новый через raw SQL
                    db.execute(
                        text("""
                            INSERT INTO reddit_trend_posts 
                            (post_id, title, url, subreddit, author, score, num_comments, upvote_ratio, text, query, query_set, collected_at)
                            VALUES 
                            (:post_id, :title, :url, :subreddit, :author, :score, :num_comments, :upvote_ratio, :text, :query, :query_set, NOW())
                        """),
                        {
                            "post_id": post_data['post_id'],
                            "title": post_data.get('title', '')[:1000],
                            "url": post_data.get('url', '')[:500],
                            "subreddit": post_data.get('subreddit', '')[:100],
                            "author": post_data.get('author', '')[:200],
                            "score": post_data.get('score', 0),
                            "num_comments": post_data.get('num_comments', 0),
                            "upvote_ratio": post_data.get('upvote_ratio', 0.0),
                            "text": (post_data.get('text', '') or '')[:5000],
                            "query": query,
                            "query_set": query_set
                        }
                    )
            
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
