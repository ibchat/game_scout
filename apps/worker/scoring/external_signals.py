"""
External Signals Scoring
Формулы для расчёта EWI и EPV
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def compute_ewi(
    rank: int,
    rank_delta_24h: Optional[int] = None,
    rank_delta_7d: Optional[int] = None,
    source: str = "top_wishlisted",
    max_rank: int = 100
) -> Tuple[float, float]:
    """Вычислить EWI (External Wishlist Index) 0-100"""
    base_score = max(0, 100 - (rank / max_rank) * 50)
    
    momentum = 0
    if rank_delta_24h:
        momentum += rank_delta_24h * 2
    if rank_delta_7d:
        momentum += rank_delta_7d * 1
    
    source_weight = 1.0 if source == "top_wishlisted" else 0.8
    
    ewi = (base_score + momentum) * source_weight
    ewi = max(0, min(100, ewi))
    
    if rank <= 10:
        confidence = 0.9
    elif rank <= 50:
        confidence = 0.7
    else:
        confidence = 0.5
    
    return round(ewi, 1), confidence


def compute_epv(
    youtube_signal: Optional[dict] = None,
    tiktok_signal: Optional[dict] = None,
    narrative_alignment: Optional[float] = None,
    weights: dict = None
) -> Tuple[float, float]:
    """Вычислить EPV (External Pattern Validation) 0-100"""
    if weights is None:
        weights = {'youtube': 0.4, 'tiktok': 0.3, 'alignment': 0.3}
    
    scores = []
    total_weight = 0
    confidence_factors = []
    
    # YouTube Score
    if youtube_signal:
        yt_engagement = youtube_signal.get('engagement', 0)
        yt_intent = youtube_signal.get('intent_ratio', 0.5)
        yt_confusion = youtube_signal.get('confusion_ratio', 0)
        
        yt_score = (
            min(yt_engagement * 100, 100) *
            yt_intent *
            (1 - yt_confusion)
        )
        
        scores.append(yt_score * weights['youtube'])
        total_weight += weights['youtube']
        confidence_factors.append(0.7)
    
    # TikTok Score
    if tiktok_signal:
        tt_engagement = tiktok_signal.get('engagement', 0)
        tt_virality = tiktok_signal.get('virality', 0)
        
        tt_score = (
            min(tt_engagement * 100, 100) *
            min(tt_virality * 10, 1)
        )
        
        scores.append(tt_score * weights['tiktok'])
        total_weight += weights['tiktok']
        confidence_factors.append(0.7)
    
    # Narrative Alignment
    if narrative_alignment is not None:
        alignment_score = narrative_alignment * 100
        scores.append(alignment_score * weights['alignment'])
        total_weight += weights['alignment']
        confidence_factors.append(0.8)
    
    if total_weight == 0:
        return 0.0, 0.0
    
    epv = sum(scores) / total_weight
    epv = max(0, min(100, epv))
    confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
    
    return round(epv, 1), round(confidence, 2)
