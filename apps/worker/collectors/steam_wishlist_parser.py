import requests
from bs4 import BeautifulSoup
import re
import logging
import time

logger = logging.getLogger(__name__)

class SteamWishlistParser:
    """Parse wishlist counts from Steam store pages"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        })
    
    def get_wishlist_count(self, appid: str) -> int:
        """Try to extract wishlist count from Steam store page"""
        try:
            url = f"https://store.steampowered.com/app/{appid}/"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Парсим HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Метод 1: Ищем в тексте "X people have this on their wishlist"
            wishlist_patterns = [
                r'([\d,]+)\s+people\s+have\s+this\s+(?:game\s+)?on\s+their\s+wishlist',
                r'([\d,]+)\s+(?:users?\s+)?(?:have\s+)?wishlisted\s+this',
            ]
            
            page_text = soup.get_text()
            for pattern in wishlist_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    count_str = match.group(1).replace(',', '')
                    count = int(count_str)
                    logger.info(f"Found wishlist count for {appid}: {count:,}")
                    return count
            
            # Метод 2: Ищем в JSON data на странице
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if 'wishlist' in script.string.lower():
                    match = re.search(r'"wishlistCount":\s*(\d+)', script.string)
                    if match:
                        count = int(match.group(1))
                        logger.info(f"Found wishlist in JSON for {appid}: {count:,}")
                        return count
            
            # Метод 3: Проверяем специфичные div'ы
            wishlist_divs = soup.find_all('div', class_=re.compile('wishlist', re.I))
            for div in wishlist_divs:
                text = div.get_text()
                match = re.search(r'([\d,]+)', text)
                if match:
                    count_str = match.group(1).replace(',', '')
                    if count_str.isdigit() and int(count_str) > 100:
                        count = int(count_str)
                        logger.info(f"Found wishlist in div for {appid}: {count:,}")
                        return count
            
            logger.debug(f"No wishlist count found for {appid}")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"HTTP error for {appid}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse wishlist for {appid}: {e}")
            return None

steam_wishlist_parser = SteamWishlistParser()
