from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import logging
from .settings import get_settings
from . import db, schemas, health_checks

logger = logging.getLogger(__name__)


settings = get_settings()

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Run health checks on app startup."""
    logger.info("🔍 Running startup health checks...")
    health = health_checks.check_database_health()

    if health["ok"] and not health["migrations_pending"]:
        logger.info("✅ Database health check passed")
    elif health["migrations_pending"]:
        logger.warning("⚠️  Database health check found pending migrations:")
        for warning in health["warnings"]:
            logger.warning(f"   - {warning}")
        logger.warning("📋 Required migration: python3 -m app.migrations.run_migration add_observed_day.sql")
    else:
        logger.error("❌ Database health check failed")
        for warning in health["warnings"]:
            logger.error(f"   - {warning}")

    # Seed required series codes to prevent frontend/API mismatches.
    try:
        result = db.seed_required_series()
        if result.get("inserted", 0) > 0:
            logger.info(f"✅ Seeded missing series codes (inserted={result['inserted']})")
    except Exception as e:
        logger.warning(f"⚠️  Failed to seed required series codes: {e}")


@app.get("/health", response_model=schemas.HealthResponse)
def health():
    """Health check endpoint."""
    result = db.get_health()
    if not result["ok"]:
        raise HTTPException(status_code=500, detail="Database connection failed")
    return result


@app.get("/meta/latest", response_model=schemas.MetaLatestResponse)
def meta_latest():
    """Get latest metadata about sources and observations."""
    return db.get_meta_latest()


@app.get("/banks", response_model=list[str])
def banks():
    """Get all unique bank names."""
    return db.get_banks()


@app.get("/series", response_model=list[schemas.SeriesResponse])
def series():
    """Get all series."""
    return db.get_series()


@app.get("/latest", response_model=schemas.LatestRatesResponse)
def latest(
    series_code: str = Query(..., description="Series code (e.g., deposit_online, loan_the_chap)"),
    term_months: int | None = Query(None, description="Term in months (required for deposit series)"),
    sort: str = Query("rate_desc", description="Sort order: rate_desc, rate_asc, bank_asc")
):
    """
    Get latest rates for a specific series.

    - For deposit series (deposit_tai_quay, deposit_online): term_months is required
    - For loan series (loan_the_chap, loan_tin_chap): term_months should not be provided
    """
    try:
        rows = db.get_latest_rates(series_code, term_months, sort)
        return {
            "rows": rows,
            "meta": {
                "series_code": series_code,
                "term_months": term_months,
                "sort": sort,
                "count": len(rows)
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/history", response_model=schemas.HistoryResponse)
def history(
    bank_name: str | None = Query(None, description="Bank name (official parameter)"),
    bank: str | None = Query(None, description="Bank name (DEPRECATED alias for bank_name, will be removed in v2.0)"),
    series_code: str = Query(..., description="Series code"),
    term_months: int | None = Query(None, description="Term in months (required for deposit series)"),
    limit: int = Query(120, description="Maximum number of history points")
):
    """
    Get historical rates for a specific bank and series.

    - For deposit series: term_months is required
    - For loan series: term_months should not be provided
    """
    # Handle deprecated 'bank' alias
    if bank is not None:
        if bank_name is not None:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both 'bank' and 'bank_name'. Use 'bank_name' only."
            )
        logger.warning(f"Deprecated parameter 'bank' used (value: '{bank}'). Please use 'bank_name' instead.")
        bank_name = bank
    elif bank_name is None:
        raise HTTPException(
            status_code=400,
            detail="Must specify 'bank_name' parameter."
        )

    try:
        return db.get_history(bank_name, series_code, term_months, limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "Interest Rates API",
        "version": settings.API_VERSION,
        "endpoints": {
            "health": "/health",
            "meta": "/meta/latest",
            "banks": "/banks",
            "series": "/series",
            "latest": "/latest",
            "history": "/history"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
