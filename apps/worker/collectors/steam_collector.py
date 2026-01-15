from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging
import re
from datetime import datetime
import time
from apps.worker.collectors.http_client import http_client

logger = logging.getLogger(__name__)

class SteamDeepCollector:
    BASE_URL = "https://store.steampowered.com"
    CATEGORIES = {
        "topsellers": "filter=topsellers",
        "new_trending": "filter=popularnew",
        "top_rated": "filter=toprated",
    }
    
    def collect_comprehensive(self, games_per_category: int = 50) -> List[Dict]:
        all_games = []
        for cat_name, cat_param in self.CATEGORIES.items():
            logger.info(f"Collecting: {cat_name}")
            try:
                games = self._collect_category(cat_name, cat_param, games_per_category)
                all_games.extend(games)
                time.sleep(2)
            except Exception as e:
                logger.error(f"Failed {cat_name}: {e}")
        logger.info(f"Collected {len(all_games)} games")
        return all_games
    
    def _collect_category(self, cat_name: str, cat_param: str, limit: int) -> List[Dict]:
        games = []
        url = f"{self.BASE_URL}/search/?{cat_param}&ndl=1"
        try:
            response = http_client.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            results = soup.find_all('a', class_='search_result_row', limit=limit)
            
            for idx, result in enumerate(results):
                try:
                    game = self._parse_game_card(result, idx, cat_name)
                    if game:
                        games.append(game)
                except Exception as e:
                    logger.warning(f"Parse error: {e}")
            logger.info(f"{cat_name}: {len(games)} games")
        except Exception as e:
            logger.error(f"Error: {e}")
        return games
    
    def _parse_game_card(self, card, rank: int, category: str) -> Optional[Dict]:
        try:
            href = card.get('href', '')
            match = re.search(r'/app/(\d+)', href)
            if not match:
                return None
            
            app_id = match.group(1)
            name_elem = card.find('span', class_='title')
            name = name_elem.text.strip() if name_elem else f"App {app_id}"
            
            price = None
            price_elem = card.find('div', class_='discount_final_price') or card.find('div', class_='search_price')
            
            if price_elem:
                text = price_elem.text.strip()
                if "free" in text.lower():
                    price = 0.0
                else:
                    m = re.search(r'(\d+[.,]\d+)', text)
                    if m:
                        price = float(m.group(1).replace(',', '.'))
            
            tags = []
            tags_cont = card.find('div', class_='search_tags')
            if tags_cont:
                tag_elems = tags_cont.find_all('span', class_='app_tag')
                tags = [t.text.strip().lower() for t in tag_elems if t.text.strip()][:10]
            
            return {
                "source": "steam",
                "source_id": app_id,
                "name": name,
                "url": href,
                "release_date": None,
                "price_eur": price,
                "tags": tags,
                "short_description": None,
                "category": category,
                "rank_in_category": rank + 1,
            }
        except Exception as e:
            logger.warning(f"Parse error: {e}")
            return None

steam_deep_collector = SteamDeepCollector()

class SteamCollector:
    def collect_new_trending(self, limit: int = 30) -> List[Dict]:
        return steam_deep_collector.collect_comprehensive(games_per_category=limit)


steam_collector = SteamCollector()
