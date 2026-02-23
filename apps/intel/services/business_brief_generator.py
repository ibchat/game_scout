"""
Business Brief Generator for Intel Events
Generates structured business briefs from extracted content.
Rules-based, no LLM for classification. Translation support.
"""
import logging
import re
from typing import Dict, Any, Optional, List, Tuple
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


def translate_to_russian(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Translate text to Russian.
    Uses free translation service (LibreTranslate).
    If translation fails, returns Russian template "нет данных" (strict rule).
    
    STRICT RULE: Must return Russian text, never original non-Russian text.
    
    IMPROVED: Always translates if text contains significant English content (>20% Latin).
    
    Returns:
        Tuple of (translated_text, meta_dict)
    """
    if not text:
        return "нет данных", {"translation_failed": True, "error": "empty_text"}
    
    # Check if already Russian - improved detection
    detected = detect_language(text)
    
    # CRITICAL: If detected as 'en' or 'other', always translate
    # Even if detected as 'ru', check if there's significant English content
    import re
    latin_count = sum(1 for char in text if ('\u0041' <= char <= '\u005A') or ('\u0061' <= char <= '\u007A'))
    total_alpha = len([c for c in text if c.isalpha()])
    latin_ratio = latin_count / total_alpha if total_alpha > 0 else 0
    
    # If significant English content (>20%), always translate
    if detected != "ru" or latin_ratio > 0.2:
        # Try to translate using free service
        try:
            from apps.intel.services.translation.free_translate import translate_to_ru, TranslationError
            # Force detection as 'en' if mixed
            source_lang = detected if detected != "ru" else ("en" if latin_ratio > 0.2 else "ru")
            translated, meta = translate_to_ru(text, source_lang)
            # Verify translation is actually Russian
            if detect_language(translated) == "ru":
                meta["translation_failed"] = False
                return translated, meta
            else:
                logger.warning(f"Translation result is not Russian, using fallback template")
                return "нет данных", {"translation_failed": True, "error": "translation_not_russian", **meta}
        except TranslationError as e:
            logger.error(f"Translation failed: {e}, using fallback template")
            # Return Russian template instead of original text (strict rule)
            return "нет данных", {"translation_failed": True, "error": str(e)}
        except Exception as e:
            logger.error(f"Translation failed: {e}, using fallback template")
            # Return Russian template instead of original text (strict rule)
            return "нет данных", {"translation_failed": True, "error": str(e)}
    
    # Truly Russian text
    return text, {"translation_failed": False, "detected_lang": "ru", "already_russian": True}


def normalize_to_ru(brief: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize all text fields in brief to Russian.
    
    Args:
        brief: Brief dict with title, what_happened, why_it_matters, key_points, etc.
    
    Returns:
        Normalized brief with all text fields guaranteed to be Russian.
        If translation fails for critical fields (title, what_happened), 
        sets translation_failed flag in meta.
    """
    normalized = brief.copy()
    translation_meta = brief.get("translation_meta", {})
    
    # Normalize title (critical field)
    title = brief.get("title", "")
    if title and detect_language(title) != "ru":
        title, title_meta = translate_to_russian(title)
        normalized["title"] = title
        translation_meta["title_meta"] = title_meta
        if title_meta.get("translation_failed"):
            translation_meta["translation_failed"] = True
    
    # Normalize what_happened (critical field)
    what_happened = brief.get("what_happened", "")
    if what_happened and detect_language(what_happened) != "ru":
        what_happened, what_meta = translate_to_russian(what_happened)
        normalized["what_happened"] = what_happened
        translation_meta["what_meta"] = what_meta
        if what_meta.get("translation_failed"):
            translation_meta["translation_failed"] = True
    
    # Normalize why_it_matters (non-critical, can be "нет данных")
    why_it_matters = brief.get("why_it_matters", "нет данных")
    if why_it_matters and why_it_matters != "нет данных" and detect_language(why_it_matters) != "ru":
        why_it_matters, why_meta = translate_to_russian(why_it_matters)
        normalized["why_it_matters"] = why_it_matters
        translation_meta["why_meta"] = why_meta
    
    # Normalize key_points
    key_points = brief.get("key_points", [])
    key_points_ru = []
    key_points_meta = []
    for point in key_points:
        if point and detect_language(point) != "ru":
            translated_point, point_meta = translate_to_russian(point)
            # Editorial rewrite
            from apps.intel.services.editorial_rewriter import rewrite_editorial_ru
            translated_point = rewrite_editorial_ru(translated_point, event_type=normalized.get("signal_type"), score=normalized.get("significance_score"))
            key_points_ru.append(translated_point)
            key_points_meta.append(point_meta)
        else:
            # Editorial rewrite even for Russian text
            if point:
                from apps.intel.services.editorial_rewriter import rewrite_editorial_ru
                point = rewrite_editorial_ru(point, event_type=normalized.get("signal_type"), score=normalized.get("significance_score"))
            key_points_ru.append(point)
            key_points_meta.append({"translation_failed": False, "already_russian": True})
    
    normalized["key_points"] = key_points_ru
    translation_meta["key_points_meta"] = key_points_meta
    
    # Editorial rewrite for executive_summary if exists
    executive_summary = normalized.get("executive_summary", "")
    if executive_summary:
        from apps.intel.services.editorial_rewriter import rewrite_editorial_ru
        executive_summary = rewrite_editorial_ru(executive_summary, event_type=normalized.get("signal_type"), score=normalized.get("significance_score"))
        normalized["executive_summary"] = executive_summary
    
    # Editorial rewrite for what_happened (critical field, enforce quality)
    if normalized.get("what_happened") and normalized["what_happened"] != "нет данных":
        from apps.intel.services.editorial_rewriter import rewrite_editorial_ru, enforce_editorial_quality
        what_happened = rewrite_editorial_ru(normalized["what_happened"], event_type=normalized.get("signal_type"), score=normalized.get("significance_score"))
        what_happened = enforce_editorial_quality(what_happened, max_iterations=2)
        normalized["what_happened"] = what_happened
    
    # Editorial rewrite for why_it_matters
    if normalized.get("why_it_matters") and normalized["why_it_matters"] != "нет данных":
        from apps.intel.services.editorial_rewriter import rewrite_editorial_ru
        why_it_matters = rewrite_editorial_ru(normalized["why_it_matters"], event_type=normalized.get("signal_type"), score=normalized.get("significance_score"))
        normalized["why_it_matters"] = why_it_matters
    
    # Editorial rewrite for title
    if normalized.get("title"):
        from apps.intel.services.editorial_rewriter import rewrite_editorial_ru
        title = rewrite_editorial_ru(normalized["title"], event_type=normalized.get("signal_type"), score=normalized.get("significance_score"))
        normalized["title"] = title
    
    normalized["translation_meta"] = translation_meta
    normalized["language"] = "ru"
    
    return normalized


def generate_executive_summary(text: str, max_length: int = 200, event_type: Optional[str] = None, score: Optional[int] = None) -> str:
    """
    Generate executive summary from text.
    
    Rules:
    - 1-2 sentences
    - Maximum 240 characters
    - No filler words
    - Strictly Russian
    - No evaluative adjectives
    
    Args:
        text: Source text
        max_length: Maximum length in characters
    
    Returns:
        Executive summary string
    """
    if not text or text == "нет данных":
        return ""
    
    # Remove HTML tags if present
    import re
    text_clean = re.sub(r'<[^>]+>', '', text)
    
    # Split into sentences
    sentences = re.split(r'[.!?]\s+', text_clean)
    
    # Filter out very short sentences
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if not sentences:
        return ""
    
    # Take first 1-2 sentences
    summary_parts = []
    total_length = 0
    
    for sentence in sentences[:2]:
        sentence_clean = sentence.strip()
        # Remove common filler phrases
        filler_patterns = [
            r'^кстати,?\s*',
            r'^вообще,?\s*',
            r'^в общем,?\s*',
            r'^так что,?\s*',
            r'^итак,?\s*',
            r'^ну,?\s*',
        ]
        for pattern in filler_patterns:
            sentence_clean = re.sub(pattern, '', sentence_clean, flags=re.IGNORECASE)
        
        sentence_clean = sentence_clean.strip()
        
        # Check if adding this sentence would exceed limit
        if summary_parts:
            potential_length = total_length + len(sentence_clean) + 2  # +2 for ". "
        else:
            potential_length = len(sentence_clean)
        
        if potential_length <= max_length:
            summary_parts.append(sentence_clean)
            total_length = potential_length
        else:
            # Truncate last sentence if needed
            if summary_parts:
                remaining = max_length - total_length - 2
                if remaining > 20:
                    truncated = sentence_clean[:remaining] + "..."
                    summary_parts.append(truncated)
            break
    
    if not summary_parts:
        # Fallback: truncate first sentence
        first_sentence = sentences[0][:max_length - 3] + "..."
        return first_sentence
    
    summary = ". ".join(summary_parts)
    if not summary.endswith(('.', '!', '?')):
        summary += "."
    
    # Final length check
    if len(summary) > max_length:
        summary = summary[:max_length - 3] + "..."
    
    # Editorial rewrite for better quality
    from apps.intel.services.editorial_rewriter import rewrite_editorial_ru
    summary = rewrite_editorial_ru(summary, event_type=event_type, score=score)
    
    # Ensure it answers "и что?" - add context if missing
    if event_type and score:
        # For high-score events, ensure summary has impact
        if score >= 70 and not any(word in summary.lower() for word in ['может', 'может быть', 'вероятно', 'это', 'это означает']):
            # Try to add impact context (but keep it short)
            if len(summary) < max_length - 50:
                if event_type == "release":
                    summary = summary.rstrip('.') + " — это может изменить рынок."
                elif event_type == "funding":
                    summary = summary.rstrip('.') + " — инвесторы видят потенциал."
                elif event_type == "controversy":
                    summary = summary.rstrip('.') + " — это может повлиять на репутацию."
    
    # Final length check after additions
    if len(summary) > max_length:
        summary = summary[:max_length - 3] + "..."
    
    return summary


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
    
    # Translate to Russian if needed (strict rule: all output must be Russian)
    if detect_language(source_text) != "ru":
        source_text, source_meta = translate_to_russian(source_text)
        # If translation failed, source_text is now "нет данных" (Russian template)
    
    # Classify signal type (rules-based)
    signal_type = classify_signal_type(source_text)
    
    # Extract key points (only if we have actual text, not "нет данных")
    key_points = []
    if source_text and source_text != "нет данных":
        key_points = extract_key_points(source_text, max_points=5)
        if not key_points:
            # Fallback: split into sentences
            sentences = re.split(r'[.!?]\s+', source_text)
            key_points = [s.strip() for s in sentences[:3] if s.strip() and len(s.strip()) > 20]
    
    # Build brief (all fields must be Russian)
    # CRITICAL: Always translate, even if title_ru exists (it might be partial English)
    title_raw = event.title_ru[:100] if event.title_ru else (event.title_en[:100] if hasattr(event, 'title_en') and event.title_en else "Новость Steam")
    what_happened_raw = event.what_happened_ru or (source_text[:500] if source_text != "нет данных" else "нет данных")
    why_it_matters_raw = event.why_it_matters_ru or "нет данных"
    
    # Normalize all fields to Russian (B1: unified normalization)
    # Always translate to ensure Russian, even if field seems Russian
    title, title_meta = translate_to_russian(title_raw)
    what_happened, what_meta = translate_to_russian(what_happened_raw)
    if why_it_matters_raw != "нет данных":
        why_it_matters, why_meta = translate_to_russian(why_it_matters_raw)
    else:
        why_it_matters = "нет данных"
        why_meta = {"translation_failed": False, "already_russian": True}
    
    # Translate key points if needed
    key_points_ru = []
    key_points_meta = []
    for point in key_points:
        if detect_language(point) != "ru":
            translated_point, point_meta = translate_to_russian(point)
            key_points_ru.append(translated_point)
            key_points_meta.append(point_meta)
        else:
            key_points_ru.append(point)
            key_points_meta.append({"translation_failed": False, "already_russian": True})
    
    # Add translation metadata
    translation_meta = {
        "translation_applied": any([
            not title_meta.get("already_russian", False),
            not what_meta.get("already_russian", False),
            not why_meta.get("already_russian", False),
            any(not m.get("already_russian", False) for m in key_points_meta)
        ]),
        "translation_failed": any([
            title_meta.get("translation_failed", False),
            what_meta.get("translation_failed", False),
            why_meta.get("translation_failed", False),
            any(m.get("translation_failed", False) for m in key_points_meta)
        ]),
        "title_meta": title_meta,
        "what_meta": what_meta,
        "why_meta": why_meta,
        "key_points_meta": key_points_meta
    }
    
    # Generate executive summary from what_happened (analytical, answers "и что?")
    executive_summary = ""
    event_score = event.significance_score if hasattr(event, 'significance_score') else 0
    if what_happened and what_happened != "нет данных":
        executive_summary = generate_executive_summary(
            what_happened,
            max_length=200,  # Reduced from 240 for denser text
            event_type=signal_type,
            score=event_score
        )
        # Ensure Russian
        if executive_summary and detect_language(executive_summary) != "ru":
            executive_summary_ru, exec_meta = translate_to_russian(executive_summary)
            executive_summary = executive_summary_ru
            translation_meta["executive_summary_meta"] = exec_meta
    
    # Generate insight line (light humor) for ALL events
    # More neutral for low scores, more impactful for high scores
    from apps.intel.services.insight_generator import generate_insight_line
    insight_line = generate_insight_line(
        event_type=signal_type,
        score=event_score,
        title=title
    )
    
    return {
        "title": title,
        "executive_summary": executive_summary,
        "what_happened": what_happened[:1000],  # Limit length
        "why_it_matters": why_it_matters[:500] if why_it_matters != "нет данных" else "нет данных",
        "key_points": key_points_ru[:5],
        "insight_line": insight_line,  # Light humor for high-score events
        "signal_type": signal_type,
        "source_url": source_url,
        "significance_score": event_score,  # Add score for editorial rewriter
        "language": "ru",
        "translation_meta": translation_meta
    }
