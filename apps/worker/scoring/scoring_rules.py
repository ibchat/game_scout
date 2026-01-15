from sqlalchemy.orm import Session
from sqlalchemy import select
from apps.db.models import Pitch, TrendsDaily
from typing import Dict, List, Tuple
from datetime import date
import logging

logger = logging.getLogger(__name__)


def clamp(value: float, min_val: float, max_val: float) -> int:
    """Clamp value between min and max and convert to int"""
    return int(max(min_val, min(max_val, value)))


def compute_hook_score(pitch: Pitch) -> Tuple[int, List[str]]:
    """
    Hook score (0-25)
    """
    score = 0
    reasons = []
    
    if pitch.hook_one_liner:
        score += 7
        reasons.append("Clear hook one-liner provided")
    
    if pitch.video_link:
        score += 7
        reasons.append("Video link included")
    
    if pitch.build_link:
        score += 7
        reasons.append("Playable build provided")
    
    if len(pitch.pitch_text) >= 200:
        score += 4
        reasons.append("Detailed pitch description")
    
    return clamp(score, 0, 25), reasons


def compute_market_score(
    db: Session,
    pitch: Pitch,
    comparables: List[Dict]
) -> Tuple[int, List[str]]:
    """
    Market & trends score (0-25)
    """
    score = 0
    reasons = []
    
    # Trending tag match (0-15)
    if pitch.tags:
        today = date.today()
        stmt = select(TrendsDaily).where(
            TrendsDaily.date == today
        ).order_by(TrendsDaily.velocity.desc())
        
        trends = db.execute(stmt).scalars().all()
        
        trending_tags = {t.signal: t.velocity for t in trends if t.velocity > 0}
        
        matching_tags = []
        trend_score = 0
        
        for tag in pitch.tags:
            normalized_tag = tag.lower().strip()
            if normalized_tag in trending_tags:
                velocity = trending_tags[normalized_tag]
                # Weight by velocity (cap at 5 per tag)
                tag_weight = min(5, velocity / 2)
                trend_score += tag_weight
                matching_tags.append(tag)
        
        trend_score = min(15, trend_score)
        score += int(trend_score)
        
        if matching_tags:
            reasons.append(f"Matches trending tags: {', '.join(matching_tags[:3])}")
    
    # Comparable survivability (0-10)
    if comparables:
        top_10 = comparables[:10]
        successful_games = [c for c in top_10 if c.get("reviews_total", 0) >= 200]
        
        if len(successful_games) >= 3:
            score += 10
            reasons.append("Multiple successful comparables (200+ reviews)")
        elif len(successful_games) >= 1:
            score += 5
            reasons.append("Some successful comparables found")
    
    return clamp(score, 0, 25), reasons


def compute_team_score(pitch: Pitch) -> Tuple[int, List[str]]:
    """
    Team execution score (0-20)
    """
    score = 0
    reasons = []
    
    if pitch.released_before:
        score += 10
        reasons.append("Team has prior release experience")
    
    if pitch.team_size <= 2:
        score += 5
        reasons.append("Lean team size (≤2)")
    
    if pitch.timeline_months <= 12:
        score += 5
        reasons.append("Realistic timeline (≤12 months)")
    
    return clamp(score, 0, 20), reasons


def compute_steam_score(pitch: Pitch) -> Tuple[int, List[str]]:
    """
    Steam viability score (0-20)
    """
    score = 0
    reasons = []
    
    if pitch.build_link:
        score += 10
        reasons.append("Playable build available")
    
    if pitch.video_link:
        score += 5
        reasons.append("Video showcase provided")
    
    if len(pitch.tags) >= 3:
        score += 5
        reasons.append("Well-tagged (≥3 tags)")
    
    return clamp(score, 0, 20), reasons


def compute_asymmetry_score(
    pitch: Pitch,
    comparables: List[Dict]
) -> Tuple[int, List[str]]:
    """
    Asymmetry score (0-10) - upside potential
    """
    score = 0
    reasons = []
    
    # Small team + fast timeline = nimble execution
    if pitch.timeline_months <= 12 and pitch.team_size <= 2:
        score += 5
        reasons.append("Nimble execution potential")
    
    # At least one highly successful comparable
    if comparables:
        highly_successful = [c for c in comparables if c.get("reviews_total", 0) >= 1000]
        if highly_successful:
            score += 5
            reasons.append("Category has proven breakout potential")
    
    return clamp(score, 0, 10), reasons


def compute_total_score(
    db: Session,
    pitch: Pitch,
    comparables: List[Dict]
) -> Dict:
    """
    Compute all scores and return breakdown
    """
    hook_score, hook_reasons = compute_hook_score(pitch)
    market_score, market_reasons = compute_market_score(db, pitch, comparables)
    team_score, team_reasons = compute_team_score(pitch)
    steam_score, steam_reasons = compute_steam_score(pitch)
    asymmetry_score, asymmetry_reasons = compute_asymmetry_score(pitch, comparables)
    
    total_score = hook_score + market_score + team_score + steam_score + asymmetry_score
    total_score = clamp(total_score, 0, 100)
    
    return {
        "score_total": total_score,
        "score_hook": hook_score,
        "score_market": market_score,
        "score_team": team_score,
        "score_steam": steam_score,
        "score_asymmetry": asymmetry_score,
        "reasons": {
            "hook": hook_reasons,
            "market": market_reasons,
            "team": team_reasons,
            "steam": steam_reasons,
            "asymmetry": asymmetry_reasons
        }
    }