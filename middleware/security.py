"""
Security headers middleware.

Adds security-related HTTP headers to all responses.
"""

from fastapi import Request
import logging

logger = logging.getLogger(__name__)


async def security_headers_middleware(request: Request, call_next):
    """
    Add security headers to all responses.

    Headers added:
    - Content-Security-Policy
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Strict-Transport-Security (if HTTPS)

    Args:
        request: FastAPI request
        call_next: Next middleware in chain

    Returns:
        Response with security headers
    """
    response = await call_next(request)

    # Content Security Policy
    # Allow Swagger UI from CDN (cdn.jsdelivr.net)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://generativelanguage.googleapis.com"
    )

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # XSS Protection
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # HSTS for HTTPS
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=()"
    )

    return response
