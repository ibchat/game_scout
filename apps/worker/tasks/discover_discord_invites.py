"""
Discord Invite Discovery Task
Discovers Discord invite links from public sources
"""
import os
import logging
import time
import requests
from typing import Dict, Any, List
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.worker.integrations.discord_invite_extractor import extract_discord_invites, normalize_invite_code, build_invite_url

logger = logging.getLogger(__name__)

# Configuration
DISCOVERY_SOURCES_ENABLED = os.getenv("DISCOVERY_SOURCES_ENABLED", "disboard,topgg,reddit,manual").split(",")
DISCOVERY_MAX_CANDIDATES_PER_RUN = int(os.getenv("DISCOVERY_MAX_CANDIDATES_PER_RUN", "200"))
DISCOVERY_RPS = float(os.getenv("DISCOVERY_RPS", "0.5"))  # Requests per second per domain

# Manual seed URLs from env
MANUAL_SEED_URLS = os.getenv("DISCORD_MANUAL_INVITES", "").split(",")
MANUAL_SEED_URLS = [url.strip() for url in MANUAL_SEED_URLS if url.strip()]


@celery_app.task(name="discover_discord_invites_task")
def discover_discord_invites_task(
    source_type: str,
    seed_url_or_query: str = None,
    max_candidates: int = None
) -> Dict[str, Any]:
    """
    Discover Discord invite links from a public source.
    
    Args:
        source_type: Type of source (disboard, topgg, discordme, reddit, twitter, website, manual)
        seed_url_or_query: URL or query string for the source
        max_candidates: Maximum number of candidates to discover in this run
        
    Returns:
        {
            "status": "ok",
            "source_type": str,
            "candidates_found": int,
            "candidates_new": int,
            "candidates_existing": int,
            "errors": []
        }
    """
    db = get_db_session()
    results = {
        "status": "ok",
        "source_type": source_type,
        "candidates_found": 0,
        "candidates_new": 0,
        "candidates_existing": 0,
        "errors": []
    }
    
    if max_candidates is None:
        max_candidates = DISCOVERY_MAX_CANDIDATES_PER_RUN
    
    try:
        # Check if source is enabled
        if source_type not in DISCOVERY_SOURCES_ENABLED:
            results["status"] = "skipped"
            results["errors"].append(f"Source type '{source_type}' is not enabled")
            return results
        
        # Fetch content based on source type
        invite_codes = []
        
        if source_type == "manual":
            invite_codes = _discover_from_manual_seeds(seed_url_or_query, max_candidates)
        elif source_type == "disboard":
            invite_codes = _discover_from_disboard(seed_url_or_query, max_candidates)
        elif source_type == "topgg":
            invite_codes = _discover_from_topgg(seed_url_or_query, max_candidates)
        elif source_type == "reddit":
            invite_codes = _discover_from_reddit(seed_url_or_query, max_candidates)
        else:
            results["errors"].append(f"Unsupported source type: {source_type}")
            return results
        
        # Store candidates
        for code in invite_codes[:max_candidates]:
            normalized_code = normalize_invite_code(code)
            if not normalized_code:
                continue
            
            invite_url = build_invite_url(normalized_code)
            
            try:
                # Check if already exists
                existing = db.execute(
                    text("SELECT id FROM discord_invite_candidate WHERE invite_code = :code"),
                    {"code": normalized_code}
                ).scalar()
                
                if existing:
                    results["candidates_existing"] += 1
                    continue
                
                # Insert new candidate
                db.execute(
                    text("""
                        INSERT INTO discord_invite_candidate (
                            invite_code, invite_url, source_type, source_url, found_at, resolve_status
                        ) VALUES (
                            :code, :url, :source_type, :source_url, NOW(), 'new'
                        )
                    """),
                    {
                        "code": normalized_code,
                        "url": invite_url,
                        "source_type": source_type,
                        "source_url": seed_url_or_query
                    }
                )
                db.commit()
                results["candidates_new"] += 1
                results["candidates_found"] += 1
                
            except IntegrityError:
                db.rollback()
                results["candidates_existing"] += 1
            except Exception as e:
                db.rollback()
                logger.warning(f"Error storing candidate {normalized_code}: {e}")
                results["errors"].append(f"Error storing {normalized_code}: {str(e)}")
        
        logger.info(
            f"Discord invite discovery: source={source_type}, "
            f"found={results['candidates_found']}, "
            f"new={results['candidates_new']}, "
            f"existing={results['candidates_existing']}"
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Error in discover_discord_invites_task: {e}", exc_info=True)
        results["status"] = "error"
        results["errors"].append(str(e))
        return results


def _discover_from_manual_seeds(seed_url: str = None, max_candidates: int = 200) -> List[str]:
    """Discover invites from manual seed URLs or env DISCORD_MANUAL_INVITES"""
    invite_codes = []
    
    # If seed_url provided, extract from it
    if seed_url:
        codes = extract_discord_invites(seed_url)
        invite_codes.extend(codes)
    
    # Extract from env DISCORD_MANUAL_INVITES (comma-separated list)
    for invite_input in MANUAL_SEED_URLS:
        if not invite_input:
            continue
        # Can be either URL or just invite code
        if invite_input.startswith("http"):
            codes = extract_discord_invites(invite_input)
            invite_codes.extend(codes)
        elif "discord.gg" in invite_input or "discord.com/invite" in invite_input:
            codes = extract_discord_invites(invite_input)
            invite_codes.extend(codes)
        else:
            # Assume it's just a code, normalize it
            normalized = normalize_invite_code(invite_input)
            if normalized:
                invite_codes.append(normalized)
    
    return invite_codes[:max_candidates]


def _discover_from_disboard(query: str = None, max_candidates: int = 200) -> List[str]:
    """Discover invites from Disboard (MVP: placeholder)"""
    # TODO: Implement Disboard scraping
    # For now, return empty list
    logger.info("Disboard discovery not yet implemented")
    return []


def _discover_from_topgg(query: str = None, max_candidates: int = 200) -> List[str]:
    """Discover invites from top.gg (MVP: placeholder)"""
    # TODO: Implement top.gg scraping
    logger.info("top.gg discovery not yet implemented")
    return []


def _discover_from_reddit(query: str = None, max_candidates: int = 200) -> List[str]:
    """Discover invites from Reddit posts (MVP: placeholder)"""
    # TODO: Implement Reddit API scraping
    logger.info("Reddit discovery not yet implemented")
    return []
