from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

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
)

# relaunch может быть новым модулем — импорт отдельно,
# чтобы было проще отладить, если что-то не так
from apps.api.routers import relaunch


app = FastAPI(title="Game Scout API", version="0.1.0")

# ============================================================
# Static + Dashboard
# ============================================================

app.mount("/static", StaticFiles(directory="apps/api/static"), name="static")


@app.get("/", tags=["Root"])
def root():
    return {"status": "ok", "service": "game_scout_api"}


@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
def dashboard():
    # game_scout_dashboard.html лежит в apps/api/static/
    import os
    from pathlib import Path
    
    # Используем абсолютный путь для надежности
    base_dir = Path(__file__).parent.parent.parent
    dashboard_path = base_dir / "apps" / "api" / "static" / "game_scout_dashboard.html"
    
    try:
        with open(dashboard_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Добавляем версионирование для обхода кэша браузера
            # Заменяем в HTML ссылки на статические файлы с версией
            import hashlib
            version_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            # Добавляем meta-тег для версионирования
            if '<head>' in content:
                content = content.replace(
                    '<head>',
                    f'<head>\n  <meta name="dashboard-version" content="{version_hash}">'
                )
            return HTMLResponse(
                content=content,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    except FileNotFoundError:
        return HTMLResponse(
            content=f"<h1>Error</h1><p>Dashboard file not found at: {dashboard_path}</p>",
            status_code=500
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Error</h1><p>Failed to load dashboard: {str(e)}</p>",
            status_code=500
        )


# ============================================================
# Routers
# ============================================================
# Единый префикс API v1
API_V1 = "/api/v1"

# Неформатированные (старые) роуты
app.include_router(health.router, prefix="")
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

# ✅ ВАЖНО: relaunch подключаем ТОЛЬКО к /api/v1
# а prefix="/relaunch" задается ВНУТРИ relaunch.py
app.include_router(relaunch.router, prefix=API_V1)