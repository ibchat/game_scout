from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from apps.api.routers import narrative, analytics, morning_scan

app = FastAPI(
    title="Game Scout API",
    description="Game trend scout and pitch viability engine",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
# app.include_router(health.router, tags=["Health"])  # Commented out - not imported
# app.include_router(pitches.router, prefix="/pitches", tags=["Pitches"])  # Commented out
# app.include_router(trends.router, prefix="/trends", tags=["Trends"])  # Commented out
# app.include_router(games.router, prefix="/games", tags=["Games"])  # Commented out
# app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])  # Commented out
app.include_router(narrative.router, prefix="/api/v1", tags=["Narrative"])
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
app.include_router(morning_scan.router, prefix="/api/v1", tags=["Morning Scan"])

@app.on_event("startup")
async def startup_event():
    """Startup tasks"""
    pass

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown tasks"""
    pass

@app.get("/")
async def dashboard():
    """Serve dashboard HTML"""
    return FileResponse("apps/api/static/dashboard.html")

@app.get("/games-dashboard")
async def games_dashboard():
    """Serve games dashboard HTML"""
    return FileResponse("apps/api/static/games_dashboard.html")



@app.get("/final")
async def final_dashboard():
    """Final unified dashboard with Morning Scan"""
    return FileResponse("apps/api/static/unified_dashboard_final.html")

@app.get("/unified")
async def unified_dashboard():
    """Unified dashboard with all features"""
    return FileResponse("apps/api/static/unified_dashboard.html")

@app.get("/investor-dashboard")
async def investor_dashboard():
    return FileResponse("apps/api/static/investor_dashboard.html")

@app.get("/trends")
async def trends_page():
    return FileResponse("apps/api/static/trend_radar.html")

@app.get("/trend_simple.html")
async def trend_simple():
    return FileResponse("apps/api/static/trend_simple.html")

@app.get("/dashboard")
async def new_dashboard():
    return FileResponse("apps/api/static/game_scout_dashboard.html")

@app.get("/dashboard-v2")
async def dashboard_v2():
    return FileResponse("apps/api/static/game_scout_dashboard_v2.html")

# Add Relaunch Scout routes
from apps.api.routers import relaunch
app.include_router(relaunch.router, prefix="/api/v1", tags=["Relaunch Scout"])
