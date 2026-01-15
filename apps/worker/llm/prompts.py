"""
LLM Prompts для анализа комментариев
"""

PROMPT_COMMENT_CLASSIFIER = """You are analyzing user comments about a video game to extract investment signals.

Game Title: {game_title}
Video Platform: {platform}
Video Title: {video_title}

Comments to analyze ({comment_count} total):
{comments_text}

Your task is to analyze these comments and extract:

1. **Intent Ratio** (0.0 to 1.0): What percentage of commenters express clear intent to play/buy the game?
   - Look for: "I want this", "day one buy", "can't wait", "adding to wishlist", "pre-ordering"
   - Ignore: casual interest without purchase intent

2. **Confusion Ratio** (0.0 to 1.0): What percentage of commenters are confused about what the game is?
   - Look for: "what is this?", "I don't understand", "what genre?", "how does it work?"
   - This indicates poor marketing/messaging

3. **Dominant Emotions** (pick top 3-5 from this list, with intensity 0.0-1.0):
   - excitement, anticipation, nostalgia, skepticism, disappointment, 
   - curiosity, hype, concern, frustration, joy

4. **Key Insights** (3-5 bullet points):
   - What are people most excited about?
   - What are the main concerns or criticisms?
   - Any patterns in what people don't understand?

Respond ONLY with valid JSON in this exact format:
{{
  "intent_ratio": 0.0,
  "confusion_ratio": 0.0,
  "emotions": {{
    "excitement": 0.0,
    "skepticism": 0.0
  }},
  "insights": [
    "Insight 1",
    "Insight 2"
  ],
  "confidence": 0.0
}}

Confidence should be 0.8-1.0 if you have 50+ comments, 0.5-0.8 for 20-50 comments, 0.3-0.5 for <20 comments.
"""


PROMPT_NARRATIVE_ALIGNMENT = """You are analyzing whether user reactions align with a game's intended narrative pattern.

Game Title: {game_title}
Intended Narrative Pattern: {narrative_pattern}
Pattern Description: {pattern_description}

User Comments Summary:
{comments_summary}

Dominant Emotions from Comments:
{emotions}

Key Insights from Comments:
{insights}

Question: Do the user reactions align with the intended narrative pattern?

Score from 0.0 to 1.0:
- 1.0 = Perfect alignment (users clearly "get" the narrative and respond as intended)
- 0.7-0.9 = Good alignment (users understand but may have mixed reactions)
- 0.4-0.6 = Partial alignment (some confusion or misinterpretation)
- 0.0-0.3 = Poor alignment (users completely misunderstand the narrative)

Respond ONLY with valid JSON:
{{
  "alignment_score": 0.0,
  "explanation": "Brief explanation of why this score",
  "misalignment_issues": ["Issue 1", "Issue 2"] or []
}}
"""


PROMPT_GTM_EVALUATION = """You are evaluating the Go-To-Market execution quality based on user comments.

Game Title: {game_title}
Comments Analysis:
- Intent Ratio: {intent_ratio}
- Confusion Ratio: {confusion_ratio}
- Dominant Emotions: {emotions}
- Key Insights: {insights}

Evaluate these GTM dimensions (each 0.0 to 1.0):

1. **Message Clarity**: Do people understand what the game is?
   - 1.0 = Everyone gets it immediately
   - 0.0 = Massive confusion about genre/gameplay

2. **Value Proposition**: Do people see compelling reasons to play?
   - 1.0 = Comments focus on unique/exciting features
   - 0.0 = No one mentions what makes it special

3. **Target Audience Fit**: Are the right people discovering this?
   - 1.0 = Comments from clearly target demographic
   - 0.0 = Attracting wrong audience or no audience

4. **Marketing Quality**: Is the presentation professional?
   - 1.0 = Comments praise visuals/trailer/presentation
   - 0.0 = Comments criticize marketing materials

Respond ONLY with valid JSON:
{{
  "message_clarity": 0.0,
  "value_proposition": 0.0,
  "target_audience_fit": 0.0,
  "marketing_quality": 0.0,
  "overall_gtm_score": 0.0,
  "main_issues": ["Issue 1", "Issue 2"]
}}

Overall GTM score should be weighted average of the 4 dimensions.
"""
