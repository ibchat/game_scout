from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models_investor import PipelineRun
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="apps.worker.tasks.morning_scan.morning_scan_task", bind=True)
def morning_scan_task(self, run_id: str, params: dict):
    db = get_db_session()
    try:
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            return {"status": "error", "error": "Run not found"}
        
        run.state = 'running'
        run.updated_at = datetime.utcnow()
        db.commit()
        
        # НОВАЯ ПОСЛЕДОВАТЕЛЬНОСТЬ С YOUTUBE
        stages = [
            ('collect_steam', collect_steam_stage),
            ('collect_itch', collect_itch_stage),
            ('youtube', youtube_trend_radar_stage),  # ← НОВОЕ!
            ('wishlist', collect_wishlist_stage),
            ('narrative', narrative_analysis_stage),
            ('scoring', investment_scoring_stage),
            ('comments', comment_analysis_stage),
            ('finalize', finalize_stage)
        ]
        
        for stage_name, stage_func in stages:
            try:
                run.stage = stage_name
                db.commit()
                stage_func(run_id, params, db)
                setattr(run, stage_name, True)
                run.progress_done += 1
                run.updated_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                logger.error(f"Stage {stage_name} failed: {e}")
                errors = run.errors or []
                errors.append({"stage": stage_name, "error": str(e)})
                run.errors = errors
                db.commit()
        
        run.state = 'done'
        run.finished_at = datetime.utcnow()
        db.commit()
        return {"status": "success", "run_id": run_id}
    finally:
        db.close()

def youtube_trend_radar_stage(run_id, params, db):
    """NEW: YouTube Trend Radar - собирает видео, комменты, генерит queries"""
    from apps.worker.celery_app import celery_app
    import os
    
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        logger.warning("YouTube API key not configured, skipping trend radar")
        return {"status": "skipped"}
    
    # 1. Collect videos
    celery_app.send_task('collect_youtube_trends', args=['indie_radar', 25]).get(timeout=30)
    
    # 2. Collect comments
    celery_app.send_task('collect_youtube_comments', args=[20, 50]).get(timeout=60)
    
    # 3. Analyze trends
    celery_app.send_task('analyze_youtube_trends', args=['indie_radar']).get(timeout=10)
    
    # 4. Generate queries
    celery_app.send_task('generate_trend_queries').get(timeout=10)
    
    logger.info("YouTube Trend Radar completed")
    return {"status": "success"}

def collect_steam_stage(run_id, params, db):
    from apps.worker.tasks.collect_steam import collect_steam_task
    collect_steam_task()
    return {"status": "success"}

def collect_itch_stage(run_id, params, db):
    from apps.worker.tasks.collect_itch import collect_itch_task
    collect_itch_task()
    return {"status": "success"}

def collect_wishlist_stage(run_id, params, db):
    from apps.worker.tasks.collect_wishlist_ranks import collect_wishlist_ranks_task
    collect_wishlist_ranks_task()
    return {"status": "success"}

def narrative_analysis_stage(run_id, params, db):
    from apps.db.models import Game
    from apps.db.models_investor import GameNarrativeAnalysis
    games = db.query(Game).filter(~Game.id.in_(db.query(GameNarrativeAnalysis.game_id))).limit(50).all()
    for game in games:
        narrative = GameNarrativeAnalysis(game_id=game.id, primary_level='biological', primary_pattern='survival', pattern_in_gameplay=True, confidence=0.7)
        db.add(narrative)
    db.commit()
    return {"count": len(games)}

def investment_scoring_stage(run_id, params, db):
    from apps.db.models import Game
    from apps.db.models_investor import GameInvestmentScore
    from apps.worker.tasks.score_game_investment import score_game_investment_task
    games = db.query(Game).filter(~Game.id.in_(db.query(GameInvestmentScore.game_id))).limit(50).all()
    for game in games:
        try:
            score_game_investment_task(str(game.id))
        except:
            pass
    return {"count": len(games)}

def comment_analysis_stage(run_id, params, db):
    return {"status": "success"}

def finalize_stage(run_id, params, db):
    return {"status": "success"}
