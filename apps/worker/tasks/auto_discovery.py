"""
Auto-Discovery Task - Automatic game discovery from Steam and Itch.io
"""
from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Game, GameSource
from apps.worker.tasks.collect_steam import collect_steam_task
from apps.worker.tasks.collect_itch import collect_itch_task
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.auto_discovery.discover_new_games")
def discover_new_games():
    """
    Автоматический поиск новых игр через существующие коллекторы
    """
    logger.info("🔍 Starting auto-discovery...")
    
    try:
        # Запускаем существующие коллекторы
        logger.info("📊 Running Steam collector...")
        steam_result = collect_steam_task()
        
        logger.info("🎮 Running Itch.io collector...")
        itch_result = collect_itch_task()
        
        return {
            "status": "success",
            "steam": steam_result,
            "itch": itch_result
        }
        
    except Exception as e:
        logger.error(f"❌ Discovery failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@celery_app.task(name="apps.worker.tasks.auto_discovery.analyze_new_games")
def analyze_new_games():
    """
    Автоматический анализ всех игр без анализа
    """
    from apps.worker.tasks.analyze_narrative import analyze_game_narrative
    from apps.db.models_narrative import NarrativeAnalysis
    
    logger.info("🔬 Analyzing new games without narrative analysis...")
    
    try:
        db = get_db_session()
        
        try:
            # Найти игры без анализа
            stmt = (
                select(Game)
                .outerjoin(NarrativeAnalysis, Game.id == NarrativeAnalysis.game_id)
                .where(NarrativeAnalysis.id == None)
                .limit(50)
            )
            
            games = db.execute(stmt).scalars().all()
            
            logger.info(f"Found {len(games)} games without analysis")
            
            analyzed = 0
            failed = 0
            
            for game in games:
                try:
                    logger.info(f"Analyzing: {game.title or game.source_id}")
                    result = analyze_game_narrative(str(game.id))
                    
                    if result.get("status") == "success":
                        analyzed += 1
                    else:
                        failed += 1
                        logger.warning(f"Analysis failed for {game.title}: {result.get('error')}")
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"Error analyzing {game.title}: {e}")
                    continue
            
            return {
                "status": "success",
                "analyzed": analyzed,
                "failed": failed,
                "total": len(games)
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
