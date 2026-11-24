"""
backend/main.py

FastAPI application entry point for the Automated Data Analyst backend.
Run locally with:

    uvicorn backend.main:app --reload --port 8000

The frontend (frontend/index.html) is a static HTML/CSS/JS app that talks to
this API over REST; no Node.js build step is required for Version 1.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import (
    ai_routes,
    analytics_routes,
    cleaning_routes,
    dashboard_routes,
    database_routes,
    profile_routes,
    sql_routes,
    upload_routes,
)
from backend.config import get_settings

settings = get_settings()
from backend.security import authenticate, validate_deployment
validate_deployment()

app = FastAPI(
    title="Automated Data Analyst API",
    description=(
        "Dataset-adaptive backend for automated data cleaning, manipulation, "
        "analytics, insight detection, visualization and dashboard generation."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_routes.router)
app.include_router(profile_routes.router)
app.include_router(cleaning_routes.router)
app.include_router(database_routes.router)
app.include_router(sql_routes.router)
app.include_router(analytics_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(ai_routes.router)
from backend.api import project_routes
app.include_router(project_routes.router)
app.middleware("http")(authenticate)


from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    if (FRONTEND_DIR / "css").exists():
        app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
    if (FRONTEND_DIR / "js").exists():
        app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    if (FRONTEND_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")


from backend import database as db
from backend.utils.logger import get_logger
from backend.utils.sanitizer import mask_secrets
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = get_logger()


@app.middleware("http")
async def check_browser_origin(request: Request, call_next):
    # CORS controls response visibility, not whether a browser can send writes.
    origin = request.headers.get("origin")
    allowed = set(settings.cors_origins) | {"http://localhost:8000", "http://127.0.0.1:8000"}
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        same_origin = str(request.base_url).rstrip("/")
        if origin not in allowed and origin != same_origin:
            return JSONResponse(status_code=403, content={"detail": "Cross-origin write request blocked."})
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    safe_detail = mask_secrets(exc.detail if isinstance(exc.detail, str) else str(exc.detail))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": safe_detail,
            "detail": safe_detail,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled server error at %s %s: %s", request.method, request.url.path, type(exc).__name__)
    safe_detail = "An unexpected server error occurred. Please retry or check the local server logs."
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal Server Error",
            "detail": safe_detail,
        },
    )


@app.get("/health")
def health():
    current_settings = get_settings()
    db_configured = db.is_configured()
    db_connected = db.is_connected()
    db_name = db.get_current_database_name()
    return {
        "status": "healthy",
        "app": "Automated Data Analyst",
        "version": "1.0.0",
        "database_connected": db_connected,
        "database_configured": db_configured,
        "database_name": db_name,
        "ai_configured": current_settings.ai_enabled,
        "ai_enabled": current_settings.ai_enabled,
        "ai_model": current_settings.ai_model,
        "debug": current_settings.debug,
    }


@app.get("/api/health")
def api_health():
    return health()


@app.get("/api/status")
def root():
    return health()

