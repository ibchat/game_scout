"""
Wishlist Rank Collector - парсинг Steam Top Wishlisted и Popular Upcoming
"""
from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Game, GameSource
from apps.db.models_investor import WishlistSignalDaily
from sqlalchemy import select
from bs4 import BeautifulSoup
import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_wishlist_ranks.collect_wishlist_ranks_task")
def collect_wishlist_ranks_task():
    """
    Основная задача - собрать wishlist ranks из Steam
    """
    logger.info("🎯 Starting wishlist ranks collection...")
    
    results = {
        "top_wishlisted": 0,
        "popular_upcoming": 0,
        "new_signals": 0,
        "updated_signals": 0
    }
    
    try:
        db = get_db_session()
        
        try:
            # 1. Собрать Top Wishlisted
            logger.info("📊 Fetching Top Wishlisted...")
            top_wishlisted = fetch_top_wishlisted(limit=100)
            results["top_wishlisted"] = len(top_wishlisted)
            
            for rank, appid in enumerate(top_wishlisted, start=1):
                save_wishlist_signal(db, appid, rank, "top_wishlisted")
                results["new_signals"] += 1
            
            # 2. Собрать Popular Upcoming
            logger.info("🔥 Fetching Popular Upcoming...")
            popular_upcoming = fetch_popular_upcoming(limit=100)
            results["popular_upcoming"] = len(popular_upcoming)
            
            for rank, appid in enumerate(popular_upcoming, start=1):
                save_wishlist_signal(db, appid, rank, "popular_upcoming")
                results["new_signals"] += 1
            
            db.commit()
            
            logger.info(f"✅ Wishlist collection complete: {results}")
            return {"status": "success", "results": results}
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Wishlist collection failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


def fetch_top_wishlisted(limit: int = 100) -> list:
    """
    Парсинг Steam Top Wishlisted page
    Возвращает: [(appid, rank), ...]
    """
    url = "https://store.steampowered.com/search/"
    params = {
        "filter": "popularwishlist",
        "hidef2p": "1",
        "ndl": "1"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('a', class_='search_result_row', limit=limit)
        
        appids = []
        for result in results:
            data_ds_appid = result.get('data-ds-appid')
            if data_ds_appid:
                appids.append(data_ds_appid)
        
        logger.info(f"Found {len(appids)} games in Top Wishlisted")
        return appids
        
    except Exception as e:
        logger.error(f"Failed to fetch Top Wishlisted: {e}")
        return []


def fetch_popular_upcoming(limit: int = 100) -> list:
    """
    Парсинг Steam Popular Upcoming page
    """
    url = "https://store.steampowered.com/search/"
    params = {
        "filter": "comingsoon",
        "hidef2p": "1",
        "ndl": "1"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        results = soup.find_all('a', class_='search_result_row', limit=limit)
        
        appids = []
        for result in results:
            data_ds_appid = result.get('data-ds-appid')
            if data_ds_appid:
                appids.append(data_ds_appid)
        
        logger.info(f"Found {len(appids)} games in Popular Upcoming")
        return appids
        
    except Exception as e:
        logger.error(f"Failed to fetch Popular Upcoming: {e}")
        return []


def save_wishlist_signal(db, appid: str, rank: int, source: str):
    """
    Сохранить wishlist signal + вычислить EWI
    """
    # Найти игру по appid
    stmt = select(Game).where(
        Game.source == GameSource.steam,
        Game.source_id == appid
    )
    game = db.execute(stmt).scalar_one_or_none()
    
    if not game:
        logger.debug(f"Game not found for appid {appid}, skipping")
        return
    
    # Получить предыдущие ранки для дельт
    yesterday = datetime.utcnow() - timedelta(days=1)
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    stmt = select(WishlistSignalDaily).where(
        WishlistSignalDaily.game_id == game.id,
        WishlistSignalDaily.rank_source == source
    ).order_by(WishlistSignalDaily.date.desc()).limit(10)
    
    previous_signals = db.execute(stmt).scalars().all()
    
    # Вычислить дельты
    rank_delta_24h = None
    rank_delta_7d = None
    
    for prev in previous_signals:
        if prev.date >= yesterday and rank_delta_24h is None:
            rank_delta_24h = prev.rank - rank if prev.rank else None
        
        if prev.date >= week_ago and rank_delta_7d is None:
            rank_delta_7d = prev.rank - rank if prev.rank else None
    
    # Вычислить EWI
    ewi_score, ewi_confidence = compute_ewi(rank, rank_delta_24h, rank_delta_7d, source)
    
    # Создать новый сигнал
    signal = WishlistSignalDaily(
        game_id=game.id,
        date=datetime.utcnow(),
        rank=rank,
        rank_source=source,
        rank_delta_24h=rank_delta_24h,
        rank_delta_7d=rank_delta_7d,
        ewi_score=ewi_score,
        ewi_confidence=ewi_confidence,
        raw_data={"appid": appid, "source": source}
    )
    
    db.add(signal)
    logger.info(f"Saved wishlist signal for {game.title}: rank={rank}, EWI={ewi_score:.1f}")


def compute_ewi(rank: int, delta_24h: int, delta_7d: int, source: str) -> tuple:
    """
    Вычислить EWI (External Wishlist Index) 0-100
    
    Формула:
    - Base score = 100 - (rank / 100) * 50  (топ-1 = 100, топ-100 = 50)
    - Momentum bonus = delta_24h * 2 + delta_7d * 1
    - Source weight = 1.0 для top_wishlisted, 0.8 для popular_upcoming
    """
    # Base score от ранка
    base_score = max(0, 100 - (rank / 100) * 50)
    
    # Momentum bonus
    momentum = 0
    if delta_24h:
        momentum += delta_24h * 2  # Позитивная дельта = рост вверх = хорошо
    if delta_7d:
        momentum += delta_7d * 1
    
    # Source weight
    source_weight = 1.0 if source == "top_wishlisted" else 0.8
    
    # Итоговый EWI
    ewi = (base_score + momentum) * source_weight
    ewi = max(0, min(100, ewi))  # Clamp 0-100
    
    # Confidence
    confidence = 0.9 if rank <= 10 else 0.7 if rank <= 50 else 0.5
    
    return round(ewi, 1), confidence
