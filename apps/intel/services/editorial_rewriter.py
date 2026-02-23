"""
Editorial Rewriter
Post-processing layer to improve machine translation quality.
Makes text read like natural Russian editorial content, not translated RSS.
"""
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# Common translation calques to replace
CALQUES_REPLACEMENTS = {
    # Passive voice -> Active
    r'\bбыл выпущен\b': 'вышел',
    r'\bбыла выпущена\b': 'вышла',
    r'\bбыло выпущено\b': 'вышло',
    r'\bбыл объявлен\b': 'объявили',
    r'\bбыла объявлена\b': 'объявили',
    r'\bбыло объявлено\b': 'объявили',
    r'\bбыл добавлен\b': 'добавили',
    r'\bбыла добавлена\b': 'добавили',
    r'\bбыло добавлено\b': 'добавили',
    r'\bбыл обновлён\b': 'обновили',
    r'\bбыла обновлена\b': 'обновили',
    r'\bбыло обновлено\b': 'обновили',
    
    # Fix translation artifacts
    r"не был't\b": "не был",
    r"был't\b": "был",
    r"не't\b": "не",
    r"\'t\b": "",  # Remove stray 't
    r"\'s\b": "",  # Remove stray 's
    r"\'m\b": "",  # Remove stray 'm
    r"\'re\b": "",  # Remove stray 're
    r"\'ve\b": "",  # Remove stray 've
    r"\'ll\b": "",  # Remove stray 'll
    r"\'d\b": "",  # Remove stray 'd
    
    # English calques
    r'\bрелиз\b': 'выход',  # Only if not part of "Early Access" or game name
    r'\bапдейт\b': 'обновление',
    r'\bпатч\b': 'обновление',
    r'\bгеймер\b': 'игрок',
    r'\bгеймеры\b': 'игроки',
    r'\bгейминг\b': 'игры',
    r'\bгайд\b': 'руководство',
    r'\bгайды\b': 'руководства',
    
    # Redundant phrases
    r'\bследует отметить,?\s*что\b': '',
    r'\bстоит отметить,?\s*что\b': '',
    r'\bважно отметить,?\s*что\b': '',
    r'\bследует сказать,?\s*что\b': '',
    r'\bнужно сказать,?\s*что\b': '',
    r'\bможно сказать,?\s*что\b': '',
    r'\bсогласно информации\b': '',
    r'\bсогласно данным\b': '',
    r'\bсогласно сообщению\b': '',
    r'\bв соответствии с\b': '',
    
    # Wordy constructions
    r'\bв настоящее время\b': 'сейчас',
    r'\bна данный момент\b': 'сейчас',
    r'\bв данный момент\b': 'сейчас',
    r'\bна сегодняшний день\b': 'сейчас',
    r'\bв связи с тем,?\s*что\b': 'так как',
    r'\bввиду того,?\s*что\b': 'так как',
    r'\bпо причине того,?\s*что\b': 'так как',
    r'\bдля того,?\s*чтобы\b': 'чтобы',
    r'\bс целью\b': 'чтобы',
    r'\bв целях\b': 'чтобы',
    
    # Repetitions
    r'\bи и\b': 'и',
    r'\bа а\b': 'а',
    r'\bно но\b': 'но',
    r'\bчто что\b': 'что',
}

# Patterns to simplify syntax
SYNTAX_SIMPLIFICATIONS = [
    # Remove unnecessary "который/которая/которое"
    (r'([^,]+),?\s*который\s+([^,\.]+),?\s*([^\.]+)\.', r'\1 — \2. \3.'),
    # Simplify "то, что" -> "что"
    (r'\bто,?\s*что\b', 'что'),
    # Remove redundant "является"
    (r'\bявляется\s+([а-яё]+)\b', r'\1'),
    # Simplify "в том числе" -> "включая"
    (r'\bв том числе\b', 'включая'),
]


def remove_double_spaces(text: str) -> str:
    """Remove double spaces and normalize whitespace."""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    return text.strip()


def fix_passive_voice(text: str) -> str:
    """Convert passive voice to active where possible."""
    # This is a simplified version - full implementation would need NLP
    # For now, we rely on CALQUES_REPLACEMENTS
    return text


