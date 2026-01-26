"""
Generate aliases for Steam games from steam_app_cache.
Idempotent script that creates normalized aliases for entity matching.
"""
import logging
import re
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Common stop words that shouldn't be used as aliases alone
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
    'game', 'games', 'inside', 'life', 'world', 'war', 'battle', 'fight', 'story', 'tale',
    'adventure', 'quest', 'journey', 'legend', 'myth', 'hero', 'heroes', 'king', 'queen',
    'prince', 'princess', 'dragon', 'monster', 'beast', 'creature', 'magic', 'spell', 'sword',
    'shield', 'armor', 'weapon', 'item', 'treasure', 'gold', 'coin', 'money', 'shop', 'store'
}


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


def generate_aliases_from_name(name: str) -> List[Dict[str, str]]:
    """
    Generate aliases from a game name.
    Returns list of {alias, alias_type} dicts.
    """
    if not name or not name.strip():
        return []
    
    aliases = []
    normalized = normalize_text(name)
    
    if not normalized:
        return []
    
    # 1. Full normalized name (official)
    aliases.append({
        "alias": normalized,
        "alias_type": "official",
        "weight": 10
    })
    
    # 2. Remove common suffixes
    suffixes_to_remove = [
        r'\s+game\s+of\s+the\s+year\s+edition$',
        r'\s+goty\s+edition$',
        r'\s+definitive\s+edition$',
        r'\s+complete\s+edition$',
        r'\s+deluxe\s+edition$',
        r'\s+ultimate\s+edition$',
        r'\s+remastered$',
        r'\s+remaster$',
        r'\s+edition$',
        r'\s+™$',
        r'\s+®$',
        r'\s+©$',
    ]
    
    cleaned = normalized
    for suffix_pattern in suffixes_to_remove:
        cleaned = re.sub(suffix_pattern, '', cleaned, flags=re.IGNORECASE)
    
    if cleaned != normalized and cleaned:
        aliases.append({
            "alias": cleaned.strip(),
            "alias_type": "common",
            "weight": 8
        })
    
    # 3. Remove "The" prefix
    if cleaned.startswith('the '):
        without_the = cleaned[4:].strip()
        if without_the:
            aliases.append({
                "alias": without_the,
                "alias_type": "common",
                "weight": 7
            })
    
    # 4. Extract main words (if name has multiple words)
    words = cleaned.split()
    if len(words) > 1:
        # First 2-3 words as abbreviation
        if len(words) >= 2:
            abbrev = ' '.join(words[:2])
            if len(abbrev) >= 6:  # Only if meaningful length
                aliases.append({
                    "alias": abbrev,
                    "alias_type": "abbrev",
                    "weight": 5
                })
        
        # Last word (if not stop word)
        last_word = words[-1]
        if last_word not in STOP_WORDS and len(last_word) >= 4:
            aliases.append({
                "alias": last_word,
                "alias_type": "short",
                "weight": 3
            })
    
    # 5. Single word names (if not stop word and >= 4 chars)
    if len(words) == 1 and words[0] not in STOP_WORDS and len(words[0]) >= 4:
        # Already added as official, but can add as "short" too
        if normalized not in [a["alias"] for a in aliases]:
            aliases.append({
                "alias": normalized,
                "alias_type": "short",
                "weight": 6
            })
    
    return aliases


def generate_aliases_for_all_games(db: Session, limit: Optional[int] = None) -> Dict[str, int]:
    """
    Generate aliases for all games in steam_app_cache.
    Idempotent: uses INSERT ... ON CONFLICT DO NOTHING.
    
    Returns: {inserted, skipped, errors}
    """
    logger.info("generate_aliases_start")
    
    try:
        # Get all games with names
        query = """
            SELECT DISTINCT steam_app_id, name
            FROM steam_app_cache
            WHERE name IS NOT NULL
              AND name != ''
              AND name != 'Unknown'
            ORDER BY steam_app_id
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        games = db.execute(text(query)).mappings().all()
        
        inserted = 0
        skipped = 0
        errors = 0
        
        for game in games:
            steam_app_id = game["steam_app_id"]
            name = game["name"]
            
            try:
                aliases = generate_aliases_from_name(name)
                
                for alias_data in aliases:
                    alias_text = alias_data["alias"]
                    alias_type = alias_data["alias_type"]
                    weight = alias_data.get("weight", 1)
                    
                    # Skip very short aliases (except if official)
                    if alias_type != "official" and len(alias_text) < 4:
                        continue
                    
                    # Skip stop words (except if official)
                    if alias_type != "official" and alias_text in STOP_WORDS:
                        continue
                    
                    # Insert alias (idempotent)
                    result = db.execute(
                        text("""
                            INSERT INTO steam_app_aliases (steam_app_id, alias, alias_type, weight)
                            VALUES (:steam_app_id, :alias, :alias_type, :weight)
                            ON CONFLICT (steam_app_id, alias) DO NOTHING
                        """),
                        {
                            "steam_app_id": steam_app_id,
                            "alias": alias_text,
                            "alias_type": alias_type,
                            "weight": weight
                        }
                    )
                    
                    if result.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1
            
            except Exception as e:
                logger.warning(f"generate_aliases_error steam_app_id={steam_app_id} name='{name}' error={e}")
                errors += 1
                continue
        
        db.commit()
        
        stats = {
            "inserted": inserted,
            "skipped": skipped,
            "errors": errors,
            "games_processed": len(games)
        }
        
        logger.info(f"generate_aliases_done {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"generate_aliases_fail error={e}", exc_info=True)
        db.rollback()
        return {"inserted": 0, "skipped": 0, "errors": 1, "games_processed": 0}


if __name__ == "__main__":
    from apps.db.session import get_db_session
    
    db = get_db_session()
    try:
        stats = generate_aliases_for_all_games(db)
        print(f"Generated aliases: {stats}")
    finally:
        db.close()
