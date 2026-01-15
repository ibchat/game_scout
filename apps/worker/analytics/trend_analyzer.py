from typing import List, Dict
from collections import defaultdict, Counter
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from apps.db.models import Game

logger = logging.getLogger(__name__)

class TrendAnalyzer:
    def __init__(self, db: Session):
        self.db = db
    
    def analyze_market_trends(self) -> Dict:
        games = self.db.query(Game).filter(Game.source == 'steam').all()
        if not games:
            return {"status": "no_data"}
        
        genre_trends = self._analyze_genres(games)
        emerging = self._find_emerging(games)
        predictions = {"6_months": {"hot_genres": []}, "12_months": {}, "24_months": {}}
        recs = [{"type": "HOT", "priority": "HIGH", "title": "Горячие жанры", "genres": []}]
        
        return {
            "status": "success",
            "analyzed_games": len(games),
            "analysis_date": datetime.utcnow().isoformat(),
            "genre_trends": genre_trends,
            "emerging_genres": emerging,
            "predictions_2y": predictions,
            "investment_recommendations": recs
        }
    
    def _analyze_genres(self, games: List[Game]) -> Dict:
        stats = defaultdict(lambda: {"count": 0, "prices": []})
        for game in games:
            if game.tags:
                for tag in game.tags:
                    stats[tag]["count"] += 1
                    if game.price_eur:
                        stats[tag]["prices"].append(game.price_eur)
        
        trends = [{"genre": g, "game_count": s["count"], "avg_price_eur": round(sum(s["prices"])/len(s["prices"]), 2) if s["prices"] else 0, "momentum_score": 0, "market_strength": 0} for g, s in stats.items()]
        trends.sort(key=lambda x: x["game_count"], reverse=True)
        return {"total_genres": len(trends), "genres": trends[:50]}
    
    def _find_emerging(self, games: List[Game]) -> List[Dict]:
        return []

def analyze_steam_market(db: Session) -> Dict:
    return TrendAnalyzer(db).analyze_market_trends()
