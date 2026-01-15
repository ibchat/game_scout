from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Game, TrendsDaily, SignalType
from sqlalchemy import select, func
from datetime import date, timedelta
from collections import Counter
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.compute_trends.compute_trends_task")
def compute_trends_task():
    """Compute daily trends from collected games"""
    logger.info("Starting trend computation")
    
    db = get_db_session()
    today = date.today()
    
    try:
        # Get all games collected today
        stmt = select(Game).where(
            func.date(Game.created_at) == today
        )
        games = db.execute(stmt).scalars().all()
        
        if not games:
            logger.warning("No games found for today")
            return {"status": "no_data", "count": 0}
        
        # Aggregate tags
        tag_counter = Counter()
        for game in games:
            for tag in game.tags:
                if tag:
                    normalized_tag = tag.lower().strip()
                    tag_counter[normalized_tag] += 1
        
        logger.info(f"Found {len(tag_counter)} unique tags from {len(games)} games")
        
        # Compute trends for each tag
        trends_created = 0
        
        for signal, count in tag_counter.items():
            try:
                # Get last 7 days of data for this signal
                seven_days_ago = today - timedelta(days=7)
                stmt = select(TrendsDaily).where(
                    TrendsDaily.signal == signal,
                    TrendsDaily.date >= seven_days_ago,
                    TrendsDaily.date < today
                ).order_by(TrendsDaily.date.desc())
                
                historical = db.execute(stmt).scalars().all()
                
                # Compute avg_7d
                if historical:
                    avg_7d = sum(h.count for h in historical) / len(historical)
                else:
                    avg_7d = 0.0
                
                # Compute delta_7d
                delta_7d = count - avg_7d
                
                # Compute velocity (change in delta)
                if len(historical) >= 1:
                    yesterday_delta = historical[0].delta_7d
                    velocity = delta_7d - yesterday_delta
                else:
                    velocity = delta_7d
                
                # Create trend record
                trend = TrendsDaily(
                    date=today,
                    signal=signal,
                    signal_type=SignalType.tag,
                    count=count,
                    avg_7d=round(avg_7d, 2),
                    delta_7d=round(delta_7d, 2),
                    velocity=round(velocity, 2)
                )
                db.add(trend)
                trends_created += 1
                
            except Exception as e:
                logger.error(f"Failed to compute trend for signal '{signal}': {e}")
                continue
        
        db.commit()
        logger.info(f"Created {trends_created} trend records for {today}")
        
        return {"status": "success", "count": trends_created, "date": str(today)}
        
    except Exception as e:
        logger.error(f"Trend computation task failed: {e}")
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()