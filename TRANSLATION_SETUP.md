# Translation Setup Guide

## Overview

Intel module uses **LibreTranslate** (free, self-hosted) for translation by default. This ensures all content is translated to Russian before publication to Telegram.

## Quick Setup

### 1. LibreTranslate is automatically started

The `libretranslate` service is included in `docker-compose.yml` and starts automatically with `docker compose up -d`.

### 2. Configuration (optional)

Add to `.env` if you need custom settings:

```env
# Translation provider (default: libretranslate)
TRANSLATION_PROVIDER=libretranslate

# LibreTranslate URL (default: http://libretranslate:5000)
LIBRETRANSLATE_URL=http://libretranslate:5000

# LibreTranslate API key (optional, leave empty for no auth)
LIBRETRANSLATE_API_KEY=
```

### 3. Verify Translation Service

```bash
# Check health endpoint
curl http://localhost:8000/api/v1/intel/health

# Should return:
# {
#   "translation_ok": true,
#   ...
# }
```

Or test directly:

```bash
# Check LibreTranslate is running
curl http://localhost:5000/languages
```

## How It Works

1. **Free Translation First**: LibreTranslate is used for all translations
2. **LLM Fallback**: If LibreTranslate fails, falls back to LLM (OpenAI/Anthropic) if configured
3. **Strict Rule**: If translation unavailable, content is **not published** (skipped with reason)

## Translation Flow

```
Input Text (any language)
    ↓
Detect Language (heuristic or LibreTranslate)
    ↓
If Russian → Use as-is
    ↓
If not Russian → Translate via LibreTranslate
    ↓
If LibreTranslate fails → Try LLM fallback (if configured)
    ↓
If all fail → Skip publication (strict rule)
```

## Troubleshooting

**"Translation service not available"**
- Check LibreTranslate is running: `docker compose ps libretranslate`
- Check logs: `docker compose logs libretranslate`
- Verify health: `curl http://localhost:5000/languages`

**"Translation failed"**
- Check LibreTranslate logs for errors
- Verify network connectivity between containers
- Check if API key is required (if using hosted LibreTranslate)

**Slow translations**
- LibreTranslate may be slow on first request (model loading)
- Consider using API key for rate limiting
- Check container resources: `docker stats libretranslate`

## Advanced Configuration

### Using External LibreTranslate Instance

If you have a hosted LibreTranslate instance:

```env
LIBRETRANSLATE_URL=https://your-libretranslate-instance.com
LIBRETRANSLATE_API_KEY=your_api_key_here
```

### Disabling Translation (Not Recommended)

⚠️ **Warning**: Disabling translation violates strict Russian output policy.

If you must disable (for testing only):

1. Ensure all sources are already in Russian
2. Set `TRANSLATION_PROVIDER=none` (not implemented, will fail)
3. Or modify policy to allow non-Russian (not recommended)

## Security Notes

- LibreTranslate runs in Docker container (isolated)
- No external API calls (self-hosted)
- No API keys required by default
- All translation happens locally
