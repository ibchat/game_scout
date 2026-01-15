from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Game, GameMetricsDaily, GameSource
from apps.worker.collectors.steamspy_collector import steamspy_collector
from apps.worker.collectors.steam_wishlist_parser import steam_wishlist_parser
from apps.worker.analysis.trend_calculator import trend_calculator
from sqlalchemy import select
from datetime import date
import logging
import time

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.update_all_metrics.update_all_metrics_task")
def update_all_metrics_task():
    """Update metrics for ALL games in database"""
    logger.info("Starting metrics update for all games")
    
    try:
        db = get_db_session()
        today = date.today()
        updated_count = 0
        
        try:
            # Получаем ВСЕ игры из Steam
            stmt = select(Game).where(Game.source == GameSource.steam)
            all_games = db.execute(stmt).scalars().all()
            
            logger.info(f"Found {len(all_games)} Steam games to update")
            
            for game in all_games:
                try:
                    # Получаем данные из SteamSpy
                    steamspy_data = steamspy_collector.get_game_details(game.source_id)
                    
                    if not steamspy_data:
                        logger.warning(f"No SteamSpy data for {game.title}")
                        continue
                    
                    # Парсим wishlist со страницы Steam (медленно!)
                    wishlist_count = steam_wishlist_parser.get_wishlist_count(game.source_id)
                    time.sleep(1)  # Rate limiting
                    
                    # Проверяем есть ли метрика за сегодня
                    stmt = select(GameMetricsDaily).where(
                        GameMetricsDaily.game_id == game.id,
                        GameMetricsDaily.date == today
                    )
                    existing_metric = db.execute(stmt).scalar_one_or_none()
                    
                    if existing_metric:
                        # Обновляем существующую метрику
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
                        metric = existing_metric
                    else:
                        # Создаем новую метрику
                        metric = GameMetricsDaily(
                            game_id=game.id,
                            date=today,
                            reviews_total=steamspy_data.get("reviews_total"),
                            positive_reviews=steamspy_data.get("positive_reviews"),
                            negative_reviews=steamspy_data.get("negative_reviews"),
                            owners_min=steamspy_data.get("owners_min"),
                            owners_max=steamspy_data.get("owners_max"),
                            average_playtime_forever=steamspy_data.get("average_playtime_forever"),
                            average_playtime_2weeks=steamspy_data.get("average_playtime_2weeks"),
                            median_playtime_forever=steamspy_data.get("median_playtime_forever"),
                            ccu=steamspy_data.get("ccu"),
                            extras={"tags": steamspy_data.get("tags", {})},
                            wishlists=wishlist_count,
                            followers=None
                        )
                        db.add(metric)
                    
                    db.commit()
                    
                    # Рассчитываем тренды
                    trends = trend_calculator.calculate_game_trends(str(game.id), db)
                    if trends.get("status") == "success":
                        metric.reviews_7d = trends.get("reviews_7d")
                        metric.reviews_30d = trends.get("reviews_30d")
                        metric.review_velocity_7d = trends.get("review_velocity_7d")
                        metric.momentum_ratio = trends.get("momentum_ratio")
                        db.commit()
                    
                    updated_count += 1
                    
                    if updated_count % 10 == 0:
                        logger.info(f"Updated {updated_count}/{len(all_games)} games")
                    
                except Exception as e:
                    logger.error(f"Failed to update {game.title}: {e}")
                    db.rollback()
                    continue
            
            logger.info(f"Successfully updated metrics for {updated_count} games")
            return {"status": "success", "updated": updated_count, "total": len(all_games)}
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Metrics update task failed: {e}")
        return {"status": "error", "error": str(e)}
