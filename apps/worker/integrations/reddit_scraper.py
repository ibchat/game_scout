import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import time
from typing import List, Dict, Any

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
    
    def get_new_posts(self, subreddits: List[str], days: int = 14, limit_per_sub: int = 25):
        """
        Получить новые посты из сабреддитов за последние N дней.
        Используется для Deal Intent Signals v3.2.
        """
        try:
            posts = []
            cutoff_timestamp = datetime.utcnow().timestamp() - (days * 24 * 60 * 60)
            
            for subreddit in subreddits:
                try:
                    # Используем публичный JSON API Reddit (new/hot)
                    url = f"https://www.reddit.com/r/{subreddit}/new.json"
                    params = {
                        'limit': min(limit_per_sub, 100)
                    }
                    
                    # B2: Backoff на 429 с экспоненциальной паузой
                    response = None
                    max_retries = 3
                    for retry in range(max_retries):
                        response = requests.get(url, headers=self.headers, params=params, timeout=15)
                        
                        if response.status_code == 429:
                            if retry < max_retries - 1:
                                backoff_seconds = [3, 7, 15][retry]
                                logger.warning(f"Reddit /r/{subreddit} returned 429 (rate limited), retrying in {backoff_seconds}s (attempt {retry + 1}/{max_retries})")
                                time.sleep(backoff_seconds)
                                continue
                            else:
                                logger.warning(f"Reddit /r/{subreddit} returned 429 after {max_retries} retries, skipping subreddit")
                                break
                        elif response.status_code != 200:
                            logger.warning(f"Reddit /r/{subreddit} returned {response.status_code}")
                            break
                        else:
                            # Success
                            break
                    
                    if response is None or response.status_code != 200:
                        continue
                    
                    data = response.json()
                    
                    for post_data in data.get('data', {}).get('children', []):
                        post = post_data.get('data', {})
                        created_utc = post.get('created_utc', 0)
                        
                        # Фильтруем по дате
                        if created_utc < cutoff_timestamp:
                            continue
                        
                        # Объединяем title и selftext для анализа
                        full_text = f"{post.get('title', '')} {post.get('selftext', '')}"
                        
                        posts.append({
                            'post_id': post.get('id'),
                            'title': post.get('title', ''),
                            'url': f"https://reddit.com{post.get('permalink', '')}",
                            'subreddit': post.get('subreddit', ''),
                            'author': post.get('author', ''),
                            'score': post.get('score', 0),
                            'num_comments': post.get('num_comments', 0),
                            'upvote_ratio': post.get('upvote_ratio', 0.0),
                            'text': full_text,  # Полный текст для матчинга keywords
                            'created_at': datetime.fromtimestamp(created_utc).isoformat(),
                            'created_utc': created_utc
                        })
                    
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error fetching /r/{subreddit}: {e}", exc_info=True)
                    continue
            
            logger.info(f"Fetched {len(posts)} new Reddit posts from {len(subreddits)} subreddits")
            return posts
            
        except Exception as e:
            logger.error(f"Reddit get_new_posts error: {e}", exc_info=True)
            return []
    
    def get_post_comments(self, permalink_or_post_id: str, subreddit: str = "", limit: int = 20) -> list[dict]:
        """
        Fetch top comments for a reddit post permalink.
        
        Args:
            permalink_or_post_id: Can be:
                - Full URL: "https://reddit.com/r/Steam/comments/xxxxxx/some_title/"
                - Permalink path: "/r/Steam/comments/xxxxxx/some_title/"
                - Post ID (if subreddit provided): "xxxxxx"
            subreddit: Subreddit name (required if permalink_or_post_id is just post_id)
            limit: Maximum comments to return
        
        Returns:
            list[dict] with keys: id, body, permalink, created_utc, score
        """
        try:
            if not permalink_or_post_id:
                return []
            
            # Normalize permalink
            permalink = permalink_or_post_id
            
            # If it's a full URL, extract the path
            if permalink.startswith("http://") or permalink.startswith("https://"):
                # Extract path from URL
                from urllib.parse import urlparse
                parsed = urlparse(permalink)
                permalink = parsed.path
            # If it's just a post_id and we have subreddit, construct permalink
            elif subreddit and not permalink.startswith("/"):
                # Assume it's a post_id, construct permalink
                permalink = f"/r/{subreddit}/comments/{permalink}/"
            # If it's a path without leading slash, add it
            elif not permalink.startswith("/"):
                permalink = "/" + permalink
            
            # Ensure permalink ends with / for Reddit API
            if not permalink.endswith("/"):
                permalink = permalink + "/"

            url = f"https://www.reddit.com{permalink}.json?raw_json=1"

            # Используем тот же паттерн что и в других методах класса
            response = requests.get(url, headers=self.headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Reddit comments for {permalink} returned {response.status_code}")
                return []
            
            data = response.json()
            
            if not data or not isinstance(data, list) or len(data) < 2:
                return []

            comments_listing = data[1]
            if not isinstance(comments_listing, dict):
                return []

            children = (comments_listing.get("data", {}) or {}).get("children", []) or []
            if not isinstance(children, list):
                return []

            out: list[dict] = []
            for ch in children:
                if not isinstance(ch, dict):
                    continue
                if ch.get("kind") != "t1":
                    continue
                cd = ch.get("data", {}) or {}
                if not isinstance(cd, dict):
                    continue

                body = (cd.get("body") or "").strip()
                if not body:
                    continue

                # Build full permalink URL if relative
                comment_permalink = cd.get("permalink", "")
                if comment_permalink and not comment_permalink.startswith("http"):
                    comment_permalink = f"https://reddit.com{comment_permalink}"
                
                # Return both formats for compatibility: body/permalink (TZ contract) and text/url (task usage)
                out.append(
                    {
                        "id": cd.get("id"),
                        "body": body,  # TZ contract
                        "text": body,  # Task compatibility
                        "permalink": comment_permalink,  # TZ contract
                        "url": comment_permalink,  # Task compatibility
                        "created_utc": cd.get("created_utc"),
                        "created_at": datetime.fromtimestamp(cd.get("created_utc", 0)).isoformat() if cd.get("created_utc") else None,  # Task compatibility
                        "score": cd.get("score", 0),
                    }
                )
                if len(out) >= limit:
                    break

            time.sleep(1)  # Rate limiting (как в других методах)
            return out
        except Exception as e:
            logger.error(f"Error fetching comments for permalink {permalink}: {e}", exc_info=True)
            return []