def remove_calques(text: str) -> str:
    """Remove English calques and replace with natural Russian."""
    for pattern, replacement in CALQUES_REPLACEMENTS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def simplify_syntax(text: str) -> str:
    """Simplify complex syntax structures."""
    for pattern, replacement in SYNTAX_SIMPLIFICATIONS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def check_english_words(text: str, max_length: int = 6) -> list:
    """
    Find English words longer than max_length (excluding proper nouns, URLs, HTML tags).
    
    Returns list of found words.
    """
    # Remove HTML tags and URLs first
    text_clean = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
    text_clean = re.sub(r'https?://[^\s]+', '', text_clean)  # Remove URLs
    text_clean = re.sub(r'www\.[^\s]+', '', text_clean)  # Remove www URLs
    
    # Pattern for English words (Latin letters, at least max_length+1 chars)
    pattern = r'\b[A-Za-z]{' + str(max_length + 1) + r',}\b'
    matches = re.findall(pattern, text_clean)
    
    # Filter out common proper nouns (game names, company names, etc.)
    # These are usually capitalized or in quotes
    proper_nouns = re.findall(r'[A-Z][a-z]+', text_clean)  # Capitalized words
    filtered = [m for m in matches if m not in proper_nouns and m.lower() not in [
        'steam', 'valve', 'xbox', 'playstation', 'nintendo', 'epic', 'unity', 'unreal',
        'early', 'access', 'beta', 'alpha', 'demo', 'dlc', 'mod', 'patch', 'update',
        'design', 'studios', 'interactive', 'games', 'entertainment', 'publishing',
        'samorost', 'creaks', 'machinarium', 'phonopolis'  # Game names
    ]]
    
    return filtered


def check_sentence_length(text: str, max_length: int = 180) -> list:
    """Find sentences longer than max_length characters."""
    sentences = re.split(r'[.!?]\s+', text)
    long_sentences = [s for s in sentences if len(s) > max_length]
    return long_sentences


def check_passive_voice_count(text: str, max_count: int = 2) -> bool:
    """Check if passive voice markers appear more than max_count times."""
    passive_patterns = [r'\bбыл\b', r'\bбыла\b', r'\bбыло\b', r'\bбыли\b']
    total_count = sum(len(re.findall(pattern, text, re.IGNORECASE)) for pattern in passive_patterns)
    return total_count > max_count


