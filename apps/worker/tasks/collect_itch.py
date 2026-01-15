from apps.worker.celery_app import celery_app
from apps.worker.collectors.itch_collector import itch_collector
from apps.db.session import get_db_session
from apps.db.models import Game, GameMetricsDaily, GameSource
from sqlalchemy import select
from datetime import date
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_itch.collect_itch_task")
def collect_itch_task():
    """Collect games from itch.io - runs daily"""
    logger.info("Starting itch.io collection")
    
    try:
        # Collect games
        games_data = itch_collector.collect_trending(limit=30)
        
        if not games_data:
            logger.warning("No games collected from itch.io")
            return {"status": "no_data", "count": 0}
        
        # Store in database
        db = get_db_session()
        today = date.today()
        stored_count = 0
        
        try:
            for game_data in games_data:
                try:
                    # Check if game exists
                    stmt = select(Game).where(
                        Game.source == GameSource.itch,
                        Game.source_id == game_data["source_id"]
                    )
                    existing_game = db.execute(stmt).scalar_one_or_none()
                    
                    if existing_game:
                        # Update existing game
                        existing_game.title = game_data.get("name", "")
                        existing_game.url = game_data["url"]
                        existing_game.tags = game_data.get("tags", [])
                        existing_game.description = game_data.get("short_description")
                        if game_data.get("price_eur") is not None:
                            existing_game.price_eur = game_data["price_eur"]
                        game = existing_game
                    else:
                        # Create new game
                        game = Game(
                            source=GameSource.itch,
                            source_id=game_data["source_id"],
                            title=game_data.get("name", ""),
                            url=game_data["url"],
                            
                            price_eur=game_data.get("price_eur"),
                            tags=game_data.get("tags", []),
                            description=game_data.get("short_description")
                        )
                        db.add(game)
                        db.flush()
                    
                    # Store metrics for today
                    stmt = select(GameMetricsDaily).where(
                        GameMetricsDaily.game_id == game.id,
                        GameMetricsDaily.date == today
                    )
                    existing_metric = db.execute(stmt).scalar_one_or_none()
                    
                    if not existing_metric:
                        metric = GameMetricsDaily(
                            game_id=game.id,
                            date=today
                        )
                        db.add(metric)
                    
                    stored_count += 1
                    
                    stored_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to store game {game_data.get('name')}: {e}")
                    continue
            logger.info(f"Stored {stored_count} games from itch.io")
            
            return {"status": "success", "count": stored_count}
            
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Itch.io collection task failed: {e}")
        return {"status": "error", "error": str(e)}