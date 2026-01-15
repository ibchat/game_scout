"""
Analytics Router
Новые endpoints для investor analytics
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from typing import List, Optional

from sqlalchemy import func
from apps.db.session import get_db
from apps.db.models import Game
from apps.db.models_investor import (
    GameInvestmentScore,
    WishlistSignalDaily,
    ExternalSignalDaily,
    ExternalVideo
)
from apps.api.schemas.analytics import (
    DashboardStatsSchema,
    GameInvestmentScoreSchema,
    EnrichedGameSchema
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardStatsSchema)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Получить статистику для dashboard
    """
    # Total games
    total_games = db.execute(select(func.count(Game.id))).scalar_one()
    
    # Games scored
    games_scored = db.execute(
        select(func.count(GameInvestmentScore.id))
    ).scalar_one()
    
    # Category breakdown
    category_counts = {}
    stmt = select(
        GameInvestmentScore.investor_category,
        func.count(GameInvestmentScore.id)
    ).group_by(GameInvestmentScore.investor_category)
    
    for category, count in db.execute(stmt):
        category_counts[category] = count
    
    # Average scores
    avg_scores = db.execute(
        select(
            func.avg(GameInvestmentScore.product_potential),
            func.avg(GameInvestmentScore.gtm_execution),
            func.avg(GameInvestmentScore.gap_score)
        )
    ).first()
    
    # External signals stats
    games_with_ewi = db.execute(
        select(func.count(func.distinct(WishlistSignalDaily.game_id)))
    ).scalar_one()
    
    games_with_epv = db.execute(
        select(func.count(func.distinct(ExternalSignalDaily.game_id)))
    ).scalar_one()
    
    avg_ewi = db.execute(
        select(func.avg(WishlistSignalDaily.ewi_score))
    ).scalar_one()
    
    avg_epv = db.execute(
        select(func.avg(ExternalSignalDaily.epv_score))
    ).scalar_one()
    
    return DashboardStatsSchema(
        total_games=total_games,
        games_scored=games_scored,
        undermarketed_gems=category_counts.get('undermarketed_gem', 0),
        marketing_fixable=category_counts.get('marketing_fixable', 0),
        product_risk=category_counts.get('product_risk', 0),
        not_investable=category_counts.get('not_investable', 0),
        watch=category_counts.get('watch', 0),
        avg_product_potential=round(avg_scores[0] or 0, 1),
        avg_gtm_execution=round(avg_scores[1] or 0, 1),
        avg_gap_score=round(avg_scores[2] or 0, 1),
        games_with_ewi=games_with_ewi,
        games_with_epv=games_with_epv,
        avg_ewi=round(avg_ewi, 1) if avg_ewi else None,
        avg_epv=round(avg_epv, 1) if avg_epv else None
    )


