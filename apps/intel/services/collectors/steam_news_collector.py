"""
Steam News Collector for Intel module.
Collects news from Steam News API for specific games.
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

from apps.intel.db.models import IntelSource
from apps.intel.services.collectors.base_collector import BaseIntelCollector

logger = logging.getLogger(__name__)


class SteamNewsCollector(BaseIntelCollector):
    """Collector for Steam news."""
    
    STEAM_NEWS_API = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    
    def collect(self, db: Session, source: IntelSource) -> Dict[str, int]:
        """
        Collect Steam news for games.
        Source URL should be in format: steam://app/{steam_appid}
        Or source.name should contain steam_appid.
        Returns: {collected: int, saved: int, errors: int}
        """
        if source.type != "steam":
            logger.warning(f"SteamNewsCollector called for non-Steam source: {source.type}")
            return {"collected": 0, "saved": 0, "errors": 1}
        
        # Extract steam_appid from source
        steam_appid = self._extract_steam_appid(source)
        if not steam_appid:
            logger.error(f"Cannot extract steam_appid from source: {source.url}")
            return {"collected": 0, "saved": 0, "errors": 1}
        
        collected = 0
        saved = 0
        errors = 0
        
        try:
            # Fetch Steam news
            logger.info(f"Collecting Steam news for app {steam_appid}")
            url = f"{self.STEAM_NEWS_API}?appid={steam_appid}&count=50&maxlength=500"
            
            response = self.fetch_url(url)
            data = response.json()
            
            if "appnews" not in data or "newsitems" not in data["appnews"]:
                logger.warning(f"No news items in Steam API response for app {steam_appid}")
                return {"collected": 0, "saved": 0, "errors": 0}
            
            news_items = data["appnews"]["newsitems"]
            
            # Process news items
            for item in news_items:
                collected += 1
                
                try:
                    # Extract data
                    url = item.get("url", "").strip()
                    if not url:
                        logger.warning(f"Steam news item missing URL, skipping")
                        continue
                    
                    title = item.get("title", "").strip() or "Untitled"
                    contents = item.get("contents", "").strip()
                    
                    # Get published date
                    published_at = None
                    if "date" in item:
                        try:
                            published_at = datetime.fromtimestamp(item["date"])
                        except:
                            pass
                    
                    # Prepare raw payload
                    raw_payload = {
                        "steam_appid": steam_appid,
                        "gid": item.get("gid", ""),
                        "author": item.get("author", ""),
                        "date": item.get("date"),
                        "feedlabel": item.get("feedlabel", ""),
                        "feedname": item.get("feedname", ""),
                        "feed_type": item.get("feed_type", 0)
                    }
                    
                    # Save to database
                    raw_item = self.save_raw_item(
                        db=db,
                        source=source,
                        url=url,
                        title=title,
                        snippet=contents[:500] if contents else None,  # First 500 chars as snippet
                        raw_payload=raw_payload
                    )
                    
                    if raw_item:
                        saved += 1
                    
                except Exception as e:
                    errors += 1
                    logger.error(f"Error processing Steam news item: {e}", exc_info=True)
            
            logger.info(f"Steam news collection complete: app {steam_appid} - collected={collected}, saved={saved}, errors={errors}")
            return {"collected": collected, "saved": saved, "errors": errors}
            
        except Exception as e:
            logger.error(f"Steam news collection failed for app {steam_appid}: {e}", exc_info=True)
            return {"collected": collected, "saved": saved, "errors": errors + 1}
    
    def _extract_steam_appid(self, source: IntelSource) -> Optional[int]:
        """
        Extract steam_appid from source URL or name.
        Supports formats:
        - steam://app/{appid}
        - https://store.steampowered.com/app/{appid}/
        - Source name containing appid
        """
        import re
        
        # Try URL first
        url = source.url
        if url.startswith("steam://app/"):
            match = re.search(r'steam://app/(\d+)', url)
            if match:
                return int(match.group(1))
        
        # Try store URL
        match = re.search(r'/app/(\d+)', url)
        if match:
            return int(match.group(1))
        
        # Try extracting from name
        match = re.search(r'(\d+)', source.name)
        if match:
            return int(match.group(1))
        
        return None
    
    def collect_for_apps(
        self,
        db: Session,
        app_ids: Optional[List[int]] = None,
        limit: int = 100
    ) -> Dict[str, int]:
        """
        Collect Steam news for multiple apps.
        If app_ids is None, gets apps from steam_app_cache.
        Returns: {collected: int, saved: int, errors: int}
        """
        # Get or create Steam source
        from apps.intel.db.models import IntelSource
        from sqlalchemy import text
        
        steam_source = db.query(IntelSource).filter(
            IntelSource.type == "steam",
            IntelSource.url.like("steam://app/%")
        ).first()
        
        if not steam_source:
            # Create default Steam source
            steam_source = IntelSource(
                type="steam",
                name="Steam News (Auto)",
                url="steam://app/0",  # Placeholder, will be replaced per app
                is_enabled=True
            )
            db.add(steam_source)
            db.commit()
            db.refresh(steam_source)
        
        # Get app IDs
        if app_ids is None:
            query = text("""
                SELECT DISTINCT steam_app_id
                FROM steam_app_cache
                WHERE steam_app_id IS NOT NULL
                ORDER BY COALESCE(reviews_total, 0) DESC
                LIMIT :limit
            """)
            rows = db.execute(query, {"limit": limit}).mappings().all()
            app_ids = [int(row["steam_app_id"]) for row in rows]
        
        total_collected = 0
        total_saved = 0
        total_errors = 0
        
        # Collect for each app
        for app_id in app_ids:
            # Create temporary source object for this app (not saved to DB)
            class TempSource:
                def __init__(self, base_source, app_id):
                    self.id = base_source.id
                    self.type = "steam"
                    self.name = f"Steam News - App {app_id}"
                    self.url = f"steam://app/{app_id}"
                    self.is_enabled = True
            
            temp_source = TempSource(steam_source, app_id)
            
            result = self.collect(db, temp_source)
            total_collected += result["collected"]
            total_saved += result["saved"]
            total_errors += result["errors"]
        
        return {
            "collected": total_collected,
            "saved": total_saved,
            "errors": total_errors
        }


# Global instance
steam_news_collector = SteamNewsCollector()
