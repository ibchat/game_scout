"""
Daily Pipeline Orchestrator
Координирует ежедневный сбор данных и scoring
"""
from apps.worker.celery_app import celery_app
from apps.worker.tasks.collect_steam import collect_steam_task
from apps.worker.tasks.collect_itch import collect_itch_task
from apps.worker.tasks.collect_wishlist_ranks import collect_wishlist_ranks_task
from apps.worker.tasks.collect_youtube import collect_youtube_task
from apps.worker.tasks.collect_tiktok import collect_tiktok_task
from apps.worker.tasks.analyze_video_comments import analyze_video_comments_task
from apps.worker.tasks.score_game_investment import score_game_investment_task
from apps.db.session import get_db_session
from apps.db.models import Game
from apps.db.models_investor import ExternalVideo
from sqlalchemy import select
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.daily_pipeline.daily_pipeline_task")
def daily_pipeline_task():
    """
    Ежедневный pipeline сбора данных и анализа
    
    Порядок выполнения:
    1. Collect Steam games (новые игры)
    2. Collect Itch games
    3. Collect Wishlist Ranks (EWI)
    4. Для новых игр: YouTube + TikTok
    5. Analyze comments (если есть LLM)
    6. Score investments
    """
    logger.info("🚀 Starting daily pipeline")
    
    results = {
        "started_at": datetime.utcnow().isoformat(),
        "steps": {}
    }
    
    try:
        # STEP 1: Collect Steam Games
        logger.info("Step 1: Collecting Steam games...")
        try:
            steam_result = collect_steam_task.apply()
            results["steps"]["steam"] = {
                "status": "success",
                "result": steam_result.get() if steam_result else None
            }
            logger.info(f"✅ Steam collection: {results['steps']['steam']}")
        except Exception as e:
            logger.error(f"❌ Steam collection failed: {e}")
            results["steps"]["steam"] = {"status": "error", "error": str(e)}
        
        # STEP 2: Collect Itch Games
        logger.info("Step 2: Collecting Itch games...")
        try:
            itch_result = collect_itch_task.apply()
            results["steps"]["itch"] = {
                "status": "success",
                "result": itch_result.get() if itch_result else None
            }
            logger.info(f"✅ Itch collection: {results['steps']['itch']}")
        except Exception as e:
            logger.error(f"❌ Itch collection failed: {e}")
            results["steps"]["itch"] = {"status": "error", "error": str(e)}
        
        # STEP 3: Collect Wishlist Ranks
        logger.info("Step 3: Collecting wishlist ranks...")
        try:
            wishlist_result = collect_wishlist_ranks_task.apply()
            results["steps"]["wishlist"] = {
                "status": "success",
                "result": wishlist_result.get() if wishlist_result else None
            }
            logger.info(f"✅ Wishlist collection: {results['steps']['wishlist']}")
        except Exception as e:
            logger.error(f"❌ Wishlist collection failed: {e}")
            results["steps"]["wishlist"] = {"status": "error", "error": str(e)}
        
        # STEP 4: Collect External Signals for Recent Games
        logger.info("Step 4: Collecting external signals for recent games...")
        results["steps"]["external_signals"] = collect_external_signals_for_recent_games()
        
        # STEP 5: Analyze Comments
        logger.info("Step 5: Analyzing video comments...")
        results["steps"]["comment_analysis"] = analyze_recent_videos()
        
        # STEP 6: Score Investments
        logger.info("Step 6: Scoring game investments...")
        results["steps"]["investment_scoring"] = score_recent_games()
        
        results["completed_at"] = datetime.utcnow().isoformat()
        results["status"] = "success"
        
        logger.info(f"✅ Daily pipeline completed: {results}")
        return results
        
    except Exception as e:
        logger.error(f"❌ Daily pipeline failed: {e}", exc_info=True)
        results["status"] = "error"
        results["error"] = str(e)
        return results


def collect_external_signals_for_recent_games() -> dict:
    """
    Собрать YouTube/TikTok для игр добавленных за последние 7 дней
    """
    logger.info("Collecting external signals for recent games...")
    
    db = get_db_session()
    results = {
        "games_processed": 0,
        "youtube_collected": 0,
        "tiktok_collected": 0,
        "errors": []
    }
    
    try:
        # Найти игры добавленные за последние 7 дней
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        stmt = select(Game).where(
            Game.created_at >= seven_days_ago,
            Game.source == 'steam'  # Только Steam для external signals
        ).limit(20)  # Лимит чтобы не перегрузить
        
        recent_games = db.execute(stmt).scalars().all()
        
        logger.info(f"Found {len(recent_games)} recent games to process")
        
        for game in recent_games:
            try:
                # YouTube
                youtube_result = collect_youtube_task.apply_async(
                    args=[str(game.id)],
                    kwargs={'max_videos': 5, 'comment_limit': 100}
                )
                
                # TikTok
                tiktok_result = collect_tiktok_task.apply_async(
                    args=[str(game.id)],
                    kwargs={'max_videos': 5}
                )
                
                results["games_processed"] += 1
                results["youtube_collected"] += 1
                results["tiktok_collected"] += 1
                
                logger.info(f"Queued external signals for: {game.title}")
                
            except Exception as e:
                logger.error(f"Error queueing signals for {game.title}: {e}")
                results["errors"].append(str(e))
        
        return results
        
    finally:
        db.close()


def analyze_recent_videos() -> dict:
    """
    Анализировать комментарии к видео собранным за последние 24 часа
    """
    logger.info("Analyzing recent video comments...")
    
    db = get_db_session()
    results = {
        "videos_processed": 0,
        "videos_analyzed": 0,
        "errors": []
    }
    
    try:
        # Найти видео собранные за последние 24 часа с комментариями
        yesterday = datetime.utcnow() - timedelta(days=1)
        
        stmt = select(ExternalVideo).where(
            ExternalVideo.collected_at >= yesterday,
            ExternalVideo.comments_count > 0
        ).limit(50)  # Лимит для LLM quota
        
        recent_videos = db.execute(stmt).scalars().all()
        
        logger.info(f"Found {len(recent_videos)} recent videos with comments")
        
        for video in recent_videos:
            try:
                # Запустить анализ асинхронно
                analyze_video_comments_task.apply_async(
                    args=[str(video.id)]
                )
                
                results["videos_processed"] += 1
                results["videos_analyzed"] += 1
                
                logger.info(f"Queued comment analysis for video: {video.title}")
                
            except Exception as e:
                logger.error(f"Error queueing analysis for video {video.id}: {e}")
                results["errors"].append(str(e))
        
        return results
        
    finally:
        db.close()


def score_recent_games() -> dict:
    """
    Проскорить игры с новыми данными
    """
    logger.info("Scoring recent games...")
    
    db = get_db_session()
    results = {
        "games_processed": 0,
        "games_scored": 0,
        "errors": []
    }
    
    try:
        # Найти игры добавленные за последние 7 дней
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        stmt = select(Game).where(
            Game.created_at >= seven_days_ago
        ).limit(50)
        
        recent_games = db.execute(stmt).scalars().all()
        
        logger.info(f"Found {len(recent_games)} recent games to score")
        
        for game in recent_games:
            try:
                # Запустить scoring асинхронно
                score_game_investment_task.apply_async(
                    args=[str(game.id)]
                )
                
                results["games_processed"] += 1
                results["games_scored"] += 1
                
                logger.info(f"Queued investment scoring for: {game.title}")
                
            except Exception as e:
                logger.error(f"Error queueing scoring for {game.title}: {e}")
                results["errors"].append(str(e))
        
        return results
        
    finally:
        db.close()
