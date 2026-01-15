import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class RedditScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def search_posts(self, query, subreddits=['IndieGaming', 'Games', 'gaming', 'pcgaming', 'truegaming'], limit=100):
        """Глубокий парсинг Reddit - до 100 постов"""
        try:
            posts = []
            
            for subreddit in subreddits:
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    'q': query,
                    'sort': 'hot',
                    'limit': min(limit, 100),  # Увеличен лимит
                    't': 'week',  # За неделю для трендов
                    'restrict_sr': 'on'
                }
                
                response = requests.get(url, headers=self.headers, params=params, timeout=15)
                
                if response.status_code != 200:
                    logger.warning(f"Reddit returned {response.status_code}")
                    continue
                
                data = response.json()
                
                for post_data in data.get('data', {}).get('children', []):
                    post = post_data.get('data', {})
                    
                    posts.append({
                        'post_id': post.get('id'),
                        'title': post.get('title'),
                        'url': f"https://reddit.com{post.get('permalink')}",
                        'subreddit': post.get('subreddit'),
                        'author': post.get('author'),
                        'score': post.get('score', 0),
                        'num_comments': post.get('num_comments', 0),
                        'upvote_ratio': post.get('upvote_ratio', 0.0),
                        'text': post.get('selftext', '')[:500],
                        'created_at': datetime.fromtimestamp(post.get('created_utc', 0)).isoformat()
                    })
                    
                    if len(posts) >= limit:
                        break
                
                time.sleep(2)
                
                if len(posts) >= limit:
                    break
            
            logger.info(f"Deep scraped {len(posts)} Reddit posts for '{query}'")
            return posts
            
        except Exception as e:
            logger.error(f"Reddit scraping error: {e}", exc_info=True)
            return []
