"""
RSS Collector for Intel module.
Collects items from RSS feeds.
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from urllib.parse import urlparse
import feedparser

from apps.intel.db.models import IntelSource
from apps.intel.services.collectors.base_collector import BaseIntelCollector

logger = logging.getLogger(__name__)


class RSSCollector(BaseIntelCollector):
    """Collector for RSS feeds."""
    
    def collect(self, db: Session, source: IntelSource) -> Dict[str, int]:
        """
        Collect items from RSS feed.
        Returns: {collected: int, saved: int, errors: int}
        """
        if source.type != "rss":
            logger.warning(f"RSSCollector called for non-RSS source: {source.type}")
            return {"collected": 0, "saved": 0, "errors": 1}
        
        collected = 0
        saved = 0
        errors = 0
        
        try:
            # Fetch RSS feed
            logger.info(f"Collecting RSS feed: {source.url}")
            response = self.fetch_url(source.url)
            
            # Parse RSS
            feed = feedparser.parse(response.text)
            
            if feed.bozo and feed.bozo_exception:
                logger.error(f"RSS parse error for {source.url}: {feed.bozo_exception}")
                return {"collected": 0, "saved": 0, "errors": 1}
            
            # Process entries
            for entry in feed.entries:
                collected += 1
                
                try:
                    # Extract data
                    url = entry.get("link", "").strip()
                    if not url:
                        logger.warning(f"RSS entry missing link, skipping")
                        continue
                    
                    title = entry.get("title", "").strip() or "Untitled"
                    
                    # Get snippet/description
                    snippet = None
                    if hasattr(entry, "summary"):
                        snippet = entry.get("summary", "").strip()
                    elif hasattr(entry, "description"):
                        snippet = entry.get("description", "").strip()
                    
                    # Get published date if available
                    published_at = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published_at = datetime(*entry.published_parsed[:6])
                        except:
                            pass
                    
                    # Prepare raw payload
                    raw_payload = {
                        "feed_title": feed.feed.get("title", ""),
                        "feed_link": feed.feed.get("link", ""),
                        "entry_id": entry.get("id", ""),
                        "published": entry.get("published", ""),
                        "published_parsed": entry.published_parsed if hasattr(entry, "published_parsed") else None,
                        "authors": [a.get("name", "") for a in entry.get("authors", [])],
                        "tags": [t.get("term", "") for t in entry.get("tags", [])]
                    }
                    
                    # Save to database
                    raw_item = self.save_raw_item(
                        db=db,
                        source=source,
                        url=url,
                        title=title,
                        snippet=snippet,
                        raw_payload=raw_payload
                    )
                    
                    if raw_item:
                        saved += 1
                    
                except Exception as e:
                    errors += 1
                    logger.error(f"Error processing RSS entry: {e}", exc_info=True)
            
            logger.info(f"RSS collection complete: {source.url} - collected={collected}, saved={saved}, errors={errors}")
            return {"collected": collected, "saved": saved, "errors": errors}
            
        except Exception as e:
            logger.error(f"RSS collection failed for {source.url}: {e}", exc_info=True)
            return {"collected": collected, "saved": saved, "errors": errors + 1}


# Global instance
rss_collector = RSSCollector()
