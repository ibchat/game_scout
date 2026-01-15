from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_youtube import TwitterTrendTweet
import logging
import os

logger = logging.getLogger(__name__)

QUERY_SETS = {
    'indie_radar': ["indie game", "indie game trailer", "wishlist indie"],
}

@celery_app.task(name="collect_twitter_trends")
def collect_twitter_trends_task(query_set='indie_radar', max_per_query=25):
    db = get_db_session()
    try:
        bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        
        from apps.worker.integrations.twitter_client import TwitterClient
        client = TwitterClient(bearer_token)
        
        queries = QUERY_SETS.get(query_set, QUERY_SETS['indie_radar'])
        total = 0
        
        for query in queries:
            tweets = client.search_tweets(query, max_per_query)
            
            for tweet_data in tweets:
                tweet = TwitterTrendTweet(
                    tweet_id=tweet_data['tweet_id'],
                    text=tweet_data['text'],
                    url=tweet_data['url'],
                    username=tweet_data['username'],
                    likes=tweet_data['likes'],
                    retweets=tweet_data['retweets'],
                    replies=tweet_data['replies'],
                    query=query,
                    query_set=query_set
                )
                db.merge(tweet)
            
            db.commit()
            total += len(tweets)
            logger.info(f"Collected {len(tweets)} tweets for '{query}'")
        
        mode = "real" if bearer_token else "mock"
        return {"status": "success", "tweets": total, "mode": mode}
        
    except Exception as e:
        logger.error(f"Twitter collection error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