@router.get("/games/enriched", response_model=List[EnrichedGameSchema])
def get_enriched_games(
    category: Optional[str] = Query(None, description="Filter by investor category"),
    min_gap: Optional[float] = Query(None, description="Minimum GAP score"),
    has_ewi: Optional[bool] = Query(None, description="Has EWI score"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """
    Получить список игр с полной аналитикой
    """
    # Base query
    stmt = select(Game).join(
        GameInvestmentScore,
        Game.id == GameInvestmentScore.game_id,
        isouter=False
    )
    
    # Filters
    if category:
        stmt = stmt.where(GameInvestmentScore.investor_category == category)
    
    if min_gap is not None:
        stmt = stmt.where(GameInvestmentScore.gap_score >= min_gap)
    
    if has_ewi:
        stmt = stmt.join(
            WishlistSignalDaily,
            Game.id == WishlistSignalDaily.game_id
        ).where(WishlistSignalDaily.ewi_score.isnot(None))
    
    # Order by GAP (highest first)
    stmt = stmt.order_by(GameInvestmentScore.gap_score.desc())
    
    # Pagination
    stmt = stmt.limit(limit).offset(offset)
    
    games = db.execute(stmt).scalars().all()
    
    # Enrich with data
    enriched = []
    for game in games:
        # Get investment score
        score_stmt = select(GameInvestmentScore).where(
            GameInvestmentScore.game_id == game.id
        )
        score = db.execute(score_stmt).scalar_one_or_none()
        
        # Get latest external signals
        signal_stmt = select(ExternalSignalDaily).where(
            ExternalSignalDaily.game_id == game.id
        ).order_by(ExternalSignalDaily.date.desc()).limit(1)
        external_signal = db.execute(signal_stmt).scalar_one_or_none()
        
        # Get latest wishlist signal
        wishlist_stmt = select(WishlistSignalDaily).where(
            WishlistSignalDaily.game_id == game.id
        ).order_by(WishlistSignalDaily.date.desc()).limit(1)
        wishlist_signal = db.execute(wishlist_stmt).scalar_one_or_none()
        
        # Build external signals summary
        external_signals = {}
        if wishlist_signal:
            external_signals['ewi'] = {
                'score': wishlist_signal.ewi_score,
                'rank': wishlist_signal.rank,
                'confidence': wishlist_signal.ewi_confidence
            }
        
        if external_signal:
            external_signals['epv'] = {
                'score': external_signal.epv_score,
                'confidence': external_signal.epv_confidence,
                'youtube': external_signal.youtube_signal,
                'tiktok': external_signal.tiktok_signal
            }
        
        enriched.append(EnrichedGameSchema(
            game_id=str(game.id),
            title=game.title,
            source=game.source,
            url=game.url,
            description=game.description,
            scores=GameInvestmentScoreSchema(
                game_id=str(score.game_id),
                game_title=game.title,
                product_potential=score.product_potential,
                gtm_execution=score.gtm_execution,
                gap_score=score.gap_score,
                fixability_score=score.fixability_score,
                ewi_score=score.ewi_score,
                epv_score=score.epv_score,
                investor_category=score.investor_category,
                investment_reasoning=score.investment_reasoning,
                overall_confidence=score.overall_confidence,
                scored_at=score.scored_at
            ) if score else None,
            external_signals=external_signals if external_signals else None,
            latest_metrics=None  # TODO: add metrics if needed
        ))
    
    return enriched


@router.get("/games/{game_id}/details")
def get_game_details(game_id: str, db: Session = Depends(get_db)):
    """
    Получить детальную информацию об игре
    """
    # Get game
    stmt = select(Game).where(Game.id == game_id)
    game = db.execute(stmt).scalar_one_or_none()
    
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Get investment score
    score_stmt = select(GameInvestmentScore).where(
        GameInvestmentScore.game_id == game_id
    )
    score = db.execute(score_stmt).scalar_one_or_none()
    
    # Get videos
    videos_stmt = select(ExternalVideo).where(
        ExternalVideo.game_id == game_id
    ).limit(10)
    videos = db.execute(videos_stmt).scalars().all()
    
    # Get signals
    signal_stmt = select(ExternalSignalDaily).where(
        ExternalSignalDaily.game_id == game_id
    ).order_by(ExternalSignalDaily.date.desc())
    signals = db.execute(signal_stmt).scalars().all()
    
    return {
        "game": {
            "id": str(game.id),
            "title": game.title,
            "source": game.source,
            "url": game.url,
            "description": game.description
        },
        "investment_score": {
            "pp": score.product_potential,
            "gtm": score.gtm_execution,
            "gap": score.gap_score,
            "fix": score.fixability_score,
            "category": score.investor_category,
            "reasoning": score.investment_reasoning
        } if score else None,
        "videos": [
            {
                "platform": v.platform,
                "title": v.title,
                "url": v.url,
                "views": v.views,
                "likes": v.likes
            } for v in videos
        ],
        "signals_history": [
            {
                "date": s.date.isoformat(),
                "epv": s.epv_score,
                "videos_analyzed": s.videos_analyzed
            } for s in signals
        ]
    }


@router.get("/trend-queries")
def get_trend_queries(limit: int = 20):
    from apps.db.models_investor import TrendQuery
    from apps.db.session import get_db
    db = next(get_db())
    queries = db.query(TrendQuery).order_by(TrendQuery.created_at.desc()).limit(limit).all()
    return [{"query": q.query, "source": q.source, "reason": q.reason} for q in queries]

@router.get("/trend-snapshots")
def get_trend_snapshots():
    from apps.db.models_investor import YouTubeTrendSnapshot
    from apps.db.session import get_db
    db = next(get_db())
    snapshots = db.query(YouTubeTrendSnapshot).order_by(YouTubeTrendSnapshot.created_at.desc()).limit(5).all()
    return [{"date": str(s.date), "query_set": s.query_set, "top_mechanics": s.top_mechanics, "top_patterns": s.top_patterns} for s in snapshots]

@router.get("/stats")
def get_analytics_stats():
    from sqlalchemy import func
    from apps.db.session import get_db
    from apps.db.models import Game
    from apps.db.models_investor import GameInvestmentScore
    
    db = next(get_db())
    
    total_games = db.query(Game).count()
    analyzed = db.query(GameInvestmentScore).count()
    
    avg_scores = db.query(
        func.avg(GameInvestmentScore.product_potential),
        func.avg(GameInvestmentScore.gtm_execution),
        func.avg(GameInvestmentScore.gap_score)
    ).first()
    
    categories = db.query(
        GameInvestmentScore.investor_category,
        func.count(GameInvestmentScore.id)
    ).group_by(GameInvestmentScore.investor_category).all()
    
    return {
        "total_games": total_games,
        "analyzed": analyzed,
        "fixable": sum(c[1] for c in categories if 'fixable' in c[0]),
        "avg_pp": round(float(avg_scores[0] or 0), 1),
        "avg_gtm": round(float(avg_scores[1] or 0), 1),
        "avg_gap": round(float(avg_scores[2] or 0), 1),
        "categories": {c[0]: c[1] for c in categories}
    }

@router.get("/tiktok-videos")
def get_tiktok_videos(limit: int = 50):
    from apps.db.models_youtube import TikTokTrendVideo
    from apps.db.session import get_db
    db = next(get_db())
    videos = db.query(TikTokTrendVideo).order_by(TikTokTrendVideo.collected_at.desc()).limit(limit).all()
    return [{
        "video_id": v.video_id,
        "title": v.title,
        "url": v.url,
        "username": v.username,
        "view_count": v.view_count,
        "like_count": v.like_count,
        "comment_count": v.comment_count,
        "share_count": v.share_count,
        "query": v.query,
        "query_set": v.query_set
    } for v in videos]

@router.get("/reddit-posts")
def get_reddit_posts(limit: int = 50):
    from apps.db.models_youtube import RedditTrendPost
    from apps.db.session import get_db
    db = next(get_db())
    posts = db.query(RedditTrendPost).order_by(RedditTrendPost.collected_at.desc()).limit(limit).all()
    return [{
        "post_id": p.post_id,
        "title": p.title,
        "url": p.url,
        "subreddit": p.subreddit,
        "score": p.score,
        "num_comments": p.num_comments,
        "query": p.query
    } for p in posts]

@router.get("/twitter-tweets")
def get_twitter_tweets(limit: int = 50):
    from apps.db.models_youtube import TwitterTrendTweet
    from apps.db.session import get_db
    db = next(get_db())
    tweets = db.query(TwitterTrendTweet).order_by(TwitterTrendTweet.collected_at.desc()).limit(limit).all()
    return [{
        "tweet_id": t.tweet_id,
        "text": t.text,
        "url": t.url,
        "username": t.username,
        "likes": t.likes,
        "retweets": t.retweets,
        "query": t.query
    } for t in tweets]


@router.get("/games")
def get_games(category: str = "all", limit: int = 100):
    from apps.db.models import Game
    from apps.db.models_investor import GameInvestmentScore
    from apps.db.session import get_db
    from sqlalchemy import func
    
    db = next(get_db())
    
    query = db.query(
        Game.id.label('game_id'),
        Game.title,
        Game.source,
        GameInvestmentScore.product_potential,
        GameInvestmentScore.gtm_execution,
        GameInvestmentScore.gap_score,
        GameInvestmentScore.fixability_score,
        GameInvestmentScore.investor_category
    ).outerjoin(GameInvestmentScore, Game.id == GameInvestmentScore.game_id)
    
    if category != "all":
        query = query.filter(GameInvestmentScore.investor_category == category)
    
    games = query.limit(limit).all()
    
    return [{
        "game_id": str(g.game_id),
        "title": g.title,
        "source": g.source,
        "product_potential": float(g.product_potential) if g.product_potential else None,
        "gtm_execution": float(g.gtm_execution) if g.gtm_execution else None,
        "gap_score": float(g.gap_score) if g.gap_score else None,
        "fixability_score": float(g.fixability_score) if g.fixability_score else None,
        "investor_category": g.investor_category
    } for g in games]

@router.get("/reddit-insights")
def get_reddit_insights():
    from apps.db.models_investor import YouTubeTrendSnapshot
    from apps.db.session import get_db
    db = next(get_db())
    
    snapshot = db.query(YouTubeTrendSnapshot).filter(
        YouTubeTrendSnapshot.query_set.like('reddit_%')
    ).order_by(YouTubeTrendSnapshot.created_at.desc()).first()
    
    if not snapshot:
        return {"recommendations": ["Нет данных. Запустите сбор Reddit трендов."]}
    
    return {
        "date": str(snapshot.date),
        "top_mechanics": snapshot.top_mechanics,
        "top_terms": snapshot.top_terms,
        "recommendations": snapshot.signals.get('recommendations_ru', []),
        "community_sentiment": snapshot.signals.get('community_sentiment', 'unknown'),
        "total_score": snapshot.signals.get('total_score', 0),
        "total_comments": snapshot.signals.get('total_comments', 0)
    }

@router.get("/collection-history/{source}")
def get_collection_history(source: str, limit: int = 10):
    from apps.db.session import get_db
    from sqlalchemy import text
    db = next(get_db())
    
    result = db.execute(text("""
        SELECT 
            id, query_set, status, items_collected,
            started_at, completed_at, error_message,
            EXTRACT(EPOCH FROM (completed_at - started_at)) as duration_seconds
        FROM trend_collection_history
        WHERE source = :source
        ORDER BY started_at DESC
        LIMIT :limit
    """), {'source': source, 'limit': limit})
    
    history = []
    for row in result:
        history.append({
            'id': str(row[0]),
            'query_set': row[1],
            'status': row[2],
            'items_collected': row[3],
            'started_at': str(row[4]),
            'completed_at': str(row[5]),
            'error_message': row[6],
            'duration_seconds': int(row[7]) if row[7] else None
        })
    
    return history

@router.get("/collection-stats/{source}")
def get_collection_stats(source: str):
    from apps.db.session import get_db
    from sqlalchemy import text
    db = next(get_db())
    
    result = db.execute(text("""
        SELECT 
            COUNT(*) as total_runs,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_runs,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_runs,
            SUM(items_collected) as total_items,
            MAX(started_at) as last_run,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration
        FROM trend_collection_history
        WHERE source = :source
    """), {'source': source})
    
    row = result.fetchone()
    
    return {
        'source': source,
        'total_runs': row[0] or 0,
        'successful_runs': row[1] or 0,
        'failed_runs': row[2] or 0,
        'total_items_collected': row[3] or 0,
        'last_run': str(row[4]) if row[4] else None,
        'avg_duration_seconds': int(row[5]) if row[5] else None
    }

@router.get("/investor-overview")
def get_investor_overview():
    """Инвесторский обзор дня"""
    from apps.db.session import get_db
    from sqlalchemy import text
    from datetime import date, timedelta
    
    db = next(get_db())
    today = date.today()
    week_ago = today - timedelta(days=7)
    
    # ТОП-3 ТРЕНДА ДНЯ
    trends = db.execute(text("""
        SELECT 
            trend_name,
            source,
            trend_score,
            confidence,
            video_count + post_count as mentions,
            CASE 
                WHEN trend_score > 500 THEN 'Растёт'
                WHEN trend_score > 200 THEN 'Стабильно'
                ELSE 'Снижается'
            END as status,
            CASE
                WHEN confidence > 0.7 THEN 'Высокая'
                WHEN confidence > 0.5 THEN 'Средняя'
                ELSE 'Низкая'
            END as confidence_level
        FROM trend_daily_snapshot
        WHERE date = :today
        ORDER BY trend_score DESC
        LIMIT 3
    """), {'today': today}).fetchall()
    
    top_trends = [{
        'name': t[0],
        'source': t[1],
        'score': t[2],
        'mentions': t[4],
        'status': t[5],
        'confidence': t[6]
    } for t in trends]
    
    # СЛЕДУЮЩИЕ ДЕЙСТВИЯ (на основе трендов)
    actions = []
    if trends:
        top_trend = trends[0][0]
        actions = [
            f"Просканировать Itch.io по запросу '{top_trend}' за последние 14 дней",
            f"Отобрать проекты с демо и слабым GTM (GAP > 4)",
            f"Проверить наличие YouTube-видео у отобранных игр",
            f"Сформировать shortlist из 5 игр для контакта",
            f"Отслеживать рост тренда '{top_trend}' следующие 7 дней"
        ]
    
    return {
        'date': str(today),
        'top_trends': top_trends,
        'next_actions': actions
    }

@router.get("/weekly-trends")
def get_weekly_trends(weeks: int = 12):
    """Получить недельные тренды за N недель"""
    from apps.db.session import get_db
    from sqlalchemy import text
    from datetime import date, timedelta
    
    db = next(get_db())
    start_date = date.today() - timedelta(weeks=weeks)
    
    trends = db.execute(text("""
        SELECT 
            trend_name,
            AVG(avg_score) as avg_score,
            AVG(growth_rate) as avg_growth,
            AVG(stability_index) as avg_stability,
            SUM(total_mentions) as total_mentions,
            COUNT(*) as weeks_present
        FROM trend_weekly_aggregate
        WHERE week_start >= :start_date
        GROUP BY trend_name
        HAVING COUNT(*) >= 2
        ORDER BY avg_score DESC
        LIMIT 20
    """), {'start_date': start_date}).fetchall()
    
    return {
        'trends': [{
            'name': t[0],
            'avg_score': round(t[1], 1),
            'growth': round(t[2], 1),
            'stability': round(t[3], 2),
            'mentions': t[4],
            'weeks': t[5]
        } for t in trends]
    }

@router.get("/trend-timeline/{trend_name}")
def get_trend_timeline(trend_name: str):
    """Получить временную линию тренда"""
    from apps.db.session import get_db
    from sqlalchemy import text
    
    db = next(get_db())
    
    timeline = db.execute(text("""
        SELECT week_start, avg_score, growth_rate, stability_index
        FROM trend_weekly_aggregate
        WHERE trend_name = :name
        ORDER BY week_start DESC
        LIMIT 12
    """), {'name': trend_name}).fetchall()
    
    return {
        'trend': trend_name,
        'timeline': [{
            'week': str(t[0]),
            'score': round(t[1], 1),
            'growth': round(t[2], 1),
            'stability': round(t[3], 2)
        } for t in timeline]
    }

@router.get("/game-details/{game_id}")
def get_game_details(game_id: str):
    """Получить детали игры"""
    from apps.db.session import get_db
    from sqlalchemy import text
    
    db = next(get_db())
    
    game = db.execute(text("""
        SELECT 
            g.id, g.title, g.description, g.url,
            g.source, g.created_at,
            gis.product_potential, gis.gtm_execution, gis.team_score,
            gis.gap_score, gis.investor_category, gis.investment_reasoning
        FROM games g
        LEFT JOIN game_investment_scores gis ON g.id = gis.game_id
        WHERE g.id = :id
    """), {'id': game_id}).fetchone()
    
    if not game:
        return {"error": "Game not found"}
    
    return {
        'id': str(game[0]),
        'title': game[1],
        'description': game[2],
        'url': game[3],
        'source': game[4],
        'created_at': str(game[5]) if game[5] else None,
        'publisher': game[6],
        'scores': {
            'product_potential': float(game[7]) if game[7] else 0,
            'gtm_execution': float(game[8]) if game[8] else 0,
            'team_score': float(game[9]) if game[9] else 0,
            'gap_score': float(game[10]) if game[10] else 0
        },
        'category': game[10],
        'reasoning': game[11]
    }
