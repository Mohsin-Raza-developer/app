"""
Rate limiting middleware.

Limits requests to 60 per minute per authenticated user.
"""

from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# In-memory rate limit tracking: {user_id: (request_count, window_start)}
rate_limit_store: Dict[str, Tuple[int, datetime]] = defaultdict(lambda: (0, datetime.now()))

# Rate limit configuration
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW = timedelta(minutes=1)


async def rate_limit_middleware(request: Request):
    """
    Rate limiting middleware for authenticated requests.

    Limits requests to 60 per minute per user_id.

    Args:
        request: FastAPI request object (must have request.state.user_id set by auth middleware)

    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    # Get user_id from request state (set by auth middleware)
    user_id = getattr(request.state, "user_id", None)

    if not user_id:
        # If no user_id in state, auth middleware hasn't run yet
        # This shouldn't happen if auth middleware is properly configured
        logger.warning("Rate limit middleware called without user_id in request state")
        return

    now = datetime.now()
    request_count, window_start = rate_limit_store[user_id]

    # Check if current window has expired
    if now - window_start >= RATE_LIMIT_WINDOW:
        # Reset window
        rate_limit_store[user_id] = (1, now)
        logger.debug(f"Rate limit window reset for user {user_id}")
        return

    # Increment request count
    request_count += 1
    rate_limit_store[user_id] = (request_count, window_start)

    # Check if rate limit exceeded
    if request_count > RATE_LIMIT_REQUESTS:
        # Calculate retry-after seconds
        window_end = window_start + RATE_LIMIT_WINDOW
        retry_after = int((window_end - now).total_seconds())

        logger.warning(
            f"Rate limit exceeded for user {user_id}: {request_count}/{RATE_LIMIT_REQUESTS} requests"
        )

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per minute.",
            headers={"Retry-After": str(retry_after)},
        )

    logger.debug(f"Rate limit check passed for user {user_id}: {request_count}/{RATE_LIMIT_REQUESTS} requests")
