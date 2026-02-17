# VOY Learning & GPT Control

## Overview

VOY learning system provides controlled, transparent, and explainable weight adjustments for skills based on human feedback and optional GPT advice.

## Architecture

### Learning Configuration

The `voy_learning_config` table stores a single configuration that controls all learning behavior:

- **learning_enabled**: Master switch for learning (if false, weights never change)
- **learning_rate**: How much weights adjust per feedback (default: 0.05)
- **max_weight_delta**: Maximum change per adjustment (default: 0.05)
- **min_skill_weight**: Minimum allowed weight (default: 0.5)
- **max_skill_weight**: Maximum allowed weight (default: 2.0)
- **min_feedback_count**: Minimum feedbacks before learning applies (default: 3)
- **frozen_skills**: List of skills that never change
- **allow_gpt_advice**: Enable GPT suggestions (default: true)

### Learning Log

Every weight change is logged to `voy_learning_log` with:
- Skill key
- Old and new weights
- Delta
- Reason
- Source ("feedback" or "gpt_advice")
- Timestamp

## Learning Rules

### Rule 1: Learning Enabled Check
If `learning_enabled = false`, no weights change regardless of feedback.

### Rule 2: Frozen Skills
Skills in `frozen_skills` list are never modified.

### Rule 3: Minimum Feedback Count
A skill must have at least `min_feedback_count` feedbacks before learning applies.

### Rule 4: Weight Limits
All weights are clamped to `[min_skill_weight, max_skill_weight]`.

### Rule 5: Delta Limits
No single adjustment can exceed `max_weight_delta`.

## Feedback-Based Learning

When user provides feedback:

1. Check `learning_enabled`
2. For each skill in `skill_scores_json`:
   - Skip if frozen
   - Skip if feedback count < `min_feedback_count`
   - Apply adjustment:
     - **Good feedback**: `new_weight = old_weight + learning_rate * score`
     - **Bad feedback**: `new_weight = old_weight - learning_rate * score`
   - Clamp to limits
   - Log change with source="feedback"

## GPT Advice Integration

### When GPT Advice is Applied

GPT advice is only considered if:
- `allow_gpt_advice = true`
- Feedback was just processed
- At least one weight changed from feedback

### GPT Prompt Template

The system uses a strict template:

```
SYSTEM:
You are an analytical assistant helping a game scouting system.
You MUST NOT propose new skills.
You MUST NOT change architecture.
You MUST stay within provided limits.
You MUST respond ONLY in valid JSON.

CONTEXT:
User feedback: {positive|negative}
Reason: {feedback_reason}

Active skills:
{skill_key} (weight={weight})
...

Frozen skills:
{frozen_skills_list}

Limits:
- max_weight_delta: {max_weight_delta}
- min_weight: {min_skill_weight}
- max_weight: {max_skill_weight}

QUESTION:
Which of the active skills might be over- or under-weighted?
Return ONLY weight adjustments within limits.
```

### Expected GPT Response

```json
{
  "suggestions": [
    {
      "skill": "wishlist_velocity",
      "delta": -0.04,
      "reason": "Growth appears driven by discounts, not organic demand"
    }
  ]
}
```

### Validation

GPT responses are strictly validated:
- Must be valid JSON
- Must have "suggestions" array
- Each suggestion must:
  - Reference an existing skill
  - Not be in frozen_skills
  - Have delta within max_weight_delta
  - Have delta that keeps weight in [min, max] range

**Any invalid response is completely ignored.**

### Applying GPT Advice

1. Validate response
2. For each valid suggestion:
   - Apply delta to skill weight
   - Clamp to limits
   - Log change with source="gpt_advice"

## API Endpoints

### Learning Config

- `GET /api/v1/voy/learning-config` - Get current config
- `PATCH /api/v1/voy/learning-config` - Update config

### Learning Log

- `GET /api/v1/voy/learning-log?limit=50&skill_key=...&source=...` - Get log entries

## UI

### Learning Settings Section

In VOY tab:
- Checkbox: Learning enabled
- Inputs: learning_rate, max_weight_delta, min/max weights, min_feedback_count
- Input: Frozen skills (comma-separated)
- Checkbox: Allow GPT advice
- Button: Save

### Learning Log Section

Table showing:
- Skill
- Old → New weight
- Delta
- Source (feedback/gpt_advice)
- Reason
- Time

Filters:
- By skill key
- By source

## Safety Guarantees

1. **No Architecture Changes**: GPT cannot propose new skills or change system structure
2. **Strict Validation**: All GPT responses validated before application
3. **Complete Logging**: Every weight change is logged with reason
4. **Configurable Limits**: All limits are configurable and enforced
5. **Frozen Skills**: Skills can be frozen to prevent any changes
6. **Minimum Feedback**: Learning only applies after sufficient feedback

## Example Flow

1. User runs VOY → shortlist created
2. User clicks 👍 on item #3
3. System:
   - Checks learning_enabled (true)
   - Gets skills used in item #3
   - For each skill:
     - Checks if frozen (no)
     - Checks feedback count (>= 3)
     - Applies adjustment: weight += learning_rate * score
     - Logs change
4. If allow_gpt_advice = true:
   - Builds GPT prompt
   - Calls GPT API
   - Validates response
   - Applies valid suggestions
   - Logs GPT changes
5. User views Learning Log to see all changes

## Configuration

Set environment variables:
- `OPENAI_API_KEY` - Required for GPT advice
- `OPENAI_API_URL` - Optional (default: https://api.openai.com/v1/chat/completions)
- `OPENAI_MODEL` - Optional (default: gpt-4)

## Files

- `migrations/versions/007_add_voy_learning_tables.py` - Learning tables
- `apps/db/models/voy.py` - VoyLearningConfig, VoyLearningLog models
- `apps/api/services/voy_gpt.py` - GPT prompt builder and validator
- `apps/api/services/voy_engine.py` - Updated with learning logic
- `apps/api/routers/voy.py` - Learning config and log endpoints
- `apps/api/static/unified_dashboard.html` - Learning UI
- `docs/voy_learning.md` - This documentation
