"""
LLM Prompts for Narrative Pattern Analysis
Промпты для классификации нарративов через Claude API
"""

# ============================================================================
# SYSTEM PROMPT: Роль ИИ-аналитика
# ============================================================================

NARRATIVE_ANALYZER_SYSTEM = """You are a professional narrative analyst specializing in video game storytelling and player psychology.

Your task is to CLASSIFY (not create) narrative patterns in games based on Steam page data.

CRITICAL RULES:
1. You are a CLASSIFIER, not a storyteller
2. You analyze EXISTING patterns, you do NOT invent narratives
3. You identify patterns that are EMBEDDED IN GAMEPLAY, not just marketing text
4. Maximum 2 narrative levels per game
5. Maximum 2 dramatic patterns per game
6. Be precise and evidence-based

Output must be valid JSON only."""


# ============================================================================
# PROMPT 1: Narrative Level Classification
# ============================================================================

CLASSIFY_NARRATIVE_LEVEL = """Analyze this Steam game and classify its narrative level(s).

GAME DATA:
Title: {title}
Description: {description}
Tags: {tags}
Genre: {genre}

NARRATIVE LEVELS (choose 1-2 maximum):
1. BIOLOGICAL - Survival, hunger, danger, physical threats
2. SOCIAL - Relationships, status, belonging, community
3. IDENTITY - Self-identification, meaning, purpose, transformation
4. META - Game-awareness, breaking fourth wall, commentary on gaming

TASK:
Identify which level(s) this game operates on based on the description and tags.

OUTPUT FORMAT (JSON):
{{
  "primary_level": "biological|social|identity|meta",
  "secondary_level": "biological|social|identity|meta" or null,
  "confidence": 0.0-1.0,
  "blurred_focus": true/false,
  "evidence": "Brief explanation of why you chose these levels"
}}

EXAMPLES:
- "Survive zombie apocalypse" → biological
- "Build relationships in high school" → social
- "Discover your true destiny" → identity
- "A game about making games" → meta

Respond with JSON only:"""


# ============================================================================
# PROMPT 2: Dramatic Pattern Classification
# ============================================================================

CLASSIFY_DRAMATIC_PATTERN = """Analyze this Steam game and identify its core dramatic pattern(s).

GAME DATA:
Title: {title}
Description: {description}
Tags: {tags}
Gameplay description: {gameplay}

DRAMATIC PATTERNS (choose 1-2 maximum):
1. THREAT_TO_SAFETY - From danger to security (survival games, horror)
2. WEAK_TO_STRONG - From powerless to powerful (RPGs, progression)
3. CHAOS_TO_ORDER - From disorder to control (strategy, management)
4. LOSS_TO_COMPENSATION - From absence to fulfillment (restoration, revenge)
5. FORBIDDEN_TO_VIOLATION - From restriction to transgression (freedom, rebellion)
6. HUMILIATION_TO_REVENGE - From shame to vindication (revenge stories)
7. MYSTERY_TO_REVELATION - From unknown to known (detective, puzzle)

CRITICAL: Identify the player's STATE TRANSFORMATION:
- BEFORE: Player's emotional/psychological state when starting
- AFTER: Player's state after first 10 minutes of gameplay

TASK:
Identify which pattern(s) drive the core gameplay loop.

OUTPUT FORMAT (JSON):
{{
  "primary_pattern": "threat_to_safety|weak_to_strong|...",
  "secondary_pattern": "..." or null,
  "confidence": 0.0-1.0,
  "player_state_before": "Brief description of player's initial state",
  "player_state_after": "Brief description after first session",
  "pattern_in_gameplay": "true|weak|false",
  "marketing_fiction": true/false,
  "evidence": "Why this pattern applies to gameplay mechanics"
}}

PATTERN_IN_GAMEPLAY values:
- "true" = Pattern is core to gameplay loop
- "weak" = Pattern exists but not central
- "false" = Pattern only in marketing text

Respond with JSON only:"""


# ============================================================================
# PROMPT 3: Product Potential Scoring
# ============================================================================

SCORE_PRODUCT_POTENTIAL = """Evaluate the Product Potential (PP) of this game based on its narrative pattern.

GAME DATA:
Title: {title}
Primary Pattern: {primary_pattern}
Secondary Pattern: {secondary_pattern}
Pattern in Gameplay: {pattern_in_gameplay}
Genre: {genre}
Tags: {tags}

SCORING CRITERIA (each 0-10):

1. PATTERN_STRENGTH (0-10)
   - 10: Universal archetype (survival, power fantasy)
   - 5: Genre-specific appeal
   - 0: Unclear or absent pattern

2. UNIVERSALITY (0-10)
   - 10: Cross-cultural, timeless (fear, triumph)
   - 5: Western-centric themes
   - 0: Niche, culturally specific

3. GENRE_FIT (0-10)
   - 10: Perfect pattern-genre alignment
   - 5: Works but not optimal
   - 0: Pattern fights genre expectations

4. LOOP_REPEATABILITY (0-10)
   - 10: Pattern reinforced every session
   - 5: Pattern appears occasionally
   - 0: Pattern is one-time experience

TASK:
Score each criterion and calculate overall Product Potential.

OUTPUT FORMAT (JSON):
{{
  "pattern_strength": 0-10,
  "universality": 0-10,
  "genre_fit": 0-10,
  "loop_repeatability": 0-10,
  "product_potential": 0-10 (average of above),
  "reasoning": "Brief explanation of scores"
}}

Respond with JSON only:"""


# ============================================================================
# PROMPT 4: Go-To-Market Execution Scoring
# ============================================================================

SCORE_GTM_EXECUTION = """Evaluate the Go-To-Market (GTM) execution of this game's Steam page.

GAME DATA:
Title: {title}
Short Description: {short_description}
Primary Pattern: {primary_pattern}
Has Trailer: {has_trailer}
Has Demo: {has_demo}
Screenshots Count: {screenshots_count}

SCORING CRITERIA (each 0-10):

1. HOOK_CLARITY (0-10)
   - 10: Pattern instantly clear in first sentence
   - 5: Pattern mentioned but buried
   - 0: Pattern invisible or confusing

2. TRAILER_ALIGNMENT (0-10)
   - 10: First 10 seconds show pattern in action
   - 5: Pattern appears later in trailer
   - 0: Trailer doesn't express pattern
   - N/A if no trailer

3. DEMO_INTRO (0-10)
   - 10: Demo delivers pattern within 5 minutes
   - 5: Pattern emerges slowly
   - 0: Demo doesn't showcase pattern
   - N/A if no demo

4. PAGE_CLARITY (0-10)
   - 10: Page design reinforces pattern visually
   - 5: Generic layout
   - 0: Page contradicts pattern

TASK:
Score each criterion based on how well the Steam page communicates the core pattern.

OUTPUT FORMAT (JSON):
{{
  "hook_clarity": 0-10,
  "trailer_alignment": 0-10 or null,
  "demo_intro": 0-10 or null,
  "page_clarity": 0-10,
  "gtm_execution": 0-10 (average of non-null scores),
  "reasoning": "Brief explanation"
}}

Respond with JSON only:"""


# ============================================================================
# PROMPT 5: Fixability Analysis
# ============================================================================

