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