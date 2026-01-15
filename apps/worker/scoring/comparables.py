from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from apps.db.models import Game, GameMetricsDaily
from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Compute Jaccard similarity between two sets"""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def tokenize(text: str) -> Set[str]:
    """Simple tokenization for keyword matching"""
    if not text:
        return set()
    # Basic tokenization - lowercase and split on non-alphanumeric
    import re
    tokens = re.findall(r'\b\w+\b', text.lower())
    # Filter out common words
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were'}
    return {t for t in tokens if len(t) > 2 and t not in stopwords}


def find_comparables(
    db: Session,
    pitch_tags: List[str],
    pitch_text: str,
    hook_text: str = None,
    limit: int = 20
) -> List[Dict]:
    """
    Find comparable games using Jaccard similarity on tags and keyword matching
    """
    logger.info(f"Finding comparables for pitch with {len(pitch_tags)} tags")
    
    # Normalize pitch tags
    pitch_tag_set = {tag.lower().strip() for tag in pitch_tags if tag}
    
    # Tokenize pitch text for keyword matching
    pitch_keywords = tokenize(pitch_text)
    if hook_text:
        pitch_keywords.update(tokenize(hook_text))
    
    # Get all games with their latest metrics
    stmt = select(Game)
    games = db.execute(stmt).scalars().all()
    
    if not games:
        logger.warning("No games found in database")
        return []
    
    # Score each game
    scored_games = []
    
    for game in games:
        try:
            # Jaccard on tags
            game_tag_set = {tag.lower().strip() for tag in game.tags if tag}
            tag_similarity = jaccard_similarity(pitch_tag_set, game_tag_set)
            
            # Keyword match on name and description
            game_text = f"{game.name} {game.short_description or ''}"
            game_keywords = tokenize(game_text)
            keyword_similarity = jaccard_similarity(pitch_keywords, game_keywords)
            
            # Combined score (weighted)
            combined_score = (tag_similarity * 0.7) + (keyword_similarity * 0.3)
            
            if combined_score > 0:
                # Get latest metrics
                stmt = select(GameMetricsDaily).where(
                    GameMetricsDaily.game_id == game.id
                ).order_by(GameMetricsDaily.date.desc()).limit(1)
                
                latest_metric = db.execute(stmt).scalar_one_or_none()
                
                comparable = {
                    "game_id": str(game.id),
                    "name": game.name,
                    "url": game.url,
                    "source": game.source.value,
                    "tags": game.tags,
                    "release_date": str(game.release_date) if game.release_date else None,
                    "price_eur": float(game.price_eur) if game.price_eur else None,
                    "similarity_score": round(combined_score, 3),
                    "reviews_total": latest_metric.reviews_total if latest_metric else 0,
                    "rating_percent": latest_metric.rating_percent if latest_metric else None
                }
                
                scored_games.append(comparable)
        
        except Exception as e:
            logger.warning(f"Error scoring game {game.name}: {e}")
            continue
    
    # Sort by similarity score and limit
    scored_games.sort(key=lambda x: x["similarity_score"], reverse=True)
    top_comparables = scored_games[:limit]
    
    logger.info(f"Found {len(top_comparables)} comparables")
    
    return top_comparables