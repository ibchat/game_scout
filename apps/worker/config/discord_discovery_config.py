"""
Discord Discovery Configuration
Configuration for invite discovery, ranking, and onboarding
"""
import os

# Discovery Sources
DISCOVERY_SOURCES_ENABLED = os.getenv("DISCOVERY_SOURCES_ENABLED", "disboard,topgg,reddit,manual").split(",")
DISCOVERY_MAX_CANDIDATES_PER_RUN = int(os.getenv("DISCOVERY_MAX_CANDIDATES_PER_RUN", "200"))
DISCOVERY_RPS = float(os.getenv("DISCOVERY_RPS", "0.5"))  # Requests per second per domain

# Resolve Configuration
RESOLVE_BATCH_SIZE = int(os.getenv("RESOLVE_BATCH_SIZE", "50"))
RESOLVE_RPS = float(os.getenv("RESOLVE_RPS", "1.0"))  # Requests per second

# Ranking Configuration
GUILDS_TARGET_SHORTLIST = int(os.getenv("GUILDS_TARGET_SHORTLIST", "50"))
AUTO_CHANNEL_PICK_TOP_K = int(os.getenv("AUTO_CHANNEL_PICK_TOP_K", "8"))

# Quality Score Weights (can be adjusted)
QUALITY_SCORE_WEIGHTS = {
    "member_count_base": 2.0,  # log10(members+1) * weight
    "online_count_base": 3.0,  # log10(online+1) * weight
    "channel_keyword_bonus": 2.0,  # +2 if channel name contains keywords
    "source_reddit_publisher_bonus": 1.0,  # +1 if source is reddit and contains "publisher"
    "small_guild_penalty": -3.0,  # -3 if members < 50
    "expired_penalty": -2.0,  # -2 if invite expired
}

# Keywords for scoring
PUBLISHER_INTENT_KEYWORDS = [
    "publisher", "pitch", "jobs", "collab", "collaboration",
    "dev", "gamedev", "indie", "unity", "unreal", "game dev"
]

# Bot Invite Configuration
DISCORD_BOT_CLIENT_ID = os.getenv("DISCORD_BOT_CLIENT_ID", "")
DISCORD_BOT_PERMISSIONS = 1024 | 8192  # View Channels (1024) + Read Message History (8192)
DISCORD_BOT_SCOPES = ["bot"]
