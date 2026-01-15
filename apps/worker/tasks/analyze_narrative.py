"""
Narrative Analysis Task - Heuristic Version (NO API)
"""
from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Game
from apps.db.models_narrative import (
    NarrativeAnalysis, PatternScore, FixabilityFlags, InvestorCategory
)
from apps.worker.analysis.heuristic_analyzer import heuristic_analyzer
from apps.worker.analysis.investment_reasoning import generate_investment_reasoning, generate_short_pitch
from sqlalchemy import select
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.analyze_narrative.analyze_game_narrative")
def analyze_game_narrative(game_id: str):
    """Heuristic narrative analysis (no API required)"""
    logger.info(f"Starting heuristic analysis for {game_id}")
    
    try:
        db = get_db_session()
        
        try:
            stmt = select(Game).where(Game.id == game_id)
            game = db.execute(stmt).scalar_one_or_none()
            
            if not game:
                return {"status": "error", "error": "Game not found"}
            
            # Получаем последние метрики
            latest_metric = None
            if game.metrics:
                latest_metric = sorted(game.metrics, key=lambda m: m.date, reverse=True)[0]
            
            game_data = {
                "title": game.title,
                "description": game.description or "",
                "short_description": (game.description or "")[:200],
                "tags": [],
                "genre": "",
                "has_trailer": False,
                "has_demo": False,
                "screenshots_count": 0,
                # НОВОЕ: Добавляем реальные метрики
                "reviews_total": latest_metric.reviews_total if latest_metric else 0,
                "positive_reviews": latest_metric.positive_reviews if latest_metric else 0,
                "owners_min": latest_metric.owners_min if latest_metric else 0,
                # Вычисляем rating из positive/total reviews
                "rating": (latest_metric.positive_reviews / latest_metric.reviews_total * 100) if latest_metric and latest_metric.reviews_total > 0 else 0
            }
            
            # Запускаем эвристический анализ
            result = heuristic_analyzer.analyze_game(game_data)
            
            # Сохраняем в БД
            save_analysis_results(db, game_id, result)
            
            db.commit()
            
            logger.info(f"✅ Analysis complete for {game.title}")
            logger.info(f"PP: {result['product_potential']}, GTM: {result['gtm_execution']}, GAP: {result['gap_score']}")
            
            # Генерируем объяснение
            investment_reasoning = generate_investment_reasoning(game_data, result)
            short_pitch = generate_short_pitch(game_data, result)
            
            return {
                "status": "success",
                "game_title": game.title,
                "product_potential": result['product_potential'],
                "gtm_execution": result['gtm_execution'],
                "gap_score": result['gap_score'],
                "investor_category": result['investor_category'],
                "investment_reasoning": investment_reasoning,
                "short_pitch": short_pitch,
                "analysis_method": "heuristic"
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


def save_analysis_results(db, game_id, result):
    """Сохранение результатов в БД"""
    
    narrative = result['narrative_level']
    pattern = result['dramatic_pattern']
    
    # NarrativeAnalysis
    narrative_analysis = NarrativeAnalysis(
        game_id=game_id,
        analyzed_at=datetime.utcnow(),
        primary_level=narrative['primary_level'],
        secondary_level=narrative['secondary_level'],
        level_confidence=narrative['confidence'],
        blurred_focus=narrative['blurred_focus'],
        primary_pattern=pattern['primary_pattern'],
        secondary_pattern=pattern['secondary_pattern'],
        pattern_confidence=pattern['confidence'],
        player_state_before=pattern['player_state_before'],
        player_state_after=pattern['player_state_after'],
        pattern_in_gameplay=pattern['pattern_in_gameplay'],
        marketing_fiction=pattern['marketing_fiction'],
        llm_reasoning={
            "method": "heuristic",
            "narrative_evidence": narrative['evidence'],
            "pattern_evidence": pattern['evidence']
        }
    )
    db.add(narrative_analysis)
    db.flush()
    
    pp_details = result['pp_details']
    gtm_details = result['gtm_details']
    
    # PatternScore
    pattern_score = PatternScore(
        narrative_analysis_id=narrative_analysis.id,
        product_potential=result['product_potential'],
        pp_pattern_strength=pp_details['pattern_strength'],
        pp_universality=pp_details['universality'],
        pp_genre_fit=pp_details['genre_fit'],
        pp_loop_repeatability=pp_details['loop_repeatability'],
        gtm_execution=result['gtm_execution'],
        gtm_hook_clarity=gtm_details['hook_clarity'],
        gtm_trailer_alignment=gtm_details['trailer_alignment'],
        gtm_demo_intro=gtm_details['demo_intro'],
        gtm_page_clarity=gtm_details['page_clarity'],
        gap_score=result['gap_score'],
        gap_category=result['gap_category'],
        fixability_score=result['fixability']['fixability_score'],
        investor_category=result['investor_category'],
        investment_reasoning=result.get('investment_reasoning'),
        short_pitch=result.get('short_pitch'),
        scoring_metadata={"analysis_method": "heuristic", "confidence": result['confidence']}
    )
    db.add(pattern_score)
    db.flush()
    
    fix = result['fixability']
    
    # FixabilityFlags
    fixability_flags = FixabilityFlags(
        pattern_score_id=pattern_score.id,
        fixable_trailer=fix['fixable_trailer'],
        fixable_hook=fix['fixable_hook'],
        fixable_demo=fix['fixable_demo'],
        fixable_page_layout=fix['fixable_page_layout'],
        not_fixable_gameplay=fix['not_fixable_gameplay'],
        main_issues=fix['main_issues'],
        recommended_actions=fix['recommended_actions'],
        why_matters=fix['why_matters'],
        estimated_fix_days=fix['estimated_fix_days']
    )
    db.add(fixability_flags)
