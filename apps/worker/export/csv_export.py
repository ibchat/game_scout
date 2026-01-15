import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import select
from apps.db.models import TrendsDaily, Pitch, PitchScore
from datetime import date
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)


def export_trends_csv(db: Session, export_dir: str, target_date: date = None) -> str:
    """Export trends to CSV"""
    if target_date is None:
        target_date = date.today()
    
    # Ensure export directory exists
    Path(export_dir).mkdir(parents=True, exist_ok=True)
    
    # Query trends
    stmt = select(TrendsDaily).where(
        TrendsDaily.date == target_date
    ).order_by(TrendsDaily.velocity.desc())
    
    trends = db.execute(stmt).scalars().all()
    
    if not trends:
        logger.warning(f"No trends found for {target_date}")
        return None
    
    # Convert to DataFrame
    data = []
    for trend in trends:
        data.append({
            "date": trend.date,
            "signal": trend.signal,
            "signal_type": trend.signal_type.value,
            "count": trend.count,
            "avg_7d": float(trend.avg_7d),
            "delta_7d": float(trend.delta_7d),
            "velocity": float(trend.velocity)
        })
    
    df = pd.DataFrame(data)
    
    # Export
    filename = f"trends_{target_date.strftime('%Y-%m-%d')}.csv"
    filepath = os.path.join(export_dir, filename)
    df.to_csv(filepath, index=False)
    
    logger.info(f"Exported {len(trends)} trends to {filepath}")
    return filepath


def export_pitches_csv(db: Session, export_dir: str, target_date: date = None) -> str:
    """Export pitches to CSV"""
    if target_date is None:
        target_date = date.today()
    
    # Ensure export directory exists
    Path(export_dir).mkdir(parents=True, exist_ok=True)
    
    # Query pitches with scores
    stmt = select(Pitch).join(
        PitchScore, Pitch.id == PitchScore.pitch_id, isouter=True
    ).order_by(Pitch.created_at.desc())
    
    pitches = db.execute(stmt).scalars().all()
    
    if not pitches:
        logger.warning("No pitches found")
        return None
    
    # Convert to DataFrame
    data = []
    for pitch in pitches:
        row = {
            "created_at": pitch.created_at,
            "dev_name": pitch.dev_name,
            "email": pitch.email,
            "studio_name": pitch.studio_name or "",
            "team_size": pitch.team_size,
            "released_before": pitch.released_before,
            "timeline_months": pitch.timeline_months,
            "tags": ", ".join(pitch.tags) if pitch.tags else "",
            "status": pitch.status.value
        }
        
        if pitch.score:
            row.update({
                "score_total": pitch.score.score_total,
                "verdict": pitch.score.verdict.value,
                "top_comparables": ", ".join([c["name"] for c in pitch.score.comparables[:3]]),
                "why_yes": " | ".join(pitch.score.why_yes),
                "why_no": " | ".join(pitch.score.why_no),
                "next_step": pitch.score.next_step or ""
            })
        else:
            row.update({
                "score_total": None,
                "verdict": "",
                "top_comparables": "",
                "why_yes": "",
                "why_no": "",
                "next_step": ""
            })
        
        data.append(row)
    
    df = pd.DataFrame(data)
    
    # Export
    filename = f"pitches_{target_date.strftime('%Y-%m-%d')}.csv"
    filepath = os.path.join(export_dir, filename)
    df.to_csv(filepath, index=False)
    
    logger.info(f"Exported {len(pitches)} pitches to {filepath}")
    return filepath