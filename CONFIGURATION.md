# Game Scout Configuration Guide

## Quick Start

1. Copy `.env.example` to `.env`:
```bash
   cp .env.example .env
```

2. Configure required services:
   - **Database**: PostgreSQL (default config works with Docker)
   - **Redis**: Redis (default config works with Docker)

3. Optional: Add API keys for full functionality

## Required Configuration

### Database & Redis
These work out-of-box with Docker Compose:
```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/game_scout
REDIS_URL=redis://redis:6379/0
```

## Optional Configuration

### YouTube Data API (for video collection)

**Without API key**: System uses mock data (good for testing)

**With API key**:
1. Go to https://console.cloud.google.com/
2. Create a project
3. Enable YouTube Data API v3
4. Create credentials (API key)
5. Add to `.env`:
```env
   YOUTUBE_API_KEY=your_actual_key_here
   YOUTUBE_MOCK_MODE=false
```

### Anthropic API (for comment analysis)

**Without API key**: Comment analysis is skipped (system still works)

**With API key**:
1. Go to https://console.anthropic.com/
2. Create API key
3. Add to `.env`:
```env
   ANTHROPIC_API_KEY=your_actual_key_here
```

### TikTok Collection

**Default mode**: Scraping (no API needed, may be blocked)

**API mode** (if you have TikTok API access):
```env
TIKTOK_MODE=api
TIKTOK_API_URL=your_tiktok_api_url
TIKTOK_API_KEY=your_tiktok_api_key
```

## Feature Matrix

| Feature | Works Without APIs | Full Functionality |
|---------|-------------------|-------------------|
| Steam Collection | ✅ Yes | ✅ Yes |
| Itch Collection | ✅ Yes | ✅ Yes |
| Wishlist Ranks (EWI) | ✅ Yes | ✅ Yes |
| YouTube Videos | ⚠️ Mock data | ✅ Real data |
| TikTok Videos | ⚠️ Mock/scraped | ✅ API data |
| Comment Analysis | ❌ Skipped | ✅ Full LLM analysis |
| Investment Scoring | ✅ Yes (basic) | ✅ Yes (full) |

## Testing Configuration

To verify your configuration:
```bash
# Test database connection
docker-compose exec postgres psql -U postgres -d game_scout -c "SELECT 1;"

# Test Redis connection
docker-compose exec redis redis-cli ping

# Test YouTube (if configured)
curl -X POST "http://localhost:8000/api/v1/narrative/test-youtube-collector?game_id=YOUR_GAME_ID"

# Test investment scoring
curl -X POST "http://localhost:8000/api/v1/narrative/test-investment-scoring?game_id=YOUR_GAME_ID"

# View analytics dashboard
curl http://localhost:8000/api/v1/analytics/dashboard
```

## Advanced Configuration

### Custom Scoring Weights

Adjust investment scoring formulas in `.env`:
```env
PP_WEIGHT=0.4   # Product Potential importance
GTM_WEIGHT=0.3  # Go-to-Market importance
GAP_WEIGHT=0.3  # GAP (difference) importance
```

### Collection Limits

Control how much data is collected:
```env
STEAM_COLLECTION_LIMIT=100
ITCH_COLLECTION_LIMIT=50
WISHLIST_RANK_LIMIT=100
COMMENT_SAMPLE_SIZE=200
```

### Schedule Configuration

Celery Beat schedules are configured in `apps/worker/celery_app.py`:
- Steam collection: 07:00 daily
- Itch collection: 07:15 daily
- Wishlist ranks: 06:30 daily

To change schedules, modify the `celery_beat_schedule` in `celery_app.py`.

## Troubleshooting

### "YouTube API key not configured"
- System will use mock data
- Add real API key to `.env` for actual YouTube data

### "LLM API key not configured"
- Comment analysis will be skipped
- Add Anthropic API key to `.env` for full analysis

### "TikTok scraping blocked"
- TikTok actively blocks scrapers
- System will generate mock data
- Consider getting official TikTok API access

### Database connection errors
- Ensure PostgreSQL container is running: `docker-compose ps`
- Check DATABASE_URL in `.env`
- Restart containers: `docker-compose restart`

## Production Deployment

For production use:

1. **Security**:
```env
   DEBUG=false
   # Use strong passwords for database
   # Restrict CORS origins in main.py
```

2. **Performance**:
```env
   # Increase worker concurrency
   # Add connection pooling
   # Enable Redis persistence
```

3. **Monitoring**:
   - Enable Celery events
   - Add logging aggregation
   - Set up health checks

4. **Backup**:
   - Regular PostgreSQL backups
   - Environment file backup
   - Redis snapshot configuration
