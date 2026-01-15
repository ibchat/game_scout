"""
Score Game Investment Task
Вычисление PP/GTM/GAP/Fixability для игры
"""
from apps.worker.celery_app import celery_app
from apps.worker.scoring.game_investment import (
    compute_pp,
    compute_gtm,
    compute_fixability,
    classify_investment
)
from apps.worker.scoring.external_signals import compute_epv
from apps.db.session import get_db_session
from apps.db.models import Game, GameMetricsDaily
from apps.db.models_investor import (
    GameNarrativeAnalysis,
    GameInvestmentScore,
    WishlistSignalDaily,
    ExternalSignalDaily
)
from sqlalchemy import select, func
from datetime import datetime, timedelta
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.score_game_investment.score_game_investment_task")
def score_game_investment_task(game_id: str):
    """
    Рассчитать investment score для игры
    
    Args:
        game_id: UUID игры
    """
    logger.info(f"💰 Starting investment scoring for game {game_id}")
    
    try:
        db = get_db_session()
        
        try:
            # 1. Получить игру
            stmt = select(Game).where(Game.id == game_id)
            game = db.execute(stmt).scalar_one_or_none()
            
            if not game:
                return {"status": "error", "error": f"Game {game_id} not found"}
            
            logger.info(f"Scoring game: {game.title}")
            
            # 2. Собрать данные
            game_data = _collect_game_data(db, game)
            narrative_data = _collect_narrative_data(db, game_id)
            external_signals = _collect_external_signals(db, game_id)
            
            # 3. Вычислить PP
            pp_score, pp_conf = compute_pp(
                game_data,
                narrative_data,
                game_data.get('metrics'),
                external_signals
            )
            
            # 4. Вычислить GTM
            gtm_score, gtm_conf = compute_gtm(
                game_data,
                narrative_data,
                game_data.get('page_quality'),
                external_signals
            )
            
            # 5. Вычислить GAP
            gap_score = pp_score - gtm_score
            
            # 6. Вычислить Fixability
            fix_score, timeline = compute_fixability(
                game_data,
                narrative_data
            )
            
            # 7. Получить EWI/EPV
            ewi_score = external_signals.get('ewi') if external_signals else None
            epv_score = external_signals.get('epv') if external_signals else None
            
            # 8. Классифицировать
            category, reasoning, roi = classify_investment(
                pp_score,
                gtm_score,
                gap_score,
                fix_score,
                ewi_score,
                epv_score
            )
            
            # 9. Сохранить результат
            stmt = select(GameInvestmentScore).where(
                GameInvestmentScore.game_id == game_id
            )
            existing = db.execute(stmt).scalar_one_or_none()
            
            if existing:
                # Обновить
                existing.product_potential = pp_score
                existing.gtm_execution = gtm_score
                existing.gap_score = gap_score
                existing.fixability_score = fix_score
                existing.ewi_score = ewi_score
                existing.epv_score = epv_score
                existing.investor_category = category
                existing.investment_reasoning = reasoning
                existing.updated_at = datetime.utcnow()
            else:
                # Создать новый
                score = GameInvestmentScore(
                    game_id=game_id,
                    product_potential=pp_score,
                    gtm_execution=gtm_score,
                    gap_score=gap_score,
                    fixability_score=fix_score,
                    ewi_score=ewi_score,
                    epv_score=epv_score,
                    investor_category=category,
                    investment_reasoning=reasoning,
                    overall_confidence=0.7,  # Default
                    scored_at=datetime.utcnow()
                )
                db.add(score)
            
            db.commit()
            
            logger.info(
                f"✅ Investment score saved: PP={pp_score}, GTM={gtm_score}, "
                f"GAP={gap_score}, FIX={fix_score}, category={category}"
            )
            
            return {
                "status": "success",
                "scores": {
                    "pp": pp_score,
                    "gtm": gtm_score,
                    "gap": gap_score,
                    "fix": fix_score,
                    "ewi": ewi_score,
                    "epv": epv_score,
                    "category": category,
                    "roi": roi
                }
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Investment scoring failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


def _collect_game_data(db, game: Game) -> dict:
    """Собрать данные об игре"""
    # Получить последние метрики
    stmt = select(GameMetricsDaily).where(
        GameMetricsDaily.game_id == game.id
    ).order_by(GameMetricsDaily.date.desc()).limit(1)
    
    latest_metrics = db.execute(stmt).scalar_one_or_none()
    
    data = {
        "title": game.title,
        "description": game.description or "",
        "tags": game.tags or [],
        "reviews": 0,
        "positive_ratio": 0.5,
        "metrics": {}
    }
    
    if latest_metrics:
        # GameMetricsDaily использует reviews_count вместо reviews
        reviews_count = getattr(latest_metrics, 'reviews_count', 0) or getattr(latest_metrics, 'review_count', 0) or 0
        positive = getattr(latest_metrics, 'positive', 0) or 0
        negative = getattr(latest_metrics, 'negative', 0) or 0
        
        data["reviews"] = reviews_count
        total = positive + negative
        if total > 0:
            data["positive_ratio"] = positive / total
        
        data["metrics"] = {
            "reviews": reviews_count,
            "rating": data["positive_ratio"],
            "avg_playtime_hours": getattr(latest_metrics, 'average_playtime', 0) or 0
        }
    
    return data


def _collect_narrative_data(db, game_id: str) -> Optional[dict]:
    """Собрать данные о нарративе"""
    stmt = select(GameNarrativeAnalysis).where(
        GameNarrativeAnalysis.game_id == game_id
    )
    
    narrative = db.execute(stmt).scalar_one_or_none()
    
    if narrative:
        return {
            "primary_level": narrative.primary_level,
            "primary_pattern": narrative.primary_pattern,
            "pattern_in_gameplay": narrative.pattern_in_gameplay,
            "confidence": narrative.confidence
        }
    
    return None


def _collect_external_signals(db, game_id: str) -> Optional[dict]:
    """Собрать внешние сигналы (EWI/EPV)"""
    # Получить последний EWI
    stmt = select(WishlistSignalDaily).where(
        WishlistSignalDaily.game_id == game_id
    ).order_by(WishlistSignalDaily.date.desc()).limit(1)
    
    wishlist = db.execute(stmt).scalar_one_or_none()
    
    # Получить последний EPV
    stmt = select(ExternalSignalDaily).where(
        ExternalSignalDaily.game_id == game_id
    ).order_by(ExternalSignalDaily.date.desc()).limit(1)
    
    external = db.execute(stmt).scalar_one_or_none()
    
    signals = {}
    
    if wishlist:
        signals['ewi'] = wishlist.ewi_score
        signals['ewi_confidence'] = wishlist.ewi_confidence
    
    if external:
        signals['epv'] = external.epv_score
        signals['epv_confidence'] = external.epv_confidence
        
        # Извлечь intent/confusion из YouTube signal
        if external.youtube_signal:
            signals['intent_ratio'] = external.youtube_signal.get('intent_ratio', 0)
            signals['confusion_ratio'] = external.youtube_signal.get('confusion_ratio', 0)
            signals['engagement'] = external.youtube_signal.get('engagement', 0)
    
    return signals if signals else None
