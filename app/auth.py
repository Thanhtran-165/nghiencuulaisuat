"""
Optional Basic Authentication for Admin Routes

Protects /admin/* and /api/admin/* routes when ADMIN_AUTH_ENABLED=true
"""
import base64
import binascii
import logging
import secrets
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBasic()


def is_admin_auth_enabled() -> bool:
    """Check if admin auth is enabled"""
    return settings.admin_auth_enabled


def get_admin_credentials() -> tuple[str, str]:
    """Get admin credentials from settings"""
    username = settings.admin_user or 'admin'
    password = settings.admin_password or ''
    return username, password


async def verify_admin_auth(request: Request) -> Optional[HTTPException]:
    """
    Verify admin authentication for request

    Returns None if auth is disabled or valid, HTTPException if invalid
    """
    if not is_admin_auth_enabled():
        return None

    # Check for Authorization header
    auth_header = request.headers.get('Authorization')

    if not auth_header:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        # Parse Basic Auth
        scheme, credentials = auth_header.split(' ', 1)
        if scheme.lower() != 'basic':
            raise ValueError("Invalid auth scheme")

        decoded = base64.b64decode(credentials).decode('utf-8')
        username, password = decoded.split(':', 1)

        # Verify credentials
        admin_user, admin_pass = get_admin_credentials()

        if not secrets.compare_digest(username, admin_user):
            logger.warning(f"Admin auth failed: invalid username '{username}'")
            return HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Basic"},
            )

        if not secrets.compare_digest(password, admin_pass):
            logger.warning(f"Admin auth failed: invalid password for user '{username}'")
            return HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Basic"},
            )

        # Auth successful
        logger.info(f"Admin auth successful: {username}")
        return None

    except (ValueError, binascii.Error, UnicodeDecodeError) as e:
        logger.warning(f"Admin auth failed: invalid credentials format")
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


async def require_admin_auth(request: Request):
    """
    Dependency for FastAPI routes that require admin authentication

    Usage:
        @router.get("/api/admin/something")
        async def admin_endpoint(request: Request):
            await require_admin_auth(request)
            # ... endpoint logic
    """
    error = await verify_admin_auth(request)
    if error:
        raise error


def is_admin_route(path: str) -> bool:
    """Check if path is an admin route"""
    return path.startswith('/admin/') or path.startswith('/api/admin/')
