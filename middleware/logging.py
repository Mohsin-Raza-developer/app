"""
Request/Response logging middleware.

Logs all incoming requests with timing and user context.
"""

from fastapi import Request
import logging
import time

logger = logging.getLogger(__name__)


async def logging_middleware(request: Request, call_next):
    """
    Log all requests with timing and context.

    Args:
        request: FastAPI request
        call_next: Next middleware in chain

    Returns:
        Response with timing headers
    """
    start_time = time.time()

    # Extract user_id if available (set by auth middleware)
    user_id = getattr(request.state, "user_id", "anonymous")

    # Log request
    logger.info(
        f"Request: {request.method} {request.url.path} - User: {user_id}"
    )

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration = time.time() - start_time
    duration_ms = int(duration * 1000)

    # Add timing header
    response.headers["X-Process-Time"] = str(duration_ms)

    # Log response
    logger.info(
        f"Response: {request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration_ms}ms - "
        f"User: {user_id}"
    )

    return response
