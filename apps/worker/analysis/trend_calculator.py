from sqlalchemy import select, desc
from apps.db.models import GameMetricsDaily
from datetime import datetime, timedelta
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class TrendCalculator:
    """Calculate trends and momentum for games"""
    
    def calculate_game_trends(self, game_id: str, db) -> Dict:
        """Calculate 7-day and 30-day trends for a game"""
        try:
            # Get last 30 days of metrics
            thirty_days_ago = datetime.now() - timedelta(days=30)
            
            stmt = select(GameMetricsDaily).where(
                GameMetricsDaily.game_id == game_id,
                GameMetricsDaily.date >= thirty_days_ago
            ).order_by(desc(GameMetricsDaily.date))
            
            metrics = db.execute(stmt).scalars().all()
            
            if len(metrics) < 2:
                return {"status": "insufficient_data"}
            
            # Sort by date ascending for calculations
            metrics = sorted(metrics, key=lambda x: x.date)
            
            latest = metrics[-1]
            week_ago = metrics[-7] if len(metrics) >= 7 else metrics[0]
            month_ago = metrics[0]
            
            # Calculate review velocity
            reviews_7d = latest.reviews_total - week_ago.reviews_total if latest.reviews_total and week_ago.reviews_total else 0
            reviews_30d = latest.reviews_total - month_ago.reviews_total if latest.reviews_total and month_ago.reviews_total else 0
            
            # Calculate daily average
            review_velocity_7d = reviews_7d / 7 if len(metrics) >= 7 else 0
            
            # Calculate momentum (acceleration)
            if len(metrics) >= 14:
                week_2_ago = metrics[-14]
                reviews_prev_week = week_ago.reviews_total - week_2_ago.reviews_total if week_ago.reviews_total and week_2_ago.reviews_total else 0
                momentum_ratio = reviews_7d / reviews_prev_week if reviews_prev_week > 0 else 1.0
            else:
                momentum_ratio = 1.0
            
            return {
                "status": "success",
                "reviews_7d": reviews_7d,
                "reviews_30d": reviews_30d,
                "review_velocity_7d": round(review_velocity_7d, 1),
                "momentum_ratio": round(momentum_ratio, 2),
                "trend_direction": "up" if momentum_ratio > 1.1 else "down" if momentum_ratio < 0.9 else "stable",
                "data_points": len(metrics)
            }
            
        except Exception as e:
            logger.error(f"Trend calculation failed for game {game_id}: {e}")
            return {"status": "error", "error": str(e)}

trend_calculator = TrendCalculator()
