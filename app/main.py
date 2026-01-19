"""
FastAPI application main entry point
"""
import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.responses import RedirectResponse, JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.db.schema import DatabaseManager
from app.ingest import IngestionPipeline
from app.api import routes

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global database manager
db_manager: Optional[DatabaseManager] = None

# Scheduler for daily ingestion
scheduler: Optional[BackgroundScheduler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global db_manager, scheduler

    # Startup
    logger.info("Starting application...")

    # Initialize database
    db_manager = DatabaseManager(settings.db_path)
    db_manager.connect()
    db_manager.initialize_schema()
    routes.set_db_manager(db_manager)
    logger.info("Database initialized")

    # Start scheduler if enabled
    if settings.scheduler_enabled:
        scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)

        # Schedule daily ingestion
        trigger = CronTrigger.from_crontab(
            f'{settings.scheduler_daily_time.split(":")[1]} '
            f'{settings.scheduler_daily_time.split(":")[0]} * * *'
        )

        scheduler.add_job(
            run_daily_ingestion,
            trigger=trigger,
            id='daily_ingestion',
            name='Daily Ingestion',
            replace_existing=True
        )

        scheduler.start()
        logger.info(f"Scheduled daily ingestion at {settings.scheduler_daily_time} {settings.scheduler_timezone}")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler stopped")

    if db_manager:
        db_manager.close()
        logger.info("Database connection closed")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# Redirect legacy (Jinja) UI routes to the Next.js frontend by default.
# This keeps the backend as API/DB/ingest engine, and makes http://127.0.0.1:3002 the canonical UI.
@app.middleware("http")
async def legacy_ui_redirect_middleware(request: Request, call_next):
    if settings.legacy_ui_enabled:
        return await call_next(request)

    if request.method != "GET":
        return await call_next(request)

    path = request.url.path or "/"
    if (
        path.startswith("/api")
        or path.startswith("/healthz")
        or path.startswith("/readyz")
        or path.startswith("/metrics")
        or path.startswith("/static")
        or path.startswith("/docs")
        or path.startswith("/openapi.json")
        or path.startswith("/redoc")
        or path.startswith("/report")
    ):
        return await call_next(request)

    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(url=f"{settings.frontend_url}{path}", status_code=307)

    return await call_next(request)

# CORS (needed for embedded Lai_suat Next.js UI on a different local port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3001",
        "http://localhost:3001",
        "http://127.0.0.1:3002",
        "http://localhost:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (optional).
# Note: backend is API-only; static assets are only needed if present for legacy pages.
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include API routes
app.include_router(routes.router, tags=["api"])


def run_daily_ingestion():
    """Run daily ingestion task"""
    logger.info("Running scheduled daily ingestion")
    try:
        if not db_manager:
            raise RuntimeError("Database not initialized")
        pipeline = IngestionPipeline(db_manager=db_manager)
        pipeline.run_daily()
    except Exception as e:
        logger.error(f"Scheduled ingestion failed: {e}")


@app.get("/")
async def root():
    """Backend root (API-only). UI lives in Next.js."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "ui": settings.frontend_url,
        "api_prefix": "/api",
    }


@app.get("/report/daily.pdf")
async def daily_pdf_report(target_date: Optional[str] = None):
    """Generate and return daily PDF report"""
    from app.reports.pdf_daily import DailyPDFReportGenerator
    from datetime import datetime
    from fastapi.responses import FileResponse

    try:
        if target_date:
            target = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            target = date.today()

        generator = DailyPDFReportGenerator(db_manager)
        pdf_path = generator.generate_report(target)

        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"daily_{target.strftime('%Y%m%d')}.pdf"
        )
    except Exception as e:
        logger.error(f"Error generating PDF report: {e}")
        return JSONResponse(content={"error": "Error generating PDF", "detail": str(e)}, status_code=500)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.app_version}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
