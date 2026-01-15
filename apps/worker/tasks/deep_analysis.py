from celery import shared_task
import logging
from datetime import datetime
from apps.db.database import get_db
from apps.db.models import Game
from apps.worker.collectors.steam_collector import steam_deep_collector
from apps.worker.analytics.trend_analyzer import analyze_steam_market

logger = logging.getLogger(__name__)

@shared_task(name="deep_steam_analysis")
def deep_steam_analysis_task():
    logger.info("Starting deep analysis")
    try:
        games_data = steam_deep_collector.collect_comprehensive(games_per_category=50)
        if not games_data:
            return {"status": "error", "message": "No games"}
        
        db = next(get_db())
        stored, updated = 0, 0
        
        try:
            for gd in games_data:
                existing = db.query(Game).filter(
                    Game.source == "steam",
                    Game.source_id == gd["source_id"]
                ).first()
                
                if existing:
                    for k, v in gd.items():
                        if hasattr(existing, k):
                            setattr(existing, k, v)
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    db.add(Game(**gd))
                    stored += 1
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise
        
        return {"status": "success", "collected": len(games_data), "stored": stored, "updated": updated}
    except Exception as e:
        logger.error(f"Failed: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
