"""
Business Brief Generator for Intel Events
Generates structured business briefs from extracted content.
Rules-based, no LLM for classification. Translation support.
"""
import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from apps.intel.db.models import IntelEvent, IntelExtractedItem
from apps.intel.policy.policy_engine import load_policy

logger = logging.getLogger(__name__)


def classify_signal_type(text: str) -> str:
    """
    Rules-based classification of signal type.
    No LLM used - pure pattern matching.
    
    Returns: release, patch_major, discount, publisher_deal, funding, market_trend, other
    """
    text_lower = text.lower()
    
    # release patterns
    if any(pattern in text_lower for pattern in ["launch", "released", "out now", "выход", "запуск", "выпуск"]):
        return "release"
    
    # patch_major patterns
    if any(pattern in text_lower for pattern in ["major update", "overhaul", "2.0", "3.0", "большое обновление", "крупное обновление"]):
        return "patch_major"
    
    # discount patterns
    if any(pattern in text_lower for pattern in ["% off", "discount", "sale", "скидка", "распродажа", "со скидкой"]):
        return "discount"
    
    # publisher_deal patterns
    if any(pattern in text_lower for pattern in ["publisher", "publishing deal", "издатель", "издательская сделка"]):
        return "publisher_deal"
    
    # funding patterns
    if any(pattern in text_lower for pattern in ["funding", "investment", "raised", "финансирование", "инвестиции", "привлек"]):
        return "funding"
    
    # market_trend patterns
    if any(pattern in text_lower for pattern in ["chart", "ranking", "peak players", "топ", "рейтинг", "пик игроков"]):
        return "market_trend"
    
    return "other"


def detect_language(text: str) -> str:
    """
    Simple language detection (Russian vs non-Russian).
    Returns: "ru" or "en" (default to en for non-Russian)
    """
    # Check for Cyrillic characters
    if re.search(r'[а-яА-ЯёЁ]', text):
        return "ru"
    return "en"


def translate_to_russian(text: str) -> str:
    """
    Translate text to Russian using LLM if available.
    Falls back to original text if translation fails.
    """
    if detect_language(text) == "ru":
        return text
    
    try:
        from apps.worker.llm.client import get_llm_client
        
        llm_client = get_llm_client()
        if llm_client:
            prompt = f"""Переведи следующий текст на русский язык. Сохрани деловой стиль, без эмоций, только факты.

Текст:
{text[:2000]}

Переведи строго на русский, сохраняя факты без изменений:"""
            
            translated = llm_client.generate(prompt, max_tokens=2000, temperature=0.2)
            if translated:
                return translated.strip()
    except Exception as e:
        logger.warning(f"Translation failed: {e}, using original text")
    
    return text  # Fallback to original


def extract_key_points(text: str, max_points: int = 5) -> List[str]:
    """
    Extract key points from text using simple rules.
    Looks for bullet points, numbered lists, or sentence breaks.
    """
    points = []
    
    # Try to find bullet points or numbered lists
    bullet_pattern = r'[•\-\*]\s*(.+?)(?=\n|$)'
    numbered_pattern = r'\d+[\.\)]\s*(.+?)(?=\n|$)'
    
    bullets = re.findall(bullet_pattern, text, re.MULTILINE)
    numbered = re.findall(numbered_pattern, text, re.MULTILINE)
    
    if bullets:
        points = [b.strip() for b in bullets[:max_points]]
    elif numbered:
        points = [n.strip() for n in numbered[:max_points]]
    else:
        # Split by sentences and take first N
        sentences = re.split(r'[.!?]\s+', text)
        points = [s.strip() for s in sentences[:max_points] if s.strip() and len(s.strip()) > 20]
    
    # Filter out very short points
    points = [p for p in points if len(p) > 15]
    
    return points[:max_points]


def generate_business_brief(event: IntelEvent, db_session) -> Dict[str, Any]:
    """
    Generate business brief for Intel event.
    Rules-based, no LLM for classification.
    
    Returns JSON structure:
    {
      "title": "...",
      "what_happened": "...",
      "why_it_matters": "...",
      "key_points": ["...", "..."],
      "signal_type": "release|patch_major|...",
      "source_url": "...",
      "language": "ru"
    }
    """
    policy = load_policy()
    
    # Get extracted items for this event
    extracted_texts = []
    source_urls = []
    
    if event.cluster_id:
        from apps.intel.db.models import IntelCluster
        cluster = db_session.query(IntelCluster).filter(
            IntelCluster.id == event.cluster_id
        ).first()
        
        if cluster:
            # Get extracted item from cluster
            extracted_item = db_session.query(IntelExtractedItem).filter(
                IntelExtractedItem.id == cluster.representative_extracted_id
            ).first()
            
            if extracted_item:
                if extracted_item.text:
                    extracted_texts.append(extracted_item.text)
                if extracted_item.url_norm:
                    source_urls.append(extracted_item.url_norm)
    
    # Fallback: use existing event fields
    if not extracted_texts:
        extracted_texts = [event.what_happened_ru or event.title_ru or ""]
    
    # Get source URL
    source_url = source_urls[0] if source_urls else (event.sources[0] if event.sources and isinstance(event.sources, list) else (str(event.sources) if event.sources else ""))
    
    # Combine extracted text
    source_text = "\n\n".join(extracted_texts[:5])  # Max 5 items
    
    # Translate to Russian if needed
    if detect_language(source_text) != "ru":
        source_text = translate_to_russian(source_text)
    
    # Classify signal type (rules-based)
    signal_type = classify_signal_type(source_text)
    
    # Extract key points
    key_points = extract_key_points(source_text, max_points=5)
    if not key_points:
        # Fallback: split into sentences
        sentences = re.split(r'[.!?]\s+', source_text)
        key_points = [s.strip() for s in sentences[:3] if s.strip() and len(s.strip()) > 20]
    
    # Build brief
    title = event.title_ru[:100] if event.title_ru else "Новость Steam"
    what_happened = event.what_happened_ru or source_text[:500] or "нет данных"
    why_it_matters = event.why_it_matters_ru or "нет данных"
    
    # Ensure Russian
    if detect_language(title) != "ru":
        title = translate_to_russian(title)
    if detect_language(what_happened) != "ru":
        what_happened = translate_to_russian(what_happened)
    if detect_language(why_it_matters) != "ru" and why_it_matters != "нет данных":
        why_it_matters = translate_to_russian(why_it_matters)
    
    # Translate key points if needed
    key_points_ru = []
    for point in key_points:
        if detect_language(point) != "ru":
            key_points_ru.append(translate_to_russian(point))
        else:
            key_points_ru.append(point)
    
    return {
        "title": title,
        "what_happened": what_happened[:1000],  # Limit length
        "why_it_matters": why_it_matters[:500] if why_it_matters != "нет данных" else "нет данных",
        "key_points": key_points_ru[:5],
        "signal_type": signal_type,
        "source_url": source_url,
        "language": "ru"
    }
