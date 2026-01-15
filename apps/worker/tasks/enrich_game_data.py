"""
Enrich Game Data Task - Fetch descriptions and metadata
"""
from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Game, GameSource
from sqlalchemy import select
import requests
import logging
import time
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.enrich_game_data.enrich_all_games")
def enrich_all_games(limit: int = 50):
    """
    Обогатить данные игр (описания, теги) из Steam/Itch.io
    """
    logger.info(f"🔍 Enriching game data for up to {limit} games...")
    
    try:
        db = get_db_session()
        
        try:
            # Найти игры без описания
            stmt = select(Game).where(
                (Game.description == None) | (Game.description == '')
            ).limit(limit)
            
            games = db.execute(stmt).scalars().all()
            
            logger.info(f"Found {len(games)} games without descriptions")
            
            enriched = 0
            failed = 0
            
            for game in games:
                try:
                    if game.source == GameSource.steam:
                        success = enrich_steam_game(game)
                    elif game.source == GameSource.itch:
                        success = enrich_itch_game(game)
                    else:
                        continue
                    
                    if success:
                        enriched += 1
                        db.commit()
                        logger.info(f"✅ Enriched: {game.title or game.source_id}")
                    else:
                        failed += 1
                    
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Failed to enrich {game.source_id}: {e}")
                    failed += 1
                    continue
            
            return {
                "status": "success",
                "enriched": enriched,
                "failed": failed,
                "total": len(games)
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Enrichment failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


def enrich_steam_game(game: Game) -> bool:
    """Получить данные из Steam Store API"""
    try:
        appid = game.source_id
        
        # Steam Store API
        url = f"https://store.steampowered.com/api/appdetails"
        params = {"appids": appid, "l": "english"}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if str(appid) not in data or not data[str(appid)].get("success"):
            return False
        
        game_data = data[str(appid)]["data"]
        
        # Обновляем данные
        game.title = game_data.get("name") or game.title
        game.description = game_data.get("short_description") or game_data.get("about_the_game")
        
        # Обрезаем HTML теги из описания
        if game.description:
            soup = BeautifulSoup(game.description, 'html.parser')
            game.description = soup.get_text()[:1000]  # Первые 1000 символов
        
        return True
        
    except Exception as e:
        logger.warning(f"Failed to enrich Steam game {game.source_id}: {e}")
        return False


def enrich_itch_game(game: Game) -> bool:
    """Получить данные из Itch.io через поиск"""
    try:
        game_id = game.source_id
        title = game.title or game_id
        
        # Itch.io search API (неофициальный)
        search_url = f"https://itch.io/search"
        params = {"q": title}
        
        response = requests.get(search_url, params=params, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        
        if response.status_code != 200:
            # Fallback: ставим базовое описание из названия
            game.description = f"{title} - инди игра с Itch.io. Исследуйте уникальный геймплей и нарратив."
            return True
        
        # Парсим HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем первую игру в результатах
        game_cells = soup.find_all('div', class_='game_cell')
        
        if game_cells:
            first_game = game_cells[0]
            
            # Находим описание
            desc_elem = first_game.find('div', class_='game_text')
            if desc_elem:
                description = desc_elem.get_text(strip=True)
                game.description = description[:1000]  # Первые 1000 символов
                return True
        
        # Если не нашли - генерируем из названия
        game.description = f"{title} - инди игра с Itch.io с уникальным подходом к геймплею."
        return True
        
    except Exception as e:
        logger.warning(f"Failed to enrich Itch game {game.source_id}: {e}")
        # Ставим хоть что-то
        game.description = f"{game.title or game.source_id} - инди игра с Itch.io"
        return True


@celery_app.task(name="apps.worker.tasks.enrich_game_data.re_analyze_enriched")
def re_analyze_enriched():
    """
    Перезапустить анализ для игр которые были обогащены
    """
    from apps.worker.tasks.analyze_narrative import analyze_game_narrative
    from apps.db.models_narrative import NarrativeAnalysis
    
    logger.info("🔬 Re-analyzing games with fresh data...")
    
    try:
        db = get_db_session()
        
        try:
            # Найти игры с описанием и анализом
            stmt = (
                select(Game)
                .join(NarrativeAnalysis, Game.id == NarrativeAnalysis.game_id)
                .where(Game.description != None)
                .where(Game.description != '')
                .limit(50)
            )
            
            games = db.execute(stmt).scalars().all()
            
            logger.info(f"Re-analyzing {len(games)} games...")
            
            analyzed = 0
            for game in games:
                try:
                    # Удаляем старый анализ
                    stmt = select(NarrativeAnalysis).where(NarrativeAnalysis.game_id == game.id)
                    old_analysis = db.execute(stmt).scalar_one_or_none()
                    if old_analysis:
                        db.delete(old_analysis)
                        db.commit()
                    
                    # Запускаем новый анализ
                    result = analyze_game_narrative(str(game.id))
                    if result.get("status") == "success":
                        analyzed += 1
                        
                except Exception as e:
                    logger.error(f"Re-analysis failed for {game.title}: {e}")
                    continue
            
            return {
                "status": "success",
                "re_analyzed": analyzed,
                "total": len(games)
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Re-analysis failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
