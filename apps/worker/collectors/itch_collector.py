from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging
import re

from apps.worker.collectors.http_client import http_client

logger = logging.getLogger(__name__)


class ItchCollector:
    """Light itch.io scraper for trending games"""
    
    BASE_URL = "https://itch.io"
    
    def collect_trending(self, limit: int = 30) -> List[Dict]:
        """
        Collect trending games from itch.io
        Light scraping - only fetch listing pages
        """
        games = []
        
        try:
            # Fetch the games page sorted by popular
            url = f"{self.BASE_URL}/games/top-rated"
            response = http_client.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find game cards
            game_cells = soup.find_all('div', class_='game_cell', limit=limit)
            
            for idx, cell in enumerate(game_cells):
                try:
                    game_data = self._parse_game_cell(cell, idx)
                    if game_data:
                        games.append(game_data)
                except Exception as e:
                    logger.warning(f"Failed to parse game cell: {e}")
                    continue
            
            logger.info(f"Collected {len(games)} games from itch.io")
            
        except Exception as e:
            logger.error(f"Failed to collect itch.io games: {e}")
        
        return games
    
    def _parse_game_cell(self, cell, rank: int) -> Optional[Dict]:
        """Parse a single game cell"""
        try:
            # Extract game link
            link_elem = cell.find('a', class_='game_link')
            if not link_elem:
                link_elem = cell.find('a', class_='title')
            
            if not link_elem:
                return None
            
            url = link_elem.get('href', '')
            if not url.startswith('http'):
                url = self.BASE_URL + url
            
            # Extract slug from URL
            slug_match = re.search(r'itch\.io/(.+?)(?:\?|$)', url)
            source_id = slug_match.group(1) if slug_match else url.split('/')[-1]
            
            # Extract name
            title_elem = cell.find('div', class_='game_title')
            if not title_elem:
                title_elem = cell.find('div', class_='title')
            
            name = title_elem.text.strip() if title_elem else source_id
            
            # Extract price
            price = None
            price_elem = cell.find('div', class_='price_value')
            if price_elem:
                price_text = price_elem.text.strip()
                if 'free' not in price_text.lower():
                    # Try to extract numeric price
                    price_match = re.search(r'(\d+[.,]\d+)', price_text)
                    if price_match:
                        price = float(price_match.group(1).replace(',', '.'))
            
            # Extract tags
            tags = []
            tags_container = cell.find('div', class_='game_genre')
            if tags_container:
                tag_links = tags_container.find_all('a')
                tags = [tag.text.strip().lower() for tag in tag_links if tag.text.strip()]
            
            # Extract short description
            short_desc = None
            desc_elem = cell.find('div', class_='game_text')
            if desc_elem:
                short_desc = desc_elem.text.strip()[:500]
            
            return {
                "source": "itch",
                "source_id": source_id,
                "name": name,
                "url": url,
                "release_date": None,
                "price_eur": price,
                "tags": tags,
                "short_description": short_desc,
                "rank_signal": float(rank + 1)
            }
            
        except Exception as e:
            logger.warning(f"Error parsing game cell: {e}")
            return None


# Global collector instance
itch_collector = ItchCollector()

itch_collector = ItchCollector()
