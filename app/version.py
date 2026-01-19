"""
Application Version and Build Information
"""
from datetime import datetime

__version__ = "1.0.0"
__build_date__ = datetime.utcnow().isoformat()


def get_version_info():
    """Get version and build information"""
    import os
    from app.config import settings

    return {
        "version": __version__,
        "build_date": __build_date__,
        "feature_flags": {
            "admin_auth_enabled": settings.admin_auth_enabled,
            "scheduler_enabled": settings.scheduler_enabled,
            "global_data_enabled": settings.global_series_enabled,
            "demo_mode_enabled": os.getenv('DEMO_MODE', 'false').lower() == 'true',
        }
    }


def get_version_string() -> str:
    """Get version string"""
    return __version__
