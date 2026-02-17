"""
Discord Candidate Ranking Task
Ranks Discord invite candidates and guilds by quality score
"""
import logging
import math
from typing import Dict, Any, List
from sqlalchemy import text

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.config.discord_discovery_config import (
    QUALITY_SCORE_WEIGHTS,
    PUBLISHER_INTENT_KEYWORDS
)

logger = logging.getLogger(__name__)


@celery_app.task(name="rank_discord_candidates_task")
def rank_discord_candidates_task() -> Dict[str, Any]:
    """
    Calculate quality scores for all candidates and update rankings.
    
    Returns:
        {
            "status": "ok",
            "candidates_ranked": int,
            "guilds_ranked": int
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "candidates_ranked": 0,
        "guilds_ranked": 0
    }
    
    try:
        # Get all candidates with status 'ok'
        candidates = db.execute(
            text("""
                SELECT 
                    invite_code, guild_id, guild_name, channel_name,
                    approx_member_count, approx_online_count,
                    source_type, source_url, expires_at, resolve_status
                FROM discord_invite_candidate
                WHERE resolve_status = 'ok'
            """)
        ).fetchall()
        
        for candidate in candidates:
            score = _calculate_quality_score(
                member_count=candidate.approx_member_count or 0,
                online_count=candidate.approx_online_count or 0,
                guild_name=candidate.guild_name or "",
                channel_name=candidate.channel_name or "",
                source_type=candidate.source_type or "",
                source_url=candidate.source_url or "",
                is_expired=candidate.expires_at is not None and candidate.expires_at < db.execute(text("SELECT NOW()")).scalar()
            )
            
            db.execute(
                text("""
                    UPDATE discord_invite_candidate
                    SET quality_score = :score
                    WHERE invite_code = :code
                """),
                {
                    "code": candidate.invite_code,
                    "score": score
                }
            )
            results["candidates_ranked"] += 1
        
        # Calculate guild scores (aggregate from candidates)
        guilds = db.execute(
            text("""
                SELECT DISTINCT guild_id
                FROM discord_invite_candidate
                WHERE resolve_status = 'ok' AND guild_id IS NOT NULL
            """)
        ).fetchall()
        
        for guild in guilds:
            # Get best quality score for this guild
            best_score = db.execute(
                text("""
                    SELECT MAX(quality_score)
                    FROM discord_invite_candidate
                    WHERE guild_id = :guild_id AND resolve_status = 'ok'
                """),
                {"guild_id": guild.guild_id}
            ).scalar() or 0.0
            
            # Update or insert guild
            db.execute(
                text("""
                    INSERT INTO discord_guild (guild_id, guild_name, guild_score)
                    SELECT guild_id, MAX(guild_name), :score
                    FROM discord_invite_candidate
                    WHERE guild_id = :guild_id AND resolve_status = 'ok'
                    GROUP BY guild_id
                    ON CONFLICT (guild_id) DO UPDATE
                    SET guild_score = :score, updated_at = NOW()
                """),
                {
                    "guild_id": guild.guild_id,
                    "score": best_score
                }
            )
            results["guilds_ranked"] += 1
        
        db.commit()
        
        logger.info(
            f"Ranked Discord candidates: candidates={results['candidates_ranked']}, "
            f"guilds={results['guilds_ranked']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Error in rank_discord_candidates_task: {e}", exc_info=True)
        db.rollback()
        results["status"] = "error"
        results["errors"] = [str(e)]
        return results


def _calculate_quality_score(
    member_count: int,
    online_count: int,
    guild_name: str,
    channel_name: str,
    source_type: str,
    source_url: str,
    is_expired: bool
) -> float:
    """
    Calculate quality score for a Discord invite candidate.
    
    Args:
        member_count: Approximate member count
        online_count: Approximate online count
        guild_name: Guild name
        channel_name: Channel name
        source_type: Source type
        source_url: Source URL
        is_expired: Whether invite is expired
        
    Returns:
        Quality score (float)
    """
    weights = QUALITY_SCORE_WEIGHTS
    score = 0.0
    
    # Base score from member count
    if member_count > 0:
        score += math.log10(member_count + 1) * weights["member_count_base"]
    
    # Base score from online count
    if online_count > 0:
        score += math.log10(online_count + 1) * weights["online_count_base"]
    
    # Channel keyword bonus
    channel_text = (guild_name + " " + channel_name).lower()
    if any(keyword in channel_text for keyword in PUBLISHER_INTENT_KEYWORDS):
        score += weights["channel_keyword_bonus"]
    
    # Source bonus (reddit + publisher)
    if source_type == "reddit" and "publisher" in (source_url or "").lower():
        score += weights["source_reddit_publisher_bonus"]
    
    # Small guild penalty
    if member_count > 0 and member_count < 50:
        score += weights["small_guild_penalty"]
    
    # Expired penalty
    if is_expired:
        score += weights["expired_penalty"]
    
    return max(0.0, score)  # Don't go below 0
