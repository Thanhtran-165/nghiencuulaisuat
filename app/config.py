"""
Application configuration using pydantic-settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path
import os
import sys
import shutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def _default_state_dir() -> Path:
    """
    Default state directory for local runs.

    Goal: keep DB_PATH/RAW_DATA_PATH consistent across:
    - manual `python -m app.ingest ...`
    - `uvicorn app.main:app` runs
    - scripts/LaunchAgents (macOS)
    """
    # Respect explicit override if user set it.
    env_state_dir = os.environ.get("STATE_DIR")
    if env_state_dir:
        return Path(env_state_dir).expanduser()

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "vn-bond-lab"

    # Linux: prefer XDG, else fallback to ~/.local/state
    if sys.platform.startswith("linux"):
        base = os.environ.get("XDG_STATE_HOME")
        if base:
            return Path(base).expanduser() / "vn-bond-lab"
        return Path.home() / ".local" / "state" / "vn-bond-lab"

    # Default fallback for other OSes / environments.
    return PROJECT_ROOT / ".local-data"


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        # Resolve relative to project root so the app can be started from any CWD.
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "vn-bond-lab"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_url: str = "http://127.0.0.1:3002"
    legacy_ui_enabled: bool = False

    # Database
    db_path: str = str(_default_state_dir() / "bonds.duckdb")

    # Data Collection
    start_date_default: str = "2013-01-01"
    rate_limit_seconds: float = 1.0
    max_concurrent_requests: int = 3
    request_timeout: int = 30
    max_retries: int = 3

    # Scheduler
    scheduler_enabled: bool = False
    scheduler_daily_time: str = "18:05"
    scheduler_timezone: str = "Asia/Ho_Chi_Minh"

    # Data Quality gate
    # Default: advisory (does NOT block analytics compute).
    # Set DQ_ENFORCE_BLOCK=true to block analytics when DQ status is FAIL.
    dq_enforce_block: bool = False

    # Providers
    hnx_base_url: str = "https://hnx.vn"
    hnx_ftp_base_url: str = "https://owa.hnx.vn/ftp"
    sbv_base_url: str = "https://www.sbv.gov.vn"
    abo_base_url: str = "https://asianbondsonline.adb.org"

    # Local interest-rate project (Lai_suat) bridge (Optional)
    lai_suat_root: str = str(PROJECT_ROOT / "Lai_suat")
    lai_suat_db_path: str = str(PROJECT_ROOT / "Lai_suat" / "data" / "rates.db")
    lai_suat_run_scraper: bool = False  # Optional: run scraper before importing
    # Lai_suat source selection:
    # Prefer high-quality sources (lower priority number). Default: only priority=1 (Timo).
    # Set to 999 to allow all sources.
    lai_suat_max_source_priority: int = 1

    # Playwright
    playwright_headless: bool = True
    playwright_timeout: int = 30000

    # Raw Data Storage
    raw_data_path: str = str(_default_state_dir() / "raw")
    enable_raw_storage: bool = True

    # Trading Economics (Optional)
    trading_economics_api_key: Optional[str] = None

    # FRED (Federal Reserve Economic Data) - Optional
    fred_api_key: Optional[str] = None

    # Global Data Configuration
    global_series_enabled: bool = False  # Auto-enabled if FRED API key provided

    # Observability
    log_format: str = "text"  # "text" or "json"

    # Admin Authentication (canonical naming)
    # Note: BASIC_AUTH_* is deprecated but still supported for backwards compatibility
    admin_auth_enabled: bool = False
    admin_user: Optional[str] = None
    admin_password: Optional[str] = None

    # Deprecated: Use ADMIN_AUTH_* instead
    basic_auth_enabled: Optional[bool] = None
    basic_auth_username: Optional[str] = None
    basic_auth_password: Optional[str] = None

    # Metrics Endpoint Authentication
    metrics_auth_enabled: bool = False  # Require Basic Auth for /metrics endpoint

    # Demo Mode
    demo_mode: bool = False  # Enable demo mode with synthetic data
    demo_db_path: Optional[str] = None  # Separate DB path for demo data
    override_demo_ingest: bool = False  # Allow provider ingestion in demo mode


# Global settings instance
settings = Settings()


def _apply_backwards_compatibility():
    """
    Apply backwards compatibility for deprecated environment variables.

    Maps BASIC_AUTH_* -> ADMIN_AUTH_* with logging.
    Called once at module load.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Map BASIC_AUTH_ENABLED -> ADMIN_AUTH_ENABLED
    if settings.basic_auth_enabled is not None:
        if not settings.admin_auth_enabled:
            settings.admin_auth_enabled = settings.basic_auth_enabled
            logger.warning(
                "BASIC_AUTH_ENABLED is deprecated. Use ADMIN_AUTH_ENABLED instead. "
                "Mapping BASIC_AUTH_ENABLED=%s to ADMIN_AUTH_ENABLED.",
                settings.basic_auth_enabled
            )

    # Map BASIC_AUTH_USERNAME -> ADMIN_USER
    if settings.basic_auth_username is not None and settings.admin_user is None:
        settings.admin_user = settings.basic_auth_username
        logger.warning(
            "BASIC_AUTH_USERNAME is deprecated. Use ADMIN_USER instead. "
            "Mapping value (not logging for security)."
        )

    # Map BASIC_AUTH_PASSWORD -> ADMIN_PASSWORD
    if settings.basic_auth_password is not None and settings.admin_password is None:
        settings.admin_password = settings.basic_auth_password
        logger.warning(
            "BASIC_AUTH_PASSWORD is deprecated. Use ADMIN_PASSWORD instead. "
            "Mapping value (not logging for security)."
        )

    # Auto-enable global series if FRED is configured.
    if settings.fred_api_key and not settings.global_series_enabled:
        settings.global_series_enabled = True
        logger.info("FRED_API_KEY detected; enabling global_series_enabled.")


