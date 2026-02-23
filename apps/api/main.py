from fastapi import FastAPI, Request, HTTPException, Header, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
import os
import logging

logger = logging.getLogger(__name__)

# импортируем модули роутеров
from apps.api.routers import (
    health,
    pitches,
    trends,
    trends_v1,
    analytics,
    games,
    morning_scan,
    narrative,
    youtube,
    reddit,
    yearly,
    system_admin,
    deals_v1,
    discord_discovery,
)

# relaunch может быть новым модулем — импорт отдельно,
# чтобы было проще отладить, если что-то не так
from apps.api.routers import relaunch


app = FastAPI(title="Game Scout API", version="0.1.0")


# ============================================================
# Public Tunnel Token Protection Middleware
# ============================================================

class PublicTunnelTokenMiddleware(BaseHTTPMiddleware):
    """
    Middleware для защиты публичного туннеля токеном.
    Проверяет X-Demo-Token header или ?token= query parameter.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Check if tunnel is enabled and token is set
        enable_tunnel = os.getenv("ENABLE_PUBLIC_TUNNEL", "0") == "1"
        demo_token = os.getenv("PUBLIC_DEMO_TOKEN", "").strip()
        
        # Skip protection if tunnel is disabled or token is not set
        if not enable_tunnel or not demo_token:
            return await call_next(request)
        
        # Skip protection for health check and root endpoints
        if request.url.path in ["/", "/health", "/api/v1/health"]:
            return await call_next(request)
        
        # Get token from header or query parameter
        token_header = request.headers.get("X-Demo-Token", "")
        token_query = request.query_params.get("token", "")
        provided_token = token_header or token_query
        
        # Check token
        if provided_token != demo_token:
            logger.warning(f"Invalid demo token attempt from {request.client.host} to {request.url.path}")
            return Response(
                content='{"detail":"Invalid or missing demo token"}',
                status_code=401,
                media_type="application/json"
            )
        
        return await call_next(request)


# Apply middleware
app.add_middleware(PublicTunnelTokenMiddleware)

# ============================================================
# Static + Dashboard
# ============================================================

app.mount("/static", StaticFiles(directory="apps/api/static"), name="static")


@app.get("/", tags=["Root"])
def root():
    return {"status": "ok", "service": "game_scout_api"}


@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
def dashboard():
    """Main dashboard with all tabs (System, Trends, Deals, Sources, Games, Relaunch, Actions)"""
    from pathlib import Path
    import os
    
    # game_scout_dashboard.html - основной дашборд со всеми вкладками включая Deals
    # Определяем базовую директорию проекта
    # __file__ = apps/api/main.py
    # .parent = apps/api
    # .parent.parent = apps
    # .parent.parent.parent = корень проекта
    
    try:
        # Вариант 1: относительно main.py (основной)
        base_dir = Path(__file__).parent.parent.parent
        dashboard_path = base_dir / "apps" / "api" / "static" / "game_scout_dashboard.html"
        
        # Если не найден, пробуем другие варианты
        if not dashboard_path.exists():
            # Вариант 2: относительно текущей рабочей директории
            dashboard_path = Path("apps") / "api" / "static" / "game_scout_dashboard.html"
            
        if not dashboard_path.exists():
            # Вариант 3: абсолютный путь
            dashboard_path = Path(os.getcwd()) / "apps" / "api" / "static" / "game_scout_dashboard.html"
        
        if not dashboard_path.exists():
            error_msg = f"Dashboard file not found. Base dir: {base_dir}, CWD: {os.getcwd()}"
            logger.error(error_msg)
            return HTMLResponse(
                content=f"<h1>Error</h1><p>{error_msg}</p><p>Tried: {dashboard_path}</p>",
                status_code=500
            )
        
        with open(dashboard_path, "r", encoding="utf-8") as f:
            content = f.read()
            return HTMLResponse(
                content=content,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                    "Content-Type": "text/html; charset=utf-8"
                }
            )
    except Exception as e:
        logger.error(f"Failed to load dashboard: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<h1>Error</h1><p>Failed to load dashboard: {str(e)}</p><pre>{type(e).__name__}</pre>",
            status_code=500
        )


# ============================================================
# Routers
# ============================================================
# Единый префикс API v1
API_V1 = "/api/v1"

# Неформатированные (старые) роуты
app.include_router(health.router, prefix="")
app.include_router(health.router, prefix=API_V1)  # Также доступен по /api/v1/health
app.include_router(pitches.router, prefix="/pitches")
app.include_router(trends.router, prefix="/trends")

app.include_router(narrative.router, prefix=API_V1)
app.include_router(analytics.router, prefix=API_V1)
app.include_router(morning_scan.router, prefix=API_V1)
app.include_router(games.router, prefix=API_V1)
app.include_router(youtube.router, prefix=API_V1)
app.include_router(reddit.router, prefix=API_V1)
app.include_router(yearly.router, prefix=API_V1)
app.include_router(trends_v1.router, prefix=API_V1)
app.include_router(system_admin.router, prefix=API_V1)
app.include_router(deals_v1.router, prefix=API_V1)
app.include_router(discord_discovery.router, prefix=API_V1)

# ✅ ВАЖНО: relaunch подключаем ТОЛЬКО к /api/v1
# а prefix="/relaunch" задается ВНУТРИ relaunch.py
app.include_router(relaunch.router, prefix=API_V1)

# VOY module (read-only overlay) - always try to include
try:
    from apps.api.routers import voy
    app.include_router(voy.router, prefix=API_V1)
    logger.info("✅ VOY router included successfully")
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"⚠️ VOY module not available: {e}")
except Exception as e:
    logger.error(f"❌ Error including VOY router: {e}", exc_info=True)

# Intel module - always try to include (guarded by feature flag)
try:
    from apps.intel.api import router as intel_router
    app.include_router(intel_router.router, prefix=API_V1)
    logger.info("✅ Intel router included successfully")
    
    # Auto-seed Intel sources on startup (idempotent)
    # Also check alembic revision and key columns
    try:
        from apps.intel.config import is_intel_enabled
        from apps.intel.db.seed_sources import seed_intel_sources, get_active_sources_count
        from apps.db.session import SessionLocal
        from sqlalchemy import text, inspect
        
        if is_intel_enabled():
            db = SessionLocal()
            try:
                # A4: Check alembic current revision
                try:
                    result = db.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))
                    row = result.fetchone()
                    alembic_rev = row[0] if row else None
                    logger.info(f"[INTEL] Alembic current revision: {alembic_rev}")
                    
                    # Check if we're at head (017)
                    if alembic_rev and "017" not in str(alembic_rev):
                        logger.warning(f"[INTEL] Alembic revision is {alembic_rev}, expected 017_created_at_publish_log. Run: alembic upgrade head")
                except Exception as alembic_err:
                    logger.warning(f"[INTEL] Could not check alembic revision: {alembic_err}")
                
                # A4: Check key columns existence
                try:
                    inspector = inspect(db.bind)
                    
                    # Check intel_extracted_items.extracted_at
                    extracted_cols = [col['name'] for col in inspector.get_columns('intel_extracted_items')]
                    extracted_at_exists = 'extracted_at' in extracted_cols
                    logger.info(f"[INTEL] intel_extracted_items.extracted_at exists: {extracted_at_exists}")
                    
                    # Check intel_publish_log.created_at
                    publish_cols = [col['name'] for col in inspector.get_columns('intel_publish_log')]
                    created_at_exists = 'created_at' in publish_cols
                    logger.info(f"[INTEL] intel_publish_log.created_at exists: {created_at_exists}")
                    
                    # Check intel_sources health fields
                    source_cols = [col['name'] for col in inspector.get_columns('intel_sources')]
                    country_exists = 'country' in source_cols
                    weight_exists = 'weight' in source_cols
                    logger.info(f"[INTEL] intel_sources.country exists: {country_exists}, weight exists: {weight_exists}")
                    
                    if not extracted_at_exists or not created_at_exists or not country_exists:
                        logger.warning(f"[INTEL] ⚠️  Missing key columns! Run migrations 015-017: alembic upgrade head")
                except Exception as col_check_err:
                    logger.warning(f"[INTEL] Could not check column existence: {col_check_err}")
                
                # Auto-seed sources
                active_count = get_active_sources_count(db)
                if active_count < 30:
                    logger.info(f"[INTEL] Auto-seeding Intel sources (current: {active_count}, target: >=30)")
                    stats = seed_intel_sources(db, force=False)
                    logger.info(f"[INTEL] Sources seed: added={stats['added']}, updated={stats['updated']}, skipped={stats['skipped']}, errors={stats['errors']}")
                else:
                    logger.info(f"[INTEL] Sources already seeded ({active_count} active sources)")
            except Exception as seed_err:
                logger.warning(f"[INTEL] Failed to auto-seed Intel sources: {seed_err}")
            finally:
                db.close()
    except Exception as seed_import_err:
        logger.warning(f"[INTEL] Could not import seed_sources: {seed_import_err}")
        
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"⚠️ Intel module not available: {e}")
except Exception as e:
    logger.error(f"❌ Error including Intel router: {e}", exc_info=True)