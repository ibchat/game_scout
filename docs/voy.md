# VOY Module (Voyager-style Scout)

## Overview

VOY is a read-only overlay module for game scouting with learning capabilities. It provides an isolated system for:
- Selecting goals
- Fetching candidate games from existing signals (read-only)
- Computing features
- Scoring via skills
- Saving shortlists
- Learning from human feedback

## Architecture

### Isolation

VOY is fully isolated:
- **Separate DB tables**: `voy_skill`, `voy_run`, `voy_run_item`, `voy_feedback`
- **Separate API router**: `/api/v1/voy/*`
- **Separate UI section**: VOY tab in unified_dashboard
- **Feature flag**: `VOY_ENABLED` environment variable

### Primary Key

VOY uses `game_id` (UUID) as primary key for logic. `app_id` (Steam app ID) is optional.

## Database Schema

### voy_skill
Skills with weights for scoring:
- `id` (UUID, PK)
- `name` (Text)
- `description` (Text, nullable)
- `weight` (Float, default 1.0, clamped to [0.2, 3.0])
- `goal` (Text, nullable) - Optional goal this skill is optimized for
- `created_at`, `updated_at` (Timestamps)

### voy_run
A single VOY execution run:
- `id` (UUID, PK)
- `goal` (Text) - Goal description
- `status` (Text) - running, completed, cancelled
- `total_candidates` (Integer)
- `shortlist_size` (Integer)
- `created_at`, `completed_at` (Timestamps)

### voy_run_item
Games in a run's shortlist:
- `id` (UUID, PK)
- `run_id` (UUID, FK to voy_run)
- `game_id` (UUID) - Primary key for VOY logic
- `app_id` (Integer, nullable) - Optional Steam app_id
- `title` (Text, nullable)
- `total_score` (Float)
- `explanation` (Text, nullable)
- `features_json` (JSONB) - Computed features
- `skill_scores_json` (JSONB) - Individual skill scores
- `rank` (Integer) - Rank in shortlist (1 = best)
- `created_at` (Timestamp)

### voy_feedback
Human feedback on run items:
- `id` (UUID, PK)
- `run_item_id` (UUID, FK to voy_run_item)
- `feedback_type` (Text) - 'good' or 'bad'
- `notes` (Text, nullable)
- `created_at` (Timestamp)

## VOY Loop

1. **Select goal** - User selects a goal (e.g., "publisher_hunt", "high_potential")
2. **Fetch candidates** - Read-only access to `deal_intent_signal` table
3. **Compute features** - Extract features from candidate data
4. **Score via skills** - Apply skill weights to compute total score
5. **Save shortlist** - Store top-N candidates in `voy_run_item`
6. **Await feedback** - User provides 👍 or 👎 feedback
7. **Update weights** - Adjust skill weights based on feedback

## Learning Logic

Simple, safe learning:
- **Good feedback** → Increase weights of contributing skills
- **Bad feedback** → Decrease weights of contributing skills
- **Clamp weights** to [0.2, 3.0]
- **No auto code changes** - Only weight adjustments

### Learning Rate

Default learning rate: 0.1 (configurable in `VoyEngine.process_feedback`)

## API Endpoints

### Health
- `GET /api/v1/voy/health` - Check if VOY is enabled

### Skills
- `GET /api/v1/voy/skills?goal=...` - List skills (optionally filtered by goal)
- `POST /api/v1/voy/skills` - Create a new skill

### Runs
- `POST /api/v1/voy/runs` - Create a new run
- `POST /api/v1/voy/runs/{run_id}/execute?shortlist_size=10` - Execute a run
- `GET /api/v1/voy/runs/{run_id}` - Get run with items
- `GET /api/v1/voy/runs?limit=20` - List recent runs

### Feedback
- `POST /api/v1/voy/feedback` - Submit feedback (updates skill weights)

## UI

### VOY Tab in unified_dashboard

Minimal UI includes:
- **Run VOY** button + goal selector
- **Shortlist table** with columns:
  - Rank
  - Game ID
  - Title
  - Total Score
  - Explanation
  - Feedback buttons (👍👎)

### Feature Flag

VOY tab is only visible when `VOY_ENABLED=true` is set in environment.

## Default Skills

If no skills exist, VOY creates default skills:
- `signal_count` (weight: 1.0) - Number of signals
- `intent_score` (weight: 1.5) - Publisher intent score
- `confidence` (weight: 1.2) - Signal confidence
- `recency` (weight: 1.0) - Signal recency

## Usage

### Enable VOY

```bash
export VOY_ENABLED=true
```

### Run Migration

```bash
docker compose exec api alembic upgrade head
```

### Create a Run

1. Open unified_dashboard
2. Click VOY tab (if enabled)
3. Select a goal
4. Click "Run VOY"
5. View shortlist
6. Provide feedback (👍 or 👎)

## Testing

### Skill Scoring
- Test that skills contribute to total score correctly
- Test that weights affect scoring

### Weight Update
- Test that good feedback increases weights
- Test that bad feedback decreases weights
- Test that weights are clamped to [0.2, 3.0]

### Full Loop
- Test: run → shortlist → feedback → weight change

## Files

- `migrations/versions/006_add_voy_tables.py` - Database migration
- `apps/db/models/voy.py` - SQLAlchemy models
- `apps/api/schemas/voy.py` - Pydantic schemas
- `apps/api/services/voy_engine.py` - Core VOY logic
- `apps/api/routers/voy.py` - API router
- `apps/api/static/unified_dashboard.html` - UI (VOY tab)
- `docs/voy.md` - This documentation

## Constraints

- **Read-only** access to existing signals (no modifications)
- **Isolated** from other modules
- **Feature flag** required for activation
- **No regression** in existing dashboards
