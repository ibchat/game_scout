"""
Discord Discovery API Endpoints
Endpoints for invite discovery, candidate management, and bot onboarding
"""
import os
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session
from apps.worker.config.discord_discovery_config import (
    DISCORD_BOT_CLIENT_ID,
    DISCORD_BOT_PERMISSIONS,
    DISCORD_BOT_SCOPES
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/discord/discovery", tags=["discord-discovery"])


@router.get("/candidates")
async def get_discord_candidates(
    status: Optional[str] = Query(None, description="Filter by resolve_status (ok, new, invalid, etc.)"),
    min_score: Optional[float] = Query(None, description="Minimum quality_score"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of candidates to return"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get Discord invite candidates with ranking.
    
    Returns list of candidates with bot invite URLs.
    """
    try:
        query = """
            SELECT 
                invite_code, invite_url, source_type, source_url,
                guild_id, guild_name, guild_icon_url,
                approx_member_count, approx_online_count,
                channel_name, quality_score, resolve_status
            FROM discord_invite_candidate
            WHERE 1=1
        """
        params = {}
        
        if status:
            query += " AND resolve_status = :status"
            params["status"] = status
        
        if min_score is not None:
            query += " AND quality_score >= :min_score"
            params["min_score"] = min_score
        
        query += " ORDER BY quality_score DESC, found_at DESC LIMIT :limit"
        params["limit"] = limit
        
        candidates = db.execute(text(query), params).fetchall()
        
        # Build response with bot invite URLs
        result_candidates = []
        for candidate in candidates:
            bot_invite_url = _make_bot_invite_url(candidate.guild_id) if candidate.guild_id else None
            
            result_candidates.append({
                "invite_code": candidate.invite_code,
                "invite_url": candidate.invite_url,
                "source_type": candidate.source_type,
                "source_url": candidate.source_url,
                "guild_id": candidate.guild_id,
                "guild_name": candidate.guild_name,
                "guild_icon_url": candidate.guild_icon_url,
                "approx_member_count": candidate.approx_member_count,
                "approx_online_count": candidate.approx_online_count,
                "channel_name": candidate.channel_name,
                "quality_score": float(candidate.quality_score or 0),
                "resolve_status": candidate.resolve_status,
                "bot_invite_url": bot_invite_url
            })
        
        return {
            "status": "ok",
            "count": len(result_candidates),
            "candidates": result_candidates
        }
        
    except Exception as e:
        logger.error(f"Error getting Discord candidates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guilds")
async def get_discord_guilds(
    is_active: Optional[bool] = Query(None, description="Filter by is_active"),
    min_score: Optional[float] = Query(None, description="Minimum guild_score"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of guilds to return"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get Discord guilds with ranking.
    """
    try:
        query = """
            SELECT 
                guild_id, guild_name, discovered_via_invite_code,
                added_bot, bot_joined_at, last_channels_sync_at,
                guild_score, is_active, tags
            FROM discord_guild
            WHERE 1=1
        """
        params = {}
        
        if is_active is not None:
            query += " AND is_active = :is_active"
            params["is_active"] = is_active
        
        if min_score is not None:
            query += " AND guild_score >= :min_score"
            params["min_score"] = min_score
        
        query += " ORDER BY guild_score DESC, created_at DESC LIMIT :limit"
        params["limit"] = limit
        
        guilds = db.execute(text(query), params).fetchall()
        
        result_guilds = []
        for guild in guilds:
            result_guilds.append({
                "guild_id": guild.guild_id,
                "guild_name": guild.guild_name,
                "discovered_via_invite_code": guild.discovered_via_invite_code,
                "added_bot": guild.added_bot,
                "bot_joined_at": str(guild.bot_joined_at) if guild.bot_joined_at else None,
                "last_channels_sync_at": str(guild.last_channels_sync_at) if guild.last_channels_sync_at else None,
                "guild_score": float(guild.guild_score or 0),
                "is_active": guild.is_active,
                "tags": guild.tags or []
            })
        
        return {
            "status": "ok",
            "count": len(result_guilds),
            "guilds": result_guilds
        }
        
    except Exception as e:
        logger.error(f"Error getting Discord guilds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _make_bot_invite_url(guild_id: Optional[str] = None) -> Optional[str]:
    """
    Generate Discord bot invite URL.
    
    Args:
        guild_id: Optional guild ID to pre-select server
        
    Returns:
        Bot invite URL or None if client_id not configured
    """
    if not DISCORD_BOT_CLIENT_ID:
        return None
    
    base_url = f"https://discord.com/api/oauth2/authorize"
    params = {
        "client_id": DISCORD_BOT_CLIENT_ID,
        "permissions": DISCORD_BOT_PERMISSIONS,
        "scope": "+".join(DISCORD_BOT_SCOPES)
    }
    
    if guild_id:
        params["guild_id"] = guild_id
    
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{param_str}"