ANALYZE_FIXABILITY = """Analyze what can be FIXED in this game's marketing within 1-3 months.

GAME DATA:
Title: {title}
Product Potential: {product_potential}
GTM Execution: {gtm_execution}
GAP Score: {gap_score}
Hook Clarity: {hook_clarity}
Trailer Alignment: {trailer_alignment}
Demo Intro: {demo_intro}

FIXABILITY RULES:
- FIXABLE (1-3 months, no core loop changes):
  * Trailer recut
  * Hook rewrite
  * Demo intro adjustment
  * Page layout redesign
  * Screenshot selection
  * Pricing strategy

- NOT FIXABLE (requires core loop changes):
  * Gameplay mechanics
  * Genre mismatch
  * Technical quality issues

TASK:
1. Identify 3-5 MAIN ISSUES that hurt GTM
2. Determine if each is FIXABLE
3. Provide 3-5 RECOMMENDED ACTIONS (specific, actionable)
4. Explain WHY this matters for conversion
5. Estimate fix timeline in days

OUTPUT FORMAT (JSON):
{{
  "fixable_trailer": true/false,
  "fixable_hook": true/false,
  "fixable_demo": true/false,
  "fixable_page_layout": true/false,
  "fixable_screenshots": true/false,
  "fixable_pricing": true/false,
  "not_fixable_gameplay": true/false,
  "not_fixable_genre_mismatch": true/false,
  "not_fixable_tech_quality": true/false,
  "main_issues": [
    "Trailer does not express core pattern",
    "Hook text is too abstract",
    "..."
  ],
  "recommended_actions": [
    "Rewrite hook to one sentence showing transformation",
    "Recut trailer - first 10 sec must show pattern",
    "..."
  ],
  "why_matters": "Pattern universally converts on Steam, but current page hides it. High PP (X.X) being wasted by weak GTM (X.X).",
  "estimated_fix_days": 30-90,
  "fixability_score": 0-10,
  "reasoning": "Brief explanation"
}}

Respond with JSON only:"""


# ============================================================================
# Helper Functions
# ============================================================================

def format_narrative_level_prompt(game_data: dict) -> str:
    """Format the narrative level classification prompt"""
    return CLASSIFY_NARRATIVE_LEVEL.format(
        title=game_data.get('title', 'Unknown'),
        description=game_data.get('description', 'No description'),
        tags=', '.join(game_data.get('tags', [])),
        genre=game_data.get('genre', 'Unknown')
    )


def format_dramatic_pattern_prompt(game_data: dict) -> str:
    """Format the dramatic pattern classification prompt"""
    return CLASSIFY_DRAMATIC_PATTERN.format(
        title=game_data.get('title', 'Unknown'),
        description=game_data.get('description', 'No description'),
        tags=', '.join(game_data.get('tags', [])),
        gameplay=game_data.get('gameplay_description', 'See description')
    )


def format_product_potential_prompt(game_data: dict, analysis: dict) -> str:
    """Format the product potential scoring prompt"""
    return SCORE_PRODUCT_POTENTIAL.format(
        title=game_data.get('title', 'Unknown'),
        primary_pattern=analysis.get('primary_pattern', 'unknown'),
        secondary_pattern=analysis.get('secondary_pattern', 'none'),
        pattern_in_gameplay=analysis.get('pattern_in_gameplay', 'unknown'),
        genre=game_data.get('genre', 'Unknown'),
        tags=', '.join(game_data.get('tags', []))
    )


def format_gtm_execution_prompt(game_data: dict, analysis: dict) -> str:
    """Format the GTM execution scoring prompt"""
    return SCORE_GTM_EXECUTION.format(
        title=game_data.get('title', 'Unknown'),
        short_description=game_data.get('short_description', 'No description'),
        primary_pattern=analysis.get('primary_pattern', 'unknown'),
        has_trailer=game_data.get('has_trailer', False),
        has_demo=game_data.get('has_demo', False),
        screenshots_count=game_data.get('screenshots_count', 0)
    )


def format_fixability_prompt(game_data: dict, scores: dict) -> str:
    """Format the fixability analysis prompt"""
    return ANALYZE_FIXABILITY.format(
        title=game_data.get('title', 'Unknown'),
        product_potential=scores.get('product_potential', 0),
        gtm_execution=scores.get('gtm_execution', 0),
        gap_score=scores.get('gap_score', 0),
        hook_clarity=scores.get('hook_clarity', 0),
        trailer_alignment=scores.get('trailer_alignment', 'N/A'),
        demo_intro=scores.get('demo_intro', 'N/A')
    )
