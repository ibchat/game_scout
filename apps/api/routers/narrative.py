"""
Narrative Analysis API Router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func
from apps.db.session import get_db
from apps.db.models import Game
from apps.db.models_narrative import NarrativeAnalysis, PatternScore, FixabilityFlags
from typing import List, Dict

router = APIRouter(prefix="/narrative", tags=["narrative"])


@router.get("/analyzed-games")
def get_analyzed_games(db: Session = Depends(get_db)):
    """Get all games with narrative analysis"""
    
    stmt = (
        select(Game)
        .join(NarrativeAnalysis)
        .join(PatternScore)
        .outerjoin(FixabilityFlags)
        .options(
            joinedload(Game.narrative_analysis).joinedload(NarrativeAnalysis.pattern_score).joinedload(PatternScore.fixability_flags)
        )
    )
    
    games = db.execute(stmt).unique().scalars().all()
    
    result_games = []
    for game in games:
        na = game.narrative_analysis
        ps = na.pattern_score if na else None
        ff = ps.fixability_flags if ps else None
        
        result_games.append({
            "title": game.title or "Unknown",
            "source": str(game.source) if game.source else None,  # Fixed: convert to string
            "primary_pattern": na.primary_pattern if na else None,
            "product_potential": float(ps.product_potential) if ps and ps.product_potential else 0,
            "gtm_execution": float(ps.gtm_execution) if ps and ps.gtm_execution else 0,
            "gap_score": float(ps.gap_score) if ps and ps.gap_score else 0,
            "fixability_score": float(ps.fixability_score) if ps and ps.fixability_score else 0,
            "investor_category": ps.investor_category if ps else "pending_analysis",
            "main_issues": ff.main_issues if ff else [],
            "recommended_actions": ff.recommended_actions if ff else [],
            "why_matters": ff.why_matters if ff else None,
            "estimated_fix_days": ff.estimated_fix_days if ff else None
        })
    
    return {"games": result_games, "total": len(result_games)}


@router.get("/stats")
def get_analysis_stats(db: Session = Depends(get_db)):
    """Get aggregate statistics"""
    
    total = db.execute(select(func.count(NarrativeAnalysis.id))).scalar()
    
    category_counts = db.execute(
        select(PatternScore.investor_category, func.count(PatternScore.id))
        .group_by(PatternScore.investor_category)
    ).all()
    
    avg_gap = db.execute(select(func.avg(PatternScore.gap_score))).scalar() or 0
    
    return {
        "total_analyzed": total,
        "categories": {cat: count for cat, count in category_counts},
        "average_gap": round(float(avg_gap), 2)
    }


@router.post("/discover")
def trigger_discovery():
    """Запустить поиск новых игр вручную"""
    from apps.worker.tasks.auto_discovery import discover_new_games
    task = discover_new_games.delay()
    return {"status": "started", "task_id": str(task.id)}


@router.post("/import-wishlist")
def import_wishlist(csv_file: str, source: str = "steam"):
    """Импорт wishlist из CSV файла"""
    from apps.worker.tasks.import_wishlist import import_wishlist_csv
    task = import_wishlist_csv.delay(csv_file, source)
    return {"status": "started", "task_id": str(task.id)}


@router.get("/wishlist-stats")
def get_wishlist_stats(db: Session = Depends(get_db)):
    """Статистика по wishlist данным"""
    from apps.db.models_narrative import WishlistData
    
    total = db.execute(select(func.count(WishlistData.id))).scalar()
    verified = db.execute(
        select(func.count(WishlistData.id))
        .where(WishlistData.mode == "verified")
    ).scalar()
    
    return {
        "total_records": total,
        "verified": verified,
        "estimated": total - verified
    }


@router.post("/enrich-games")
def trigger_enrichment():
    """Запустить обогащение данных игр"""
    from apps.worker.tasks.enrich_game_data import enrich_all_games
    task = enrich_all_games.delay()
    return {"status": "started", "task_id": str(task.id)}


@router.post("/re-analyze")
def trigger_re_analysis():
    """Перезапустить анализ для обогащённых игр"""
    from apps.worker.tasks.enrich_game_data import re_analyze_enriched
    task = re_analyze_enriched.delay()
    return {"status": "started", "task_id": str(task.id)}


@router.post("/test-wishlist-collector")
def test_wishlist_collector():
    """Тестовый endpoint для wishlist collector"""
    from apps.worker.tasks.collect_wishlist_ranks import collect_wishlist_ranks_task
    result = collect_wishlist_ranks_task()
    return result


@router.post("/test-youtube-collector")
def test_youtube_collector(game_id: str):
    """Тестовый endpoint для YouTube collector"""
    from apps.worker.tasks.collect_youtube import collect_youtube_task
    result = collect_youtube_task(game_id, max_videos=3, comment_limit=50)
    return result


@router.post("/test-tiktok-collector")
def test_tiktok_collector(game_id: str):
    """Тестовый endpoint для TikTok collector"""
    from apps.worker.tasks.collect_tiktok import collect_tiktok_task
    result = collect_tiktok_task(game_id, max_videos=5)
    return result


@router.post("/test-analyze-comments")
def test_analyze_comments(video_id: str):
    """Тестовый endpoint для анализа комментариев"""
    from apps.worker.tasks.analyze_video_comments import analyze_video_comments_task
    result = analyze_video_comments_task(video_id)
    return result


@router.post("/test-investment-scoring")
def test_investment_scoring(game_id: str):
    """Тестовый endpoint для investment scoring"""
    from apps.worker.tasks.score_game_investment import score_game_investment_task
    result = score_game_investment_task(game_id)
    return result


@router.post("/trigger-daily-pipeline")
def trigger_daily_pipeline():
    """Manually trigger daily pipeline"""
    from apps.worker.tasks.daily_pipeline import daily_pipeline_task
    task = daily_pipeline_task.apply_async()
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Daily pipeline started. This will take several minutes."
    }

@router.post("/test-steam-collector")
def test_steam_collector():
    """Test Steam collector"""
    from apps.worker.tasks.collect_steam import collect_steam_task
    task = collect_steam_task.apply_async()
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Steam collection started"
    }

@router.post("/test-itch-collector")
def test_itch_collector():
    """Test Itch collector"""
    from apps.worker.tasks.collect_itch import collect_itch_task
    task = collect_itch_task.apply_async()
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Itch.io collection started"
    }

@router.post("/test-youtube-trends")
def test_youtube_trends():
    from apps.worker.celery_app import celery_app
    task = celery_app.send_task(
        'collect_youtube_trends',
        args=['indie_radar', 25]
    )
    return {"status": "queued", "task_id": task.id}

@router.post("/test-trend-analysis")
def test_trend_analysis():
    from apps.worker.celery_app import celery_app
    
    # Запустить все stages последовательно
    t1 = celery_app.send_task('collect_youtube_comments', args=[20, 50])
    t2 = celery_app.send_task('analyze_youtube_trends', args=['indie_radar'])
    t3 = celery_app.send_task('generate_trend_queries')
    
    return {
        "status": "queued",
        "tasks": {
            "comments": t1.id,
            "analysis": t2.id,
            "queries": t3.id
        }
    }

@router.post("/test-tiktok-trends")
def test_tiktok_trends():
    from apps.worker.celery_app import celery_app
    task = celery_app.send_task('collect_tiktok_trends', args=['indie_radar', 25])
    return {"status": "queued", "task_id": task.id}

@router.post("/test-reddit-trends")
def test_reddit_trends():
    from apps.worker.celery_app import celery_app
    task = celery_app.send_task('collect_reddit_trends', args=['indie_radar', 20])
    return {"status": "queued", "task_id": task.id}

@router.post("/test-twitter-trends")
def test_twitter_trends():
    from apps.worker.celery_app import celery_app
    task = celery_app.send_task('collect_twitter_trends', args=['indie_radar', 25])
    return {"status": "queued", "task_id": task.id}

@router.post("/analyze-reddit-trends")
def analyze_reddit_trends():
    from apps.worker.celery_app import celery_app
    task = celery_app.send_task('analyze_reddit_trends', args=['indie_radar'])
    return {"status": "queued", "task_id": task.id}

@router.post("/save-daily-snapshot")
def save_daily_snapshot():
    from apps.worker.celery_app import celery_app
    task = celery_app.send_task('save_daily_snapshot')
    return {"status": "queued", "task_id": task.id}

@router.post("/calculate-weekly-aggregates")
def calculate_weekly():
    from apps.worker.celery_app import celery_app
    task = celery_app.send_task('calculate_weekly_aggregates')
    return {"status": "queued", "task_id": task.id}
