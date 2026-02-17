"""
Reddit RSS Collector for Intel module.
Collects posts from Reddit subreddits via RSS feeds.
"""
import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session
from urllib.parse import urlparse, urlunparse

from apps.intel.db.models import IntelSource
from apps.intel.services.collectors.rss_collector import RSSCollector

logger = logging.getLogger(__name__)


class RedditRSSCollector(RSSCollector):
    """Collector for Reddit RSS feeds."""
    
    REDDIT_RSS_BASE = "https://www.reddit.com"
    
    def collect(self, source: IntelSource) -> Dict[str, int]:
        """
        Collect items from Reddit RSS feed.
        Source URL can be:
        - Direct RSS URL: https://www.reddit.com/r/{subreddit}/.rss
        - Subreddit URL: https://www.reddit.com/r/{subreddit}/
        - Subreddit name: r/{subreddit}
        Returns: {collected: int, saved: int, errors: int}
        """
        if source.type != "reddit_rss":
            logger.warning(f"RedditRSSCollector called for non-Reddit source: {source.type}")
            return {"collected": 0, "saved": 0, "errors": 1}
        
        # Normalize Reddit URL to RSS format
        rss_url = self._normalize_reddit_url(source.url)
        if not rss_url:
            logger.error(f"Cannot normalize Reddit URL: {source.url}")
            return {"collected": 0, "saved": 0, "errors": 1}
        
        # Temporarily update source URL for RSS collection
        original_url = source.url
        source.url = rss_url
        
        try:
            # Use parent RSS collector
            result = super().collect(source)
            return result
        finally:
            # Restore original URL
            source.url = original_url
    
    def _normalize_reddit_url(self, url: str) -> Optional[str]:
        """
        Normalize Reddit URL to RSS format.
        Examples:
        - r/gamedev -> https://www.reddit.com/r/gamedev/.rss
        - https://www.reddit.com/r/gamedev/ -> https://www.reddit.com/r/gamedev/.rss
        - https://www.reddit.com/r/gamedev/.rss -> https://www.reddit.com/r/gamedev/.rss
        """
        url = url.strip()
        
        # Already RSS format
        if url.endswith(".rss"):
            return url
        
        # Extract subreddit name
        import re
        
        # Pattern: r/{subreddit} or /r/{subreddit}
        match = re.search(r'/r/([^/\s]+)', url)
        if match:
            subreddit = match.group(1)
        elif url.startswith("r/"):
            subreddit = url[2:].split("/")[0].split("?")[0]
        else:
            # Try to extract from any URL
            parts = url.split("/")
            for i, part in enumerate(parts):
                if part == "r" and i + 1 < len(parts):
                    subreddit = parts[i + 1].split("?")[0]
                    break
            else:
                logger.warning(f"Cannot extract subreddit from URL: {url}")
                return None
        
        # Build RSS URL
        rss_url = f"{self.REDDIT_RSS_BASE}/r/{subreddit}/.rss"
        return rss_url


# Global instance
