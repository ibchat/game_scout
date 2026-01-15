from apps.worker.celery_app import celery_app
from apps.worker.collectors.steam_collector import steam_collector
from apps.worker.collectors.steamspy_collector import steamspy_collector
from apps.worker.analysis.trend_calculator import trend_calculator
from apps.db.session import get_db_session
from apps.db.models import Game, GameMetricsDaily, GameSource
from sqlalchemy import select
from datetime import date
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.collect_steam.collect_steam_task")
def collect_steam_task():
    """Collect games from Steam - runs daily"""
    logger.info("Starting Steam collection")
    
    try:
        # Collect games
        games_data = steam_collector.collect_new_trending(limit=30)
        
        if not games_data:
            logger.warning("No games collected from Steam")
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
                        Game.source == GameSource.steam,
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
                            source=GameSource.steam,
                            source_id=game_data["source_id"],
                            title=game_data.get("name", ""),
                            url=game_data["url"],
                            
                            price_eur=game_data.get("price_eur"),
                            tags=game_data.get("tags", []),
                            description=game_data.get("short_description")
                        )
                        db.add(game)
                        db.flush()  # Get the ID
                    
                    # Store metrics for today
                    stmt = select(GameMetricsDaily).where(
                        GameMetricsDaily.game_id == game.id,
                        GameMetricsDaily.date == today
                    )
                    existing_metric = db.execute(stmt).scalar_one_or_none()
                    
                    # Get detailed metrics from SteamSpy
                    steamspy_data = steamspy_collector.get_game_details(game_data["source_id"])
                    
                    if not existing_metric:
                        metric = GameMetricsDaily(
                            game_id=game.id,
                            date=today,
                            reviews_total=steamspy_data.get("reviews_total") if steamspy_data else None,
                            positive_reviews=steamspy_data.get("positive_reviews") if steamspy_data else None,
                            negative_reviews=steamspy_data.get("negative_reviews") if steamspy_data else None,
                            owners_min=steamspy_data.get("owners_min") if steamspy_data else None,
                            owners_max=steamspy_data.get("owners_max") if steamspy_data else None,
                            average_playtime_forever=steamspy_data.get("average_playtime_forever") if steamspy_data else None,
                            average_playtime_2weeks=steamspy_data.get("average_playtime_2weeks") if steamspy_data else None,
                            median_playtime_forever=steamspy_data.get("median_playtime_forever") if steamspy_data else None,
                            ccu=steamspy_data.get("ccu") if steamspy_data else None,
                            extras={"tags": steamspy_data.get("tags", {})} if steamspy_data else {},
                            wishlists=None,
                            followers=None
                        )
                        db.add(metric)
                    else:
                        # Update existing metric with SteamSpy data
                        if steamspy_data:
                            existing_metric.reviews_total = steamspy_data.get("reviews_total")
                            existing_metric.positive_reviews = steamspy_data.get("positive_reviews")
                            existing_metric.negative_reviews = steamspy_data.get("negative_reviews")
                            existing_metric.owners_min = steamspy_data.get("owners_min")
                            existing_metric.owners_max = steamspy_data.get("owners_max")
                            existing_metric.average_playtime_forever = steamspy_data.get("average_playtime_forever")
                            existing_metric.average_playtime_2weeks = steamspy_data.get("average_playtime_2weeks")
                            existing_metric.median_playtime_forever = steamspy_data.get("median_playtime_forever")
                            existing_metric.ccu = steamspy_data.get("ccu")
                            existing_metric.extras = {"tags": steamspy_data.get("tags", {})}
                    
                    db.commit()  # Commit after each game
                    
                    # Calculate and update trends
                    trends = trend_calculator.calculate_game_trends(str(game.id), db)
                    if trends.get("status") == "success":
                        # Update trends for both new and existing metrics
                        target_metric = metric if not existing_metric else existing_metric
                        target_metric.reviews_7d = trends.get("reviews_7d")
                        target_metric.reviews_30d = trends.get("reviews_30d")
                        target_metric.review_velocity_7d = trends.get("review_velocity_7d")
                        target_metric.momentum_ratio = trends.get("momentum_ratio")
                        db.commit()
                    stored_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to store game {game_data.get('name')}: {e}")
                    db.rollback()
                    continue
            logger.info(f"Stored {stored_count} games from Steam")
            
            return {"status": "success", "count": stored_count}
            
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"Steam collection task failed: {e}")
        return {"status": "error", "error": str(e)}