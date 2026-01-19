"""
Middleware for request correlation and structured logging
"""
import logging
import uuid
import json
import os
from datetime import datetime
from typing import Dict, Any
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# Sensitive fields that should never appear in logs
SENSITIVE_FIELDS = {
    'password', 'api_key', 'secret', 'token', 'private_key',
    'webhook_url', 'smtp_password', 'fred_api_key'
}


class RedactingFormatter(logging.Formatter):
    """Custom formatter that redacts sensitive fields"""

    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)

    def format(self, record):
        # Format the log message
        message = super().format(record)

        # Redact sensitive values if present in JSON
        try:
            if '{' in message and '}' in message:
                # Try to parse as JSON
                obj = json.loads(message)
                redacted = self._redact_object(obj)
                return json.dumps(redacted)
        except (json.JSONDecodeError, ValueError):
            pass

        return message

    def _redact_object(self, obj: Any) -> Any:
        """Recursively redact sensitive fields from object"""
        if isinstance(obj, dict):
            return {
                k: '******' if k.lower() in SENSITIVE_FIELDS else self._redact_object(v)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [self._redact_object(item) for item in obj]
        else:
            return obj


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID and correlation tracking"""

    async def dispatch(self, request: Request, call_next):
        # Generate or extract request ID
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))

        # Add request ID to request state
        request.state.request_id = request_id

        # Process request
        start_time = datetime.utcnow()
        response = await call_next(request)

        # Calculate duration
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Add request ID to response headers
        response.headers['X-Request-ID'] = request_id

        # Log request (with sensitive data redacted)
        log_data = {
            'request_id': request_id,
            'method': request.method,
            'path': request.url.path,
            'status_code': response.status_code,
            'duration_seconds': duration,
            'client': request.client.host if request.client else None
        }

        # Log in appropriate format based on LOG_FORMAT env var
        log_format = os.getenv('LOG_FORMAT', 'text').lower()

        if log_format == 'json':
            logger.info(json.dumps(log_data))
        else:
            logger.info(
                f"request_id={request_id} "
                f"method={request.method} "
                f"path={request.url.path} "
                f"status={response.status_code} "
                f"duration={duration:.3f}s"
            )

        return response


def setup_logging():
    """Configure logging with file rotation and redaction"""
    log_format = os.getenv('LOG_FORMAT', 'text').lower()
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

    # Create logs directory
    os.makedirs('logs', exist_ok=True)

    # Import RotatingFileHandler
    from logging.handlers import RotatingFileHandler

    # Setup formatters
    if log_format == 'json':
        formatter = RedactingFormatter(
            fmt='%(message)s',
            datefmt=None
        )
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # File handler with rotation
    file_handler = RotatingFileHandler(
        'logs/app.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, log_level))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level))

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger.info("Logging configured: format=%s, level=%s", log_format, log_level)
