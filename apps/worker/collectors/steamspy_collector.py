import requests
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class SteamSpyCollector:
    """Collect detailed metrics from SteamSpy API"""
    BASE_URL = "https://steamspy.com/api.php"
    
    def get_game_details(self, appid: str) -> Optional[Dict]:
        """Get detailed metrics for a specific Steam game"""
        try:
            params = {
                "request": "appdetails",
                "appid": appid
            }
            
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data or 'name' not in data:
                return None
            
            # Parse owners range
            owners_str = data.get("owners", "")
            owners_min, owners_max = None, None
            if ".." in owners_str:
                parts = owners_str.split("..")
                owners_min = int(parts[0].strip().replace(",", ""))
                owners_max = int(parts[1].strip().replace(",", ""))
            
            return {
                "reviews_total": data.get("positive", 0) + data.get("negative", 0),
                "positive_reviews": data.get("positive", 0),
                "negative_reviews": data.get("negative", 0),
                "owners_min": owners_min,
                "owners_max": owners_max,
                "average_playtime_forever": data.get("average_forever", 0),
                "average_playtime_2weeks": data.get("average_2weeks", 0),
                "median_playtime_forever": data.get("median_forever", 0),
                "ccu": data.get("ccu", 0),
                "tags": data.get("tags", {})
            }
            
        except Exception as e:
            logger.warning(f"SteamSpy failed for {appid}: {e}")
            return None

steamspy_collector = SteamSpyCollector()
