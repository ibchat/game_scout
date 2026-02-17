"""
Sync Guild Channels Task
Syncs channels from a Discord guild after bot is added
"""
import os
import logging
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import text

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.integrations.discord_scraper import DiscordScraper
from apps.worker.config.discord_discovery_config import AUTO_CHANNEL_PICK_TOP_K, DISCORD_BOT_CLIENT_ID, DISCORD_BOT_PERMISSIONS, DISCORD_BOT_SCOPES

logger = logging.getLogger(__name__)


@celery_app.task(name="sync_guild_channels_task")
def sync_guild_channels_task(guild_id: str) -> Dict[str, Any]:
    """
    Sync channels from a Discord guild after bot is added.
    
    Gets list of channels, marks visible ones, and auto-enables top-K for scanning.
    
    Args:
        guild_id: Discord guild ID
        
    Returns:
        {
            "status": "ok",
            "guild_id": str,
            "channels_found": int,
            "channels_visible": int,
            "channels_enabled": int
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "guild_id": guild_id,
        "channels_found": 0,
        "channels_visible": 0,
        "channels_enabled": 0,
        "errors": []
    }
    
    try:
        bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        if not bot_token:
            results["status"] = "error"
            results["errors"].append("DISCORD_BOT_TOKEN not configured")
            return results
        
        scraper = DiscordScraper(bot_token=bot_token)
        
        # Get guild info
        guild_name = None
        try:
            guild_info = scraper.get_guild_info(guild_id)
            guild_name = guild_info.get("name")
        except Exception as e:
            logger.warning(f"Could not get guild info for {guild_id}: {e}")
        
        # Get guild channels
        channels = scraper.get_guild_channels(guild_id)
        results["channels_found"] = len(channels)
        
        # Update guild record
        db.execute(
            text("""
                UPDATE discord_guild
                SET 
                    added_bot = true,
                    bot_joined_at = COALESCE(bot_joined_at, NOW()),
                    last_channels_sync_at = NOW(),
                    updated_at = NOW()
                WHERE guild_id = :guild_id
            """),
            {"guild_id": guild_id}
        )
        
        # Insert/update channels (only text/forum/announcement types)
        channel_scores = []
        text_channel_types = [0, 4, 5]  # 0 = text, 4 = forum, 5 = announcement
        
        for channel in channels:
            channel_id = channel.get("id")
            channel_name = channel.get("name", "")
            channel_type = channel.get("type", 0)
            
            # Only process text/forum/announcement channels
            if channel_type not in text_channel_types:
                continue
            
            # Map channel type
            type_map = {
                0: "text",
                4: "forum",
                5: "announcement"
            }
            channel_type_str = type_map.get(channel_type, "text")
            
            # Check if channel is visible (bot can see it)
            is_visible = channel_id is not None
            
            # Calculate activity score (simple heuristic)
            activity_score = 0.0
            if channel_name:
                # Keywords boost
                keywords = ["pitch", "publisher", "jobs", "collab", "dev", "gamedev", "indie"]
                if any(kw in channel_name.lower() for kw in keywords):
                    activity_score += 5.0
                
                # Channel type boost
                if channel_type_str in ["forum", "announcement"]:
                    activity_score += 3.0
            
            channel_scores.append((channel_id, activity_score))
            
            # Insert or update channel
            db.execute(
                text("""
                    INSERT INTO discord_channel (
                        channel_id, guild_id, channel_name, channel_type,
                        is_visible_to_bot, activity_score, raw_metadata
                    ) VALUES (
                        :channel_id, :guild_id, :channel_name, :channel_type,
                        :is_visible, :activity_score, :raw_metadata
                    )
                    ON CONFLICT (channel_id) DO UPDATE
                    SET 
                        channel_name = :channel_name,
                        channel_type = :channel_type,
                        is_visible_to_bot = :is_visible,
                        activity_score = :activity_score,
                        raw_metadata = :raw_metadata,
                        updated_at = NOW()
                """),
                {
                    "channel_id": channel_id,
                    "guild_id": guild_id,
                    "channel_name": channel_name,
                    "channel_type": channel_type_str,
                    "is_visible": is_visible,
                    "activity_score": activity_score,
                    "raw_metadata": channel
                }
            )
            
            if is_visible:
                results["channels_visible"] += 1
                results["channels_found"] += 1
        
        # STEP E: Auto-pick top-K channels for scanning (eligible_for_scan = scan_enabled)
        channel_scores.sort(key=lambda x: x[1], reverse=True)
        top_channels = [ch_id for ch_id, _ in channel_scores[:AUTO_CHANNEL_PICK_TOP_K]]
        
        if top_channels:
            db.execute(
                text("""
                    UPDATE discord_channel
                    SET scan_enabled = true, priority = 1
                    WHERE channel_id = ANY(:channel_ids)
                """),
                {"channel_ids": top_channels}
            )
            results["channels_enabled"] = len(top_channels)
        else:
            # If no channels scored, enable first N text channels
            first_channels = [ch_id for ch_id, _ in channel_scores[:min(5, len(channel_scores))]]
            if first_channels:
                db.execute(
                    text("""
                        UPDATE discord_channel
                        SET scan_enabled = true, priority = 1
                        WHERE channel_id = ANY(:channel_ids)
                    """),
                    {"channel_ids": first_channels}
                )
                results["channels_enabled"] = len(first_channels)
        
        db.commit()
        
        logger.info(
            f"Synced guild channels: guild={guild_id}, "
            f"found={results['channels_found']}, "
            f"visible={results['channels_visible']}, "
            f"enabled={results['channels_enabled']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Error syncing guild channels for {guild_id}: {e}", exc_info=True)
        db.rollback()
        results["status"] = "error"
        results["errors"].append(str(e))
        return results


def _make_bot_invite_url(guild_id: str = None) -> str:
    """
    Generate Discord bot invite URL.
    
    Args:
        guild_id: Optional guild ID to pre-select server
        
    Returns:
        Bot invite URL or empty string if client_id not configured
    """
    if not DISCORD_BOT_CLIENT_ID:
        return ""
    
    base_url = "https://discord.com/api/oauth2/authorize"
    params = {
        "client_id": DISCORD_BOT_CLIENT_ID,
        "permissions": DISCORD_BOT_PERMISSIONS,
        "scope": "+".join(DISCORD_BOT_SCOPES)
    }
    
    if guild_id:
        params["guild_id"] = guild_id
    
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{base_url}?{param_str}"
