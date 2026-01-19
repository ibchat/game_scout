"""
Steam Research Engine для Relaunch Scout
Ищет недореализованные игры через пагинацию Steam Search (general/genre/tag).
НЕ ищет тренды - это археология провалов.
"""

import requests
import time
import re
from typing import List, Set, Dict, Any, Optional, Tuple
from datetime import datetime
from bs4 import BeautifulSoup
import logging

from apps.api.routers.relaunch_config import (
    STEAM_GENRES,
    STEAM_TAGS,
    DEFAULT_PAGE_START,
    DEFAULT_PAGE_END,
    EXCLUDE_APP_IDS,
    EXCLUDE_NAME_CONTAINS,
    EXCLUDE_TYPES,
)

logger = logging.getLogger(__name__)

STEAM_SEARCH_BASE = "https://store.steampowered.com/search/"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_APPREVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"


class SteamResearchEngine:
    """Steam Research Engine - пагинация и сбор seed app_ids"""
    
    def __init__(self):
        self.session = requests.Session()
        # КРИТИЧНО: реалистичные заголовки для Steam
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        # Rate limiting: задержка между запросами (по умолчанию 250ms)
        self.rate_limit_delay = 0.25
    
    def collect_seed_app_ids(
        self,
        page_start: int = DEFAULT_PAGE_START,
        page_end: int = DEFAULT_PAGE_END,
        limit_seed: int = 400,
    ) -> Set[int]:
        """
        Собирает seed app_ids из нескольких источников:
        - General search (Released_DESC, Reviews_DESC)
        - Genre-based search
        - Tag-based search
        
        Возвращает set уникальных app_id.
        """
        seed_set: Set[int] = set()
        
        # 1) General search (увеличено покрытие)
        logger.info(f"Steam Research: General search (pages {page_start}-{page_end})")
        for sort_by in ["Released_DESC", "Reviews_DESC"]:
            for page in range(page_start, min(page_end + 1, page_start + 10)):  # Максимум 10 страниц
                app_ids, _ = self._fetch_search_page(
                    params={"sort_by": sort_by, "page": page, "category1": "998", "ndl": "1"}
                )
                seed_set.update(app_ids)
                time.sleep(self.rate_limit_delay)  # Rate limiting
                if len(seed_set) >= limit_seed:
                    break
            if len(seed_set) >= limit_seed:
                break
        
        # 2) Genre-based search (минимум 5 жанров как требуется)
        logger.info(f"Steam Research: Genre search (минимум 5 жанров)")
        for genre in STEAM_GENRES[:5]:  # Минимум 5 жанров
            for page in range(page_start, min(page_end + 1, page_start + 5)):  # 5 страниц на жанр
                app_ids, _ = self._fetch_search_page(
                    params={"genre": genre, "page": page, "category1": "998", "ndl": "1"}
                )
                seed_set.update(app_ids)
                time.sleep(self.rate_limit_delay)
                if len(seed_set) >= limit_seed:
                    break
            if len(seed_set) >= limit_seed:
                break
        
        # 3) Tag-based search (минимум 5 тегов как требуется)
        logger.info(f"Steam Research: Tag search (минимум 5 тегов)")
        for tag in STEAM_TAGS[:5]:  # Минимум 5 тегов
            for page in range(page_start, min(page_end + 1, page_start + 3)):  # 3 страницы на тег
                app_ids, _ = self._fetch_search_page(
                    params={"tags": tag, "page": page, "category1": "998", "ndl": "1"}
                )
                seed_set.update(app_ids)
                time.sleep(self.rate_limit_delay)
                if len(seed_set) >= limit_seed:
                    break
            if len(seed_set) >= limit_seed:
                break
        
        logger.info(f"Steam Research: Collected {len(seed_set)} unique app_ids")
        return seed_set
    
    def _fetch_search_page(self, params: Dict[str, Any], retries: int = 3) -> Tuple[List[int], Dict[str, Any]]:
        """
        Парсит одну страницу Steam Search и возвращает (список app_id, диагностика).
        
        PRIMARY: Использует /search/results/?query&start=N&count=50&infinite=1 (JSON endpoint)
        FALLBACK: Если JSON не работает — парсит HTML /search/?
        
        Диагностика содержит: status_code, final_url, markers (captcha/agecheck/search_result_row), html_sample, blocked_suspected.
        """
        import random
        
        # Добавляем cc=us, l=english для стабильности
        search_params = dict(params)
        if "cc" not in search_params:
            search_params["cc"] = "us"
        if "l" not in search_params:
            search_params["l"] = "english"
        
        # PRIMARY: Используем results endpoint с infinite=1 (JSON-based)
        # Формат: start=0, count=50 (или больше)
        page = params.get("page", 1)
        search_params_results = {
            "query": search_params.get("term", ""),
            "start": (page - 1) * 50,  # Пагинация: start=0, 50, 100, ...
            "count": 50,
            "infinite": "1",
            "cc": search_params.get("cc", "us"),
            "l": search_params.get("l", "english"),
        }
        
        # Добавляем другие параметры из оригинального params
        if "sort_by" in search_params:
            search_params_results["sort_by"] = search_params["sort_by"]
        if "category1" in search_params:
            search_params_results["category1"] = search_params["category1"]
        
        search_url_primary = "https://store.steampowered.com/search/results/"
        search_url_fallback = "https://store.steampowered.com/search/"
        
        blocked_suspected = False
        
        for attempt in range(retries):
            try:
                # PRIMARY: Пробуем results endpoint (JSON-based)
                response = None
                try:
                    response = self.session.get(
                        search_url_primary,
                        params=search_params_results,
                        timeout=15
                    )
                    response.raise_for_status()
                    
                    # Пробуем парсить как JSON (если infinite=1)
                    try:
                        json_data = response.json()
                        app_ids = []
                        
                        # Извлекаем app_ids из JSON (может быть в results_html или total_count/data)
                        if "results_html" in json_data:
                            # Парсим HTML из JSON
                            soup_json = BeautifulSoup(json_data["results_html"], 'html.parser')
                            for row in soup_json.find_all('a', class_=re.compile(r'search_result_row')):
                                href = row.get('href', '')
                                match = re.search(r'/app/(\d+)', href)
                                if match:
                                    try:
                                        app_id = int(match.group(1))
                                        if app_id > 0:
                                            app_ids.append(app_id)
                                    except (ValueError, TypeError):
                                        continue
                        
                        if app_ids:
                            unique_ids = list(set(app_ids))
                            markers = {
                                "search_result_row": True,
                                "captcha": False,
                                "agecheck": False,
                            }
                            diagnostics = {
                                "status_code": response.status_code,
                                "final_url": str(response.url),
                                "markers": markers,
                                "html_sample": json_data.get("results_html", "")[:500] if "results_html" in json_data else "",
                                "blocked_suspected": False,
                            }
                            logger.info(f"Steam Search (JSON) found {len(unique_ids)} app_ids on page {page}")
                            return unique_ids, diagnostics
                    except (ValueError, KeyError):
                        # Не JSON, продолжаем как HTML
                        pass
                except Exception as primary_error:
                    logger.debug(f"Primary endpoint failed, trying fallback: {primary_error}")
                    response = None
                
                # FALLBACK: Парсим обычный HTML endpoint
                if response is None:
                    response = self.session.get(
                        search_url_fallback,
                        params=search_params,
                        timeout=15
                    )
                    response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                app_ids = []
                
                # Диагностика: определяем markers (captcha, agecheck, search_result_row)
                html_lower = response.text.lower()
                markers = {
                    "search_result_row": bool(soup.find_all('a', class_=re.compile(r'search_result_row'))),
                    "captcha": "captcha" in html_lower or "you are a robot" in html_lower or "i'm not a robot" in html_lower,
                    "agecheck": "agecheck" in html_lower or "age verification" in html_lower,
                }
                blocked_suspected = markers["captcha"] or ("robot" in html_lower and "captcha" in html_lower)
                
                # Метод 1: Ищем search_result_row (основной метод для Steam Search)
                for row in soup.find_all('a', class_=re.compile(r'search_result_row')):
                    href = row.get('href', '')
                    match = re.search(r'/app/(\d+)', href)
                    if match:
                        try:
                            app_id = int(match.group(1))
                            if app_id > 0 and app_id not in app_ids:
                                app_ids.append(app_id)
                        except (ValueError, TypeError):
                            continue
                
                # Метод 2: Ищем data-ds-appid атрибуты (fallback)
                if len(app_ids) < 10:
                    for elem in soup.find_all(attrs={"data-ds-appid": True}):
                        try:
                            app_id = int(elem.get("data-ds-appid"))
                            if app_id > 0 and app_id not in app_ids:
                                app_ids.append(app_id)
                        except (ValueError, TypeError):
                            continue
                
                # Метод 3: Ищем все ссылки вида /app/{id}/ (fallback)
                if len(app_ids) < 10:
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '')
                        match = re.search(r'/app/(\d+)', href)
                        if match:
                            try:
                                app_id = int(match.group(1))
                                if app_id > 0 and app_id not in app_ids:
                                    app_ids.append(app_id)
                            except (ValueError, TypeError):
                                continue
                
                unique_ids = list(set(app_ids))  # Дедупликация
                
                # Диагностика для возврата
                diagnostics = {
                    "status_code": response.status_code,
                    "final_url": str(response.url),
                    "markers": markers,
                    "html_sample": response.text[:500] if len(response.text) > 500 else response.text,
                    "blocked_suspected": blocked_suspected,
                }
                
                # Логирование
                if not unique_ids:
                    logger.warning(f"Steam Search page {params.get('page', 1)} returned 0 app_ids. Status: {response.status_code}, URL: {response.url}, Markers: {markers}, Blocked: {blocked_suspected}")
                else:
                    logger.info(f"Found {len(unique_ids)} app_ids on page {params.get('page', 1)}")
                
                return unique_ids, diagnostics
            except Exception as e:
                if attempt < retries - 1:
                    backoff_delay = 0.5 * (2 ** attempt) + random.uniform(0, 0.5)  # Jitter
                    logger.warning(f"Error fetching search page {params} (attempt {attempt+1}/{retries}): {e}. Retrying after {backoff_delay:.2f}s...")
                    time.sleep(backoff_delay)
                else:
                    logger.warning(f"Error fetching search page {params} after {retries} attempts: {e}")
                    return [], {
                        "status_code": 0,
                        "final_url": "",
                        "markers": {"search_result_row": False, "captcha": False, "agecheck": False},
                        "html_sample": "",
                        "blocked_suspected": True,  # Подозрение на блокировку при ошибке
                    }
        return [], {
            "status_code": 0,
            "final_url": "",
            "markers": {"search_result_row": False, "captcha": False, "agecheck": False},
            "html_sample": "",
        }
    
    def fetch_app_details(self, app_id: int, retries: int = 3, backoff_base: float = 0.5) -> Optional[Dict[str, Any]]:
        """
        Получает детали игры из Steam API (с retries, backoff и улучшенной обработкой).
        Фиксирует cc=us&l=en для стабильности.
        """
        # КРИТИЧНО: проверяем тип app_id
        if not isinstance(app_id, int):
            raise TypeError(f"fetch_app_details expects int app_id, got {type(app_id)}: {app_id}")
        
        for attempt in range(retries):
            try:
                # 1) Получаем appdetails (фиксируем cc=us&l=en)
                response = self.session.get(
                    STEAM_APPDETAILS_URL,
                    params={"appids": app_id, "l": "en", "cc": "us"},  # Фиксируем l=en (было english)
                    timeout=15  # Увеличено до 15s
                )
                response.raise_for_status()
                
                data = response.json().get(str(app_id), {})
                if not data.get("success"):
                    if attempt < retries - 1:
                        # Exponential backoff
                        backoff_delay = backoff_base * (2 ** attempt)
                        time.sleep(backoff_delay)
                        continue
                    return None
                
                game_data = data.get("data", {})
                
                # КРИТИЧНО: проверяем что name получен (не пустой и не "App {id}")
                name = game_data.get("name", "")
                if not name or name.startswith("App ") or name == f"App {app_id}":
                    if attempt < retries - 1:
                        # Exponential backoff
                        backoff_delay = backoff_base * (2 ** attempt)
                        time.sleep(backoff_delay)
                        continue
                    logger.warning(f"Invalid name for app_id {app_id}: '{name}'")
                    return None
                
                # 2) Извлекаем reviews через reviews API (КРИТИЧНО: в appdetails нет reviews_total, нужно получать из reviews API)
                reviews_total = 0
                positive_ratio = 0.0
                reviews_missing = False
                try:
                    r2 = self.session.get(
                        STEAM_APPREVIEWS_URL.format(app_id=app_id),
                        params={"json": 1, "filter": "all", "language": "all", "num_per_page": 0},
                        timeout=10  # Увеличено до 10s
                    )
                    if r2.status_code == 200:
                        review_data = r2.json().get("query_summary", {})
                        total_positive = review_data.get("total_positive", 0)
                        total_negative = review_data.get("total_negative", 0)
                        reviews_total = review_data.get("total_reviews", 0) or (total_positive + total_negative)
                        
                        # Вычисляем positive_ratio
                        if reviews_total > 0:
                            positive_ratio = total_positive / reviews_total
                    else:
                        reviews_missing = True
                        logger.debug(f"Reviews API returned status {r2.status_code} for {app_id} (non-critical)")
                except Exception as e:
                    reviews_missing = True
                    logger.debug(f"Failed to fetch reviews for {app_id}: {e} (non-critical, continuing without reviews)")
                    # Продолжаем без reviews (НЕ критично)
                
                # 3) Формируем результат с flags для missing fields
                release_date_str = game_data.get("release_date", {}).get("date")
                price_overview = game_data.get("price_overview", {})
                
                # Flags для missing fields (НЕ hard-exclude, а снижение score)
                has_price = bool(price_overview and price_overview.get("final", 0) > 0)
                has_reviews = reviews_total > 0
                has_release_date = bool(release_date_str)
                
                return {
                    "app_id": app_id,
                    "name": name,  # Гарантированно нормальное имя
                    "type": game_data.get("type", ""),
                    "release_date": release_date_str,
                    "is_free": game_data.get("is_free", False),
                    "price_overview": price_overview,
                    "genres": [g.get("description") for g in game_data.get("genres", [])],
                    "categories": [c.get("description") for c in game_data.get("categories", [])],
                    "tags": [t.get("description") for t in game_data.get("tags", [])[:10]],
                    "reviews_total": reviews_total,
                    "positive_ratio": positive_ratio,
                    "steam_url": f"https://store.steampowered.com/app/{app_id}",
                    # Flags для missing fields (для снижения score, не hard-exclude)
                    "_flags": {
                        "has_price": has_price,
                        "has_reviews": has_reviews,
                        "has_release_date": has_release_date,
                        "reviews_missing": reviews_missing,
                    },
                }
            except Exception as e:
                if attempt < retries - 1:
                    logger.warning(f"Error fetching app details for {app_id} (attempt {attempt+1}/{retries}): {e}. Retrying...")
                    # Exponential backoff
                    backoff_delay = backoff_base * (2 ** attempt)
                    time.sleep(backoff_delay)
                else:
                    logger.warning(f"Error fetching app details for {app_id} after {retries} attempts: {e}")
                    return None
        return None


# Глобальный экземпляр
steam_research_engine = SteamResearchEngine()
