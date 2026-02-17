"""
Discord Invite Resolve Task
Resolves Discord invite codes to get guild metadata via Discord API
"""
import os
import logging
import time
import requests
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text
import json

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session

logger = logging.getLogger(__name__)

# Configuration
RESOLVE_RPS = float(os.getenv("RESOLVE_RPS", "1.0"))  # Requests per second
RESOLVE_BATCH_SIZE = int(os.getenv("RESOLVE_BATCH_SIZE", "50"))


@celery_app.task(name="resolve_discord_invite_task")
def resolve_discord_invite_task(invite_code: str) -> Dict[str, Any]:
    """
    Resolve a Discord invite code to get guild metadata.
    
    Uses Discord API endpoint:
    GET https://discord.com/api/v10/invites/{invite_code}?with_counts=true&with_expiration=true
    
    Args:
        invite_code: Discord invite code (e.g., "abc123")
        
    Returns:
        {
            "status": "ok" | "error",
            "invite_code": str,
            "resolve_status": str,
            "http_status": int,
            "guild_id": str | None,
            "guild_name": str | None,
            "errors": []
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "invite_code": invite_code,
        "resolve_status": "error",
        "http_status": None,
        "guild_id": None,
        "guild_name": None,
        "errors": []
    }
    
    try:
        bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        if not bot_token:
            results["status"] = "error"
            results["errors"].append("DISCORD_BOT_TOKEN not configured")
            return results
        
        # Rate limiting
        time.sleep(1.0 / RESOLVE_RPS)
        
        # Discord API endpoint
        url = f"https://discord.com/api/v10/invites/{invite_code}?with_counts=true&with_expiration=true"
        headers = {
            "Authorization": f"Bot {bot_token}",
            "User-Agent": "GameScout/1.0 (https://gamescout.app, v1)"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        http_status = response.status_code
        results["http_status"] = http_status
        
        # Process response
        if http_status == 200:
            data = response.json()
            
            # Extract guild info
            guild = data.get("guild", {})
            guild_id = guild.get("id")
            guild_name = guild.get("name")
            guild_icon = guild.get("icon")
            guild_icon_url = f"https://cdn.discordapp.com/icons/{guild_id}/{guild_icon}.png" if guild_icon else None
            
            # Extract counts
            approx_member_count = data.get("approximate_member_count")
            approx_online_count = data.get("approximate_presence_count")
            
            # Extract channel info
            channel = data.get("channel", {})
            channel_id = channel.get("id")
            channel_name = channel.get("name")
            
            # Extract expiration
            expires_at = None
            if data.get("expires_at"):
                try:
                    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            
            # Update candidate record
            db.execute(
                text("""
                    UPDATE discord_invite_candidate
                    SET 
                        last_resolved_at = NOW(),
                        resolve_status = 'ok',
                        resolve_http_status = :http_status,
                        guild_id = :guild_id,
                        guild_name = :guild_name,
                        guild_icon_url = :guild_icon_url,
                        approx_member_count = :member_count,
                        approx_online_count = :online_count,
                        channel_id = :channel_id,
                        channel_name = :channel_name,
                        expires_at = :expires_at,
                        raw_invite_json = :raw_json
                    WHERE invite_code = :code
                """),
                {
                    "code": invite_code,
                    "http_status": http_status,
                    "guild_id": guild_id,
                    "guild_name": guild_name,
                    "guild_icon_url": guild_icon_url,
                    "member_count": approx_member_count,
                    "online_count": approx_online_count,
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "expires_at": expires_at,
                    "raw_json": data
                }
            )
            
            # STEP C: Upsert guild if resolve_status=ok
            if guild_id and guild_name:
                db.execute(
                    text("""
                        INSERT INTO discord_guild (
                            guild_id, guild_name, discovered_via_invite_code,
                            guild_score, is_active, raw_metadata, created_at, updated_at
                        ) VALUES (
                            :guild_id, :guild_name, :invite_code,
                            :guild_score, true, :raw_metadata, NOW(), NOW()
                        )
                        ON CONFLICT (guild_id) DO UPDATE
                        SET 
                            guild_name = :guild_name,
                            discovered_via_invite_code = COALESCE(discord_guild.discovered_via_invite_code, :invite_code),
                            updated_at = NOW(),
                            raw_metadata = :raw_metadata
                    """),
                    {
                        "guild_id": guild_id,
                        "guild_name": guild_name,
                        "invite_code": invite_code,
                        "guild_score": 0.0,  # Will be calculated by ranking task
                        "raw_metadata": {
                            "approx_member_count": approx_member_count,
                            "approx_online_count": approx_online_count,
                            "guild_icon_url": guild_icon_url,
                            "resolved_at": datetime.utcnow().isoformat()
                        }
                    }
                )
            
            db.commit()
            
            results["resolve_status"] = "ok"
            results["guild_id"] = guild_id
            results["guild_name"] = guild_name
            
            logger.info(f"Resolved invite {invite_code}: guild={guild_name} ({guild_id})")
            
        elif http_status == 404:
            # Invalid or expired
            resolve_status = "expired" if "expires_at" in response.text.lower() else "invalid"
            db.execute(
                text("""
                    UPDATE discord_invite_candidate
                    SET 
                        last_resolved_at = NOW(),
                        resolve_status = :status,
                        resolve_http_status = :http_status
                    WHERE invite_code = :code
                """),
                {
                    "code": invite_code,
                    "status": resolve_status,
                    "http_status": http_status
                }
            )
            db.commit()
            results["resolve_status"] = resolve_status
            
        elif http_status == 429:
            # Rate limited
            results["resolve_status"] = "rate_limited"
            db.execute(
                text("""
                    UPDATE discord_invite_candidate
                    SET 
                        last_resolved_at = NOW(),
                        resolve_status = 'rate_limited',
                        resolve_http_status = :http_status
                    WHERE invite_code = :code
                """),
                {
                    "code": invite_code,
                    "http_status": http_status
                }
            )
            db.commit()
            results["errors"].append("Rate limited by Discord API")
            
        elif http_status == 403:
            # Forbidden
            results["resolve_status"] = "forbidden"
            db.execute(
                text("""
                    UPDATE discord_invite_candidate
                    SET 
                        last_resolved_at = NOW(),
                        resolve_status = 'forbidden',
                        resolve_http_status = :http_status
                    WHERE invite_code = :code
                """),
                {
                    "code": invite_code,
                    "http_status": http_status
                }
            )
            db.commit()
            
        else:
            # Other error
            results["resolve_status"] = "error"
            db.execute(
                text("""
                    UPDATE discord_invite_candidate
                    SET 
                        last_resolved_at = NOW(),
                        resolve_status = 'error',
                        resolve_http_status = :http_status
                    WHERE invite_code = :code
                """),
                {
                    "code": invite_code,
                    "http_status": http_status
                }
            )
            db.commit()
            results["errors"].append(f"HTTP {http_status}: {response.text[:200]}")
        
        return results
        
    except Exception as e:
        logger.error(f"Error resolving invite {invite_code}: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        
        # Update candidate with error status
        try:
            db.execute(
                text("""
                    UPDATE discord_invite_candidate
                    SET 
                        last_resolved_at = NOW(),
                        resolve_status = 'error'
                    WHERE invite_code = :code
                """),
                {"code": invite_code}
            )
            db.commit()
        except Exception:
            db.rollback()
        
        return results
