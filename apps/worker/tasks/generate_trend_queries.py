from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_investor import YouTubeTrendSnapshot, TrendQuery
from datetime import date
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="generate_trend_queries")
def generate_trend_queries_task():
    db = get_db_session()
    try:
        today = date.today()
        snapshot = db.query(YouTubeTrendSnapshot).filter(
            YouTubeTrendSnapshot.date == today
        ).first()
        
        if not snapshot:
            logger.warning("No trend snapshot found")
            return {"status": "skipped"}
        
        # Генерация запросов
        queries = []
        for mechanic in snapshot.top_mechanics[:3]:
            for pattern in snapshot.top_patterns[:2]:
                query_text = f"{mechanic} {pattern.replace('_', ' ')}"
                queries.append({
                    'text': query_text,
                    'reason': {'mechanic': mechanic, 'pattern': pattern}
                })
        
        for term in snapshot.top_terms[:5]:
            queries.append({
                'text': f"{term} indie game",
                'reason': {'trending_term': term}
            })
        
        count = 0
        for q in queries[:20]:
            trend_query = TrendQuery(
                date=today,
                query=q['text'],
                source='youtube_radar',
                reason=q['reason'],
                priority=10
            )
            db.add(trend_query)
            count += 1
        
        db.commit()
        logger.info(f"Generated {count} trend queries")
        return {"status": "success", "queries": count}
    finally:
        db.close()
