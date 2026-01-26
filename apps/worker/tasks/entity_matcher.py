"""
Entity Matching: Match raw events to Steam games using aliases.
Uses normalized text matching with fuzzy fallback for confidence scoring.
"""
import logging
import re
from typing import Optional, Tuple, List, Dict
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Minimum confidence threshold for matching
MIN_CONFIDENCE = 0.80

# Maximum fuzzy match confidence (fuzzy is always lower than exact)
MAX_FUZZY_CONFIDENCE = 0.85

# Minimum alias length for fuzzy matching
MIN_FUZZY_ALIAS_LENGTH = 6


def normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, remove special chars, collapse spaces"""
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Remove special characters but keep spaces
    text = re.sub(r'[^\w\s]', '', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def find_exact_match(normalized_text: str, db: Session) -> Optional[Tuple[int, float, str]]:
    """
    Find exact alias match in normalized text.
    Returns: (steam_app_id, confidence, reason) or None
    """
    # Split text into words for word boundary matching
    words = normalized_text.split()
    
    # Try to find aliases that appear as whole words
    # Query: find aliases that are contained in text with word boundaries
    query = """
        SELECT DISTINCT ON (steam_app_id)
            steam_app_id,
            alias,
            alias_type,
            weight
        FROM steam_app_aliases
        WHERE :text LIKE '%' || alias || '%'
          AND LENGTH(alias) >= 4
        ORDER BY steam_app_id, weight DESC, LENGTH(alias) DESC
    """
    
    results = db.execute(text(query), {"text": normalized_text}).mappings().all()
    
    if not results:
        return None
    
    # Score matches by alias quality
    best_match = None
    best_score = 0.0
    
    for result in results:
        alias = result["alias"]
        alias_type = result["alias_type"]
        weight = result.get("weight", 1)
        steam_app_id = result["steam_app_id"]
        
        # Check if alias appears as whole word (word boundary)
        # Simple check: alias surrounded by space or start/end of string
        pattern = r'\b' + re.escape(alias) + r'\b'
        if re.search(pattern, normalized_text):
            # Calculate confidence based on alias type and length
            base_confidence = {
                "official": 0.98,
                "common": 0.95,
                "abbrev": 0.90,
                "short": 0.88,
            }.get(alias_type, 0.85)
            
            # Adjust by alias length (longer = more confident)
            length_bonus = min(0.05, len(alias) * 0.002)
            confidence = min(0.98, base_confidence + length_bonus)
            
            # Weight adjustment
            confidence = confidence * (0.9 + weight * 0.01)
            
            if confidence > best_score:
                best_score = confidence
                best_match = (steam_app_id, confidence, f"exact_match_{alias_type}")
    
    if best_match and best_match[1] >= MIN_CONFIDENCE:
        return best_match
    
    return None


def find_fuzzy_match(normalized_text: str, db: Session) -> Optional[Tuple[int, float, str]]:
    """
    Find fuzzy alias match using SequenceMatcher.
    Only for longer aliases to avoid false positives.
    Returns: (steam_app_id, confidence, reason) or None
    """
    # Get candidate aliases (longer ones only)
    query = """
        SELECT DISTINCT steam_app_id, alias, alias_type, weight
        FROM steam_app_aliases
        WHERE LENGTH(alias) >= :min_length
          AND alias_type IN ('official', 'common')
        ORDER BY weight DESC, LENGTH(alias) DESC
        LIMIT 500
    """
    
    candidates = db.execute(
        text(query),
        {"min_length": MIN_FUZZY_ALIAS_LENGTH}
    ).mappings().all()
    
    if not candidates:
        return None
    
    best_match = None
    best_ratio = 0.0
    
    # Extract potential game name from text (first 3-5 words)
    words = normalized_text.split()
    text_candidate = ' '.join(words[:5]) if len(words) > 5 else normalized_text
    
    for candidate in candidates:
        alias = candidate["alias"]
        steam_app_id = candidate["steam_app_id"]
        alias_type = candidate["alias_type"]
        
        # Use SequenceMatcher for similarity
        ratio = SequenceMatcher(None, text_candidate, alias).ratio()
        
        # Only consider if ratio is high enough
        if ratio > 0.75 and ratio > best_ratio:
            # Convert ratio to confidence (capped at MAX_FUZZY_CONFIDENCE)
            confidence = min(MAX_FUZZY_CONFIDENCE, ratio * 0.95)
            
            # Only accept if above minimum threshold
            if confidence >= MIN_CONFIDENCE:
                best_ratio = ratio
                best_match = (
                    steam_app_id,
                    confidence,
                    f"fuzzy_match_{alias_type}_ratio_{ratio:.2f}"
                )
    
    return best_match


def match_event_to_game(
    event_title: str,
    event_body: Optional[str],
    db: Session
) -> Optional[Tuple[int, float, str]]:
    """
    Match a raw event (title + body) to a Steam game.
    Returns: (steam_app_id, confidence, reason) or None if no match above threshold
    """
    if not event_title:
        return None
    
    # Combine title and body for matching
    combined_text = event_title
    if event_body:
        combined_text = f"{event_title} {event_body}"
    
    normalized = normalize_text(combined_text)
    
    if not normalized or len(normalized) < 4:
        return None
    
    # Try exact match first
    exact_match = find_exact_match(normalized, db)
    if exact_match:
        return exact_match
    
    # Try fuzzy match if exact failed
    fuzzy_match = find_fuzzy_match(normalized, db)
    if fuzzy_match:
        return fuzzy_match
    
    return None


def match_events_batch(
    events: List[Dict],
    db: Session,
    batch_size: int = 100
) -> Dict[str, int]:
    """
    Match a batch of events to games.
    events: list of {id, title, body, ...}
    Returns: {matched, unmatched, errors}
    """
    matched = 0
    unmatched = 0
    errors = 0
    
    for event in events:
        event_id = event.get("id")
        title = event.get("title", "")
        body = event.get("body")
        
        try:
            match_result = match_event_to_game(title, body, db)
            
            if match_result:
                steam_app_id, confidence, reason = match_result
                
                # Update event with match
                db.execute(
                    text("""
                        UPDATE trends_raw_events
                        SET matched_steam_app_id = :app_id,
                            match_confidence = :confidence,
                            match_reason = :reason
                        WHERE id = :event_id
                    """),
                    {
                        "event_id": event_id,
                        "app_id": steam_app_id,
                        "confidence": confidence,
                        "reason": reason
                    }
                )
                matched += 1
            else:
                unmatched += 1
        
        except Exception as e:
            logger.warning(f"match_event_error event_id={event_id} error={e}")
            errors += 1
            continue
    
    db.commit()
    
    return {
        "matched": matched,
        "unmatched": unmatched,
        "errors": errors
    }


if __name__ == "__main__":
    from apps.db.session import get_db_session
    
    # Test matching
    db = get_db_session()
    try:
        test_title = "Baldur's Gate 3 gets major update"
        result = match_event_to_game(test_title, None, db)
        print(f"Match result: {result}")
    finally:
        db.close()
