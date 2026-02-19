"""
Intel Sources Seeder
Seeds high-noise global sources for Intel collection.
"""
import logging
from typing import Dict, List, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from apps.intel.db.models import IntelSource, IntelSourceType

logger = logging.getLogger(__name__)


# High-noise global sources configuration
GLOBAL_SOURCES = [
    # Google News RSS (multiple locales)
    {
        "name": "Google News - Steam (US)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+game&hl=en-US&gl=US&ceid=US:en",
        "language_hint": "en",
        "priority": 20
    },
    {
        "name": "Google News - Steam (UK)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+game&hl=en-GB&gl=GB&ceid=GB:en",
        "language_hint": "en",
        "priority": 20
    },
    {
        "name": "Google News - Steam (DE)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+Spiel&hl=de&gl=DE&ceid=DE:de",
        "language_hint": "de",
        "priority": 20
    },
    {
        "name": "Google News - Steam (ES)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+juego&hl=es&gl=ES&ceid=ES:es",
        "language_hint": "es",
        "priority": 20
    },
    {
        "name": "Google News - Steam (FR)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+jeu&hl=fr&gl=FR&ceid=FR:fr",
        "language_hint": "fr",
        "priority": 20
    },
    {
        "name": "Google News - Steam (PL)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+gra&hl=pl&gl=PL&ceid=PL:pl",
        "language_hint": "pl",
        "priority": 20
    },
    {
        "name": "Google News - Steam (BR)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+jogo&hl=pt-BR&gl=BR&ceid=BR:pt",
        "language_hint": "pt",
        "priority": 20
    },
    {
        "name": "Google News - Steam (JP)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+ゲーム&hl=ja&gl=JP&ceid=JP:ja",
        "language_hint": "ja",
        "priority": 20
    },
    {
        "name": "Google News - Steam (KR)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+게임&hl=ko&gl=KR&ceid=KR:ko",
        "language_hint": "ko",
        "priority": 20
    },
    {
        "name": "Google News - Steam (CN)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+游戏&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "language_hint": "zh",
        "priority": 20,
        "country": "CN",
        "locale": "zh-CN"
    },
    {
        "name": "Google News - Steam (CA)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+game&hl=en-CA&gl=CA&ceid=CA:en",
        "language_hint": "en",
        "priority": 20,
        "country": "CA",
        "locale": "en-CA"
    },
    {
        "name": "Google News - Steam (AU)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+game&hl=en-AU&gl=AU&ceid=AU:en",
        "language_hint": "en",
        "priority": 20,
        "country": "AU",
        "locale": "en-AU"
    },
    {
        "name": "Google News - Steam (IT)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+gioco&hl=it&gl=IT&ceid=IT:it",
        "language_hint": "it",
        "priority": 20,
        "country": "IT",
        "locale": "it-IT"
    },
    {
        "name": "Google News - Steam (RU)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+игра&hl=ru&gl=RU&ceid=RU:ru",
        "language_hint": "ru",
        "priority": 20,
        "country": "RU",
        "locale": "ru-RU"
    },
    {
        "name": "Google News - Steam (TR)",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+oyun&hl=tr&gl=TR&ceid=TR:tr",
        "language_hint": "tr",
        "priority": 20,
        "country": "TR",
        "locale": "tr-TR"
    },
    # Reddit RSS (лучший "шум" про Steam)
    {
        "name": "Reddit - r/Steam",
        "type": IntelSourceType.reddit_rss,
        "url": "https://www.reddit.com/r/Steam/.rss",
        "language_hint": "en",
        "priority": 25
    },
    {
        "name": "Reddit - r/pcgaming",
        "type": IntelSourceType.reddit_rss,
        "url": "https://www.reddit.com/r/pcgaming/.rss",
        "language_hint": "en",
        "priority": 20
    },
    {
        "name": "Reddit - r/gaming",
        "type": IntelSourceType.reddit_rss,
        "url": "https://www.reddit.com/r/gaming/.rss",
        "language_hint": "en",
        "priority": 20
    },
    {
        "name": "Reddit - r/indiegames",
        "type": IntelSourceType.reddit_rss,
        "url": "https://www.reddit.com/r/indiegames/.rss",
        "language_hint": "en",
        "priority": 20
    },
    {
        "name": "Reddit - r/GameDeals",
        "type": IntelSourceType.reddit_rss,
        "url": "https://www.reddit.com/r/GameDeals/.rss",
        "language_hint": "en",
        "priority": 20
    },
    {
        "name": "Reddit - r/SteamDeck",
        "type": IntelSourceType.reddit_rss,
        "url": "https://www.reddit.com/r/SteamDeck/.rss",
        "language_hint": "en",
        "priority": 20
    },
    # SteamDB
    {
        "name": "SteamDB News",
        "type": IntelSourceType.rss,
        "url": "https://steamdb.info/feeds/news/",
        "language_hint": "en",
        "priority": 25
    },
    # Major gaming media RSS
    {
        "name": "PC Gamer RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.pcgamer.com/rss/",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "GameIndustry.biz RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.gamesindustry.biz/feed",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "IGN RSS",
        "type": IntelSourceType.rss,
        "url": "https://feeds.ign.com/ign/all",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "GameSpot RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.gamespot.com/feeds/news/",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "Polygon RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.polygon.com/rss/index.xml",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "Rock Paper Shotgun RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.rockpapershotgun.com/feed",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "VG247 RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.vg247.com/feed",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "Kotaku RSS",
        "type": IntelSourceType.rss,
        "url": "https://kotaku.com/rss",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "Eurogamer RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.eurogamer.net/feed",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "Destructoid RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.destructoid.com/feed",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "The Verge Gaming RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.theverge.com/games/rss/index.xml",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "Game Informer RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.gameinformer.com/feeds/thefeed.aspx",
        "language_hint": "en",
        "priority": 10
    },
    {
        "name": "Giant Bomb RSS",
        "type": IntelSourceType.rss,
        "url": "https://www.giantbomb.com/feeds/reviews/",
        "language_hint": "en",
        "priority": 10
    },
    # Steam Official (высокая релевантность, низкий шум)
    {
        "name": "Steam RSS News",
        "type": IntelSourceType.rss,
        "url": "https://store.steampowered.com/feeds/news.xml",
        "language_hint": "en",
        "priority": 30
    },
    {
        "name": "Steam Community Announcements",
        "type": IntelSourceType.rss,
        "url": "https://steamcommunity.com/games/steam/rss/",
        "language_hint": "en",
        "priority": 30
    },
    # Google News RSS - дополнительные запросы для большего охвата
    {
        "name": "Google News - Steam Release",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+release&hl=en-US&gl=US&ceid=US:en",
        "language_hint": "en",
        "priority": 20,
        "country": "US",
        "locale": "en-US"
    },
    {
        "name": "Google News - Steam Discount",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+discount&hl=en-US&gl=US&ceid=US:en",
        "language_hint": "en",
        "priority": 20,
        "country": "US",
        "locale": "en-US"
    },
    {
        "name": "Google News - Steam Valve",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+Valve&hl=en-US&gl=US&ceid=US:en",
        "language_hint": "en",
        "priority": 20,
        "country": "US",
        "locale": "en-US"
    },
    {
        "name": "Google News - Steam Ban",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+banned&hl=en-US&gl=US&ceid=US:en",
        "language_hint": "en",
        "priority": 20,
        "country": "US",
        "locale": "en-US"
    },
    {
        "name": "Google News - Steam Regulation",
        "type": IntelSourceType.rss,
        "url": "https://news.google.com/rss/search?q=Steam+regulation&hl=en-US&gl=US&ceid=US:en",
        "language_hint": "en",
        "priority": 20,
        "country": "US",
        "locale": "en-US"
    },
]


def seed_global_sources(db: Session, force_update: bool = False) -> Dict[str, Any]:
    """
    Seed high-noise global sources for Intel collection.
    
    Args:
        db: Database session
        force_update: If True, update existing sources (name, priority, is_enabled)
    
    Returns:
        Dict with summary: {added: int, updated: int, skipped: int, errors: List[str]}
    """
    added = 0
    updated = 0
    skipped = 0
    errors = []
    
    for source_config in GLOBAL_SOURCES:
        try:
            # Check if source already exists by URL
            existing = db.query(IntelSource).filter(
                IntelSource.url == source_config["url"]
            ).first()
            
            if existing:
                if force_update:
                    # Update existing source
                    existing.name = source_config["name"]
                    existing.type = source_config["type"].value
                    existing.language_hint = source_config.get("language_hint")
                    existing.priority = source_config.get("priority", 0)
                    existing.is_enabled = True
                    if "country" in source_config:
                        existing.country = source_config.get("country")
                    if "locale" in source_config:
                        existing.locale = source_config.get("locale")
                    if "category_hint" in source_config:
                        existing.category_hint = source_config.get("category_hint")
                    if "weight" in source_config:
                        existing.weight = source_config.get("weight", 10)
                    updated += 1
                    logger.info(f"Updated source: {source_config['name']}")
                else:
                    skipped += 1
                    logger.debug(f"Skipped existing source: {source_config['name']}")
            else:
                # Create new source
                new_source = IntelSource(
                    type=source_config["type"].value,
                    name=source_config["name"],
                    url=source_config["url"],
                    language_hint=source_config.get("language_hint"),
                    priority=source_config.get("priority", 0),
                    is_enabled=True,
                    country=source_config.get("country"),
                    locale=source_config.get("locale"),
                    category_hint=source_config.get("category_hint"),
                    weight=source_config.get("weight", 10)
                )
                db.add(new_source)
                added += 1
                logger.info(f"Added source: {source_config['name']}")
        
        except Exception as e:
            error_msg = f"Error processing source {source_config.get('name', 'unknown')}: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg, exc_info=True)
    
    try:
        db.commit()
        logger.info(f"Seeded sources: {added} added, {updated} updated, {skipped} skipped")
    except Exception as e:
        db.rollback()
        errors.append(f"Failed to commit sources: {str(e)}")
        logger.error(f"Failed to commit sources: {str(e)}", exc_info=True)
    
    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": len(GLOBAL_SOURCES)
    }