# Apply backwards compatibility once at module load
_apply_backwards_compatibility()


def _lockout_legacy_repo_duckdb_path() -> None:
    """
    Prevent accidentally using the legacy repo-local DuckDB file.

    Historically, the project stored the DuckDB file at:
      <repo>/.local-data/bonds.duckdb

    The canonical local location is now:
      ~/Library/Application Support/vn-bond-lab/bonds.duckdb  (macOS)
      ~/.local/state/vn-bond-lab/bonds.duckdb               (Linux, unless XDG_STATE_HOME)

    This guard helps avoid "split brain" where the UI and services point at different DB files.
    """
    allow_legacy = os.environ.get("ALLOW_LEGACY_DB_PATH", "").strip().lower() in {"1", "true", "yes"}
    if allow_legacy:
        return

    legacy_repo_db = (PROJECT_ROOT / ".local-data" / "bonds.duckdb").resolve()

    try:
        configured = Path(settings.db_path).expanduser()
        configured_resolved = configured.resolve()
    except Exception:
        configured_resolved = Path(settings.db_path).expanduser()

    if configured_resolved != legacy_repo_db:
        return

    canonical = (_default_state_dir() / "bonds.duckdb").expanduser().resolve()

    # If the legacy DB exists but the canonical one doesn't, migrate by copying once.
    if legacy_repo_db.exists() and not canonical.exists():
        canonical.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(legacy_repo_db), str(canonical))
        settings.db_path = str(canonical)
        import logging

        logging.getLogger(__name__).warning(
            "DB_PATH pointed to legacy repo DB (%s). Migrated to canonical state DB (%s). "
            "To bypass this guard, set ALLOW_LEGACY_DB_PATH=true.",
            str(legacy_repo_db),
            str(canonical),
        )
        return

    # Otherwise, hard-fail so we never keep using the wrong file by accident.
    raise RuntimeError(
        "DB_PATH points to the legacy repo DB file (.local-data/bonds.duckdb). "
        f"Please unset DB_PATH (recommended) or set DB_PATH to the canonical state DB at: {canonical}. "
        "If you need to migrate, run: scripts/migrate_repo_db_to_state_dir.sh. "
        "To bypass (not recommended), set ALLOW_LEGACY_DB_PATH=true."
    )


# Enforce DB path guard at module load (safe for local dev).
_lockout_legacy_repo_duckdb_path()


def get_raw_data_path(provider: str) -> Path:
    """Get the raw data storage path for a specific provider"""
    base_path = Path(settings.raw_data_path)
    provider_path = base_path / provider
    provider_path.mkdir(parents=True, exist_ok=True)
    return provider_path