def rewrite_editorial_ru(
    text: str,
    event_type: Optional[str] = None,
    score: Optional[int] = None
) -> str:
    """
    Rewrite text to read like natural Russian editorial content.
    
    Tasks:
    1. Remove HTML tags
    2. Fix translation artifacts
    3. Simplify syntax
    4. Remove calques
    5. Remove passive voice markers
    6. Make active form
    7. Remove redundant repetitions
    8. Make text dense
    
    Args:
        text: Text to rewrite
        event_type: Event type (for context)
        score: Significance score (for context)
    
    Returns:
        Rewritten text
    """
    if not text or text == "нет данных":
        return text
    
    # Step 0: Remove HTML tags and clean up (AGGRESSIVE)
    # Remove all HTML tags including attributes
    text = re.sub(r'<[^>]+>', '', text)  # Remove HTML tags
    # Remove HTML entities
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&ldquo;', '"', text)
    text = re.sub(r'&rdquo;', '"', text)
    text = re.sub(r'&mdash;', '—', text)
    text = re.sub(r'&ndash;', '–', text)
    # Remove URL fragments and query strings that might be in text
    text = re.sub(r'https?://[^\s]+', '', text)  # Remove URLs
    text = re.sub(r'[a-zA-Z0-9_-]+\.(jpg|png|gif|webp|jpeg)\?[^\s]+', '', text, flags=re.IGNORECASE)  # Remove image URLs with params
    
    # Step 0.5: Normalize ALL quote types FIRST (critical - must be before artifact removal)
    # Handle ALL Unicode quote variants - this is critical for fixing artifacts
    # IMPORTANT: Order matters - normalize all variants to straight quotes
    quote_replacements = [
        ("'", "'"),  # U+2019 Right single quotation mark (most common typographic quote)
        ("'", "'"),  # U+2018 Left single quotation mark
        ('"', '"'),  # U+201D Right double quotation mark
        ('"', '"'),  # U+201C Left double quotation mark
        ('«', '"'),  # Russian left double
        ('»', '"'),  # Russian right double
        ('„', '"'),  # German left double
        ('"', '"'),  # German right double
        ('‚', "'"),  # Single low-9 quotation mark
        ('‹', "'"),  # Single left-pointing angle quotation mark
        ('›', "'"),  # Single right-pointing angle quotation mark
    ]
    for old_quote, new_quote in quote_replacements:
        text = text.replace(old_quote, new_quote)
    
    # Step 0.6: Fix common translation artifacts (aggressive)
    # After normalization, all quotes should be straight ', so we can use simple patterns
    # Remove stray English contractions after Russian words
    text = re.sub(r"([а-яёА-ЯЁ]+)\s*'t\s+", r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r"([а-яёА-ЯЁ]+)\s*'s\s+", r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r"([а-яёА-ЯЁ]+)\s*'m\s+", r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r"([а-яёА-ЯЁ]+)\s*'re\s+", r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r"([а-яёА-ЯЁ]+)\s*'ve\s+", r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r"([а-яёА-ЯЁ]+)\s*'ll\s+", r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r"([а-яёА-ЯЁ]+)\s*'d\s+", r'\1 ', text, flags=re.IGNORECASE)
    
    # Fix specific patterns like "не был't" -> "не был" (after normalization, quotes are straight)
    text = re.sub(r'\bне\s+был\'t\b', 'не был', text, flags=re.IGNORECASE)
    text = re.sub(r'\bбыл\'t\b', 'был', text, flags=re.IGNORECASE)
    # Cyrillic 'т' artifacts
    text = re.sub(r'\bне\s+был\'т\b', 'не был', text, flags=re.IGNORECASE)
    text = re.sub(r'\bбыл\'т\b', 'был', text, flags=re.IGNORECASE)
    
    # More aggressive: remove any 't/'т after Russian words at word boundary
    text = re.sub(r'([а-яёА-ЯЁ]+)\'t\b', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'([а-яёА-ЯЁ]+)\'т\b', r'\1', text, flags=re.IGNORECASE)
    
    # Fix Cyrillic artifacts (был'т -> был) - after normalization
    text = re.sub(r"([а-яёА-ЯЁ]+)'т\b", r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r"([а-яёА-ЯЁ]+)'Т\b", r'\1', text, flags=re.IGNORECASE)
    
    # Fix specific patterns
    text = re.sub(r'\bне\s+был[''"]t\b', 'не был', text, flags=re.IGNORECASE)
    text = re.sub(r'\bбыл[''"]t\b', 'был', text, flags=re.IGNORECASE)
    # Cyrillic 'т' artifacts
    text = re.sub(r'\bне\s+был[''"]т\b', 'не был', text, flags=re.IGNORECASE)
    text = re.sub(r'\bбыл[''"]т\b', 'был', text, flags=re.IGNORECASE)
    
    # More aggressive: remove any 't/'т after Russian words at word boundary
    text = re.sub(r'([а-яёА-ЯЁ]+)[''"]t\b', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'([а-яёА-ЯЁ]+)[''"]т\b', r'\1', text, flags=re.IGNORECASE)
    
    # Fix mixed language artifacts
    text = re.sub(r'\b([а-яё]+)[''"]([a-z]+)\b', r'\1 \2', text, flags=re.IGNORECASE)
    
    # Step 1: Remove calques
    text = remove_calques(text)
    
    # Step 2: Simplify syntax
    text = simplify_syntax(text)
    
    # Step 3: Fix passive voice (via calques replacements)
    text = fix_passive_voice(text)
    
    # Step 4: Remove double spaces
    text = remove_double_spaces(text)
    
    # Step 5: Fix common bad translations and editorial issues
    # Fix "не помещает зуб" -> "не может конкурировать" or similar
    bad_translations = {
        r'\bне\s+помещает\s+зуб\b': 'не может конкурировать',
        r'\bпомещает\s+зуб\b': 'конкурирует',
        r'\bне\s+помещает\b': 'не может',
        r'\bпомещает\b': 'может',
        # Fix other common bad translations
        r'\bбыл\s+выпущен\s+в\s+продажу\b': 'вышел в продажу',
        r'\bбыла\s+выпущена\s+в\s+продажу\b': 'вышла в продажу',
        r'\bбыло\s+выпущено\s+в\s+продажу\b': 'вышло в продажу',
        # Fix duplicate phrases
        r'\b([^\.]+)\s+\1\b': r'\1',  # Remove exact duplicates
        r'\b(Кто-то|кто-то)\s+\1\b': r'\1',  # Remove duplicate "Кто-то"
    }
    for pattern, replacement in bad_translations.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Remove duplicate sentences (editorial quality)
    sentences = re.split(r'[.!?]\s+', text)
    seen_sentences = set()
    unique_sentences = []
    for sent in sentences:
        sent_clean = sent.strip()
        if sent_clean:
            sent_lower = sent_clean.lower()
            # Normalize for comparison (remove punctuation, extra spaces)
            sent_normalized = re.sub(r'[^\w\s]', '', sent_lower)
            sent_normalized = re.sub(r'\s+', ' ', sent_normalized).strip()
            if sent_normalized and sent_normalized not in seen_sentences:
                unique_sentences.append(sent_clean)
                seen_sentences.add(sent_normalized)
    text = ". ".join(unique_sentences)
    if text and not text.endswith(('.', '!', '?')):
        text += "."
    
    # Step 6: Final cleanup - remove any remaining artifacts
    text = re.sub(r"([а-яёА-ЯЁ])\s*['']([a-z]+)", r'\1 \2', text)  # Fix remaining mixed artifacts
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def validate_editorial_quality(text: str) -> Dict[str, any]:
    """
    Validate text meets editorial quality standards.
    
    Checks:
    1. No English words > 6 chars (except proper nouns)
    2. Cyrillic >= 30%
    3. No double spaces
    4. No "был/была/было" more than 2 times
    5. No sentences longer than 180 chars
    
    Returns:
        Dict with validation results
    """
    if not text:
        return {
            "valid": False,
            "errors": ["Text is empty"]
        }
    
    errors = []
    warnings = []
    
    # Check 1: English words
    english_words = check_english_words(text, max_length=6)
    if english_words:
        errors.append(f"English words found: {', '.join(english_words[:5])}")
    
    # Check 2: Cyrillic ratio
    cyrillic_count = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
    total_alpha = len([c for c in text if c.isalpha()])
    cyrillic_ratio = cyrillic_count / total_alpha if total_alpha > 0 else 0
    if cyrillic_ratio < 0.30:
        errors.append(f"Cyrillic ratio too low: {cyrillic_ratio:.1%} (min 30%)")
    
    # Check 3: Double spaces
    if '  ' in text:
        errors.append("Double spaces found")
    
    # Check 4: Passive voice count
    if check_passive_voice_count(text, max_count=2):
        warnings.append("Too many passive voice markers (был/была/было)")
    
    # Check 5: Sentence length
    long_sentences = check_sentence_length(text, max_length=180)
    if long_sentences:
        warnings.append(f"Long sentences found: {len(long_sentences)}")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "cyrillic_ratio": cyrillic_ratio,
        "english_words": english_words,
        "long_sentences": len(long_sentences)
    }


def enforce_editorial_quality(text: str, max_iterations: int = 3) -> str:
    """
    Enforce editorial quality by rewriting until validation passes.
    
    Args:
        text: Text to rewrite
        max_iterations: Maximum rewrite iterations
    
    Returns:
        Rewritten text that passes validation (or best attempt)
    """
    current_text = text
    
    for iteration in range(max_iterations):
        validation = validate_editorial_quality(current_text)
        
        if validation["valid"]:
            return current_text
        
        # Rewrite to fix errors
        current_text = rewrite_editorial_ru(current_text)
        
        # Additional fixes based on errors
        if "Double spaces" in str(validation["errors"]):
            current_text = remove_double_spaces(current_text)
        
        if "passive voice" in str(validation["warnings"]).lower():
            current_text = remove_calques(current_text)
    
    # Return best attempt even if not perfect
    return current_text
