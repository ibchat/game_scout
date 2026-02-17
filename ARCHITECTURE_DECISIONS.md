# Architecture Decisions

## Steam/Market Intel → Business Brief → Telegram (Free/Premium)

**Date:** 2026-02-17  
**Status:** Implementation in progress

### Current State Audit

#### Existing Models (IntelEvent)
- ✅ `business_brief_json` (JSONB) - already exists
- ✅ `business_brief_generated_at` (datetime) - already exists
- ✅ `publish_status` (draft/published/failed) - already exists
- ✅ `publish_channel` (string) - already exists
- ✅ `is_premium` (boolean) - already exists
- ✅ `telegram_message_id` - already exists
- ✅ `published_at` - already exists

#### Existing Models (IntelPublishLog)
- ✅ `channel_id` (string) - exists, but needs to be used as "free"/"premium"
- ✅ `telegram_message_id` - already exists
- ✅ `payload` (JSONB) - already exists
- ❌ `status` (published/failed/skipped) - **NEEDS TO BE ADDED**
- ❌ `error` (text) - **NEEDS TO BE ADDED**

#### Existing Services
- ✅ `steam_brief_generator.py` - exists but needs format update
- ✅ `telegram_publisher.py` - exists but needs FREE/PREMIUM channel support
- ✅ `/run-steam-feed` endpoint - exists but needs refactoring

#### Policy Structure
- ✅ `telegram_template` with `max_chars: 3500` and format list
- ✅ `allowed_event_types_for_autopublish` - configured
- ✅ `limits.max_posts_per_hour` and `max_posts_per_day` - configured

### What We're Adding

1. **Config Updates:**
   - `TELEGRAM_CHAT_ID_FREE` and `TELEGRAM_CHAT_ID_PREMIUM` (separate from `TELEGRAM_CHAT_ID`)
   - Function to get channel configs

2. **Migration:**
   - Add `status` and `error` fields to `IntelPublishLog`

3. **Business Brief Format Update:**
   - Change from current format to:
     ```json
     {
       "title": "...",
       "what_happened": "...",
       "why_it_matters": "...",
       "key_points": ["...", "..."],
       "signal_type": "release|patch_major|...",
       "confidence": 0.0-1.0,
       "sources": ["url1", "url2"],
       "language": "ru"
     }
     ```

4. **Pipeline Orchestrator:**
   - New service: `apps/intel/services/pipeline/steam_intel_pipeline.py`
   - Flow: collect → extract → event → brief → publish
   - Idempotency: check `IntelPublishLog` for existing (event_id, channel) before publishing

5. **API Endpoints:**
   - `POST /api/v1/intel/pipeline/run` - new endpoint with body params
   - `GET /api/v1/intel/health` - update to include telegram_config_present, db_ok

6. **Celery Tasks:**
   - `run_intel_pipeline_free` - every 30-60 minutes
   - `run_intel_pipeline_premium` - every 15-30 minutes

7. **Tests:**
   - `test_telegram_template.py`
   - `test_pipeline_idempotency.py`
   - `scripts/intel_smoke_publish_dry_run.py`

### Why This Architecture

1. **No New Tables:** All data fits into existing `IntelEvent` and `IntelPublishLog` models. Only adding 2 fields to `IntelPublishLog`.

2. **Idempotency:** Using `(event_id, channel_id)` as unique key in `IntelPublishLog` prevents duplicate publishes.

3. **Channel Separation:** FREE vs PREMIUM handled via:
   - `is_premium` flag on `IntelEvent`
   - Separate `TELEGRAM_CHAT_ID_FREE` and `TELEGRAM_CHAT_ID_PREMIUM` env vars
   - `channel_id` in `IntelPublishLog` tracks which channel was used

4. **Pipeline Orchestrator:** Single service coordinates all stages, making it easy to test and maintain.

5. **Rules-based Fallback:** If LLM unavailable, use simple text summarization from `extracted_text` without LLM calls.

### Risks & Mitigations

1. **Risk:** LLM unavailable → fallback to rules-based summarizer
   - **Mitigation:** Implement simple text extraction and bullet points from `extracted_text`

2. **Risk:** Duplicate publishes
   - **Mitigation:** Check `IntelPublishLog` for existing `(event_id, channel_id)` before publishing

3. **Risk:** Telegram API failures
   - **Mitigation:** Retry with backoff (3 attempts, 1/2/4 seconds), save error in `IntelPublishLog.status` and `error` fields

### Next Steps

1. Update config for FREE/PREMIUM channels
2. Create migration for `IntelPublishLog.status` and `error`
3. Update business brief generator to new format
4. Update Telegram publisher for FREE/PREMIUM channels
5. Create pipeline orchestrator
6. Add API endpoints
7. Add Celery tasks
8. Add tests
9. Update Dev Supervisor
