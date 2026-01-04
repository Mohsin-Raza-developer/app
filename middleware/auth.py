"""
Better Auth session validation middleware.

Validates session tokens from Authorization header via Better Auth API.
"""

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
import httpx
import logging

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme
security = HTTPBearer()


async def validate_session(session_token: str) -> str:
    """
    Validate Better Auth session token via API and extract user_id.

    Args:
        session_token: Session token from Authorization header

    Returns:
        str: user_id from valid session

    Raises:
        HTTPException: If session is invalid or expired
    """
    try:
        # Call Better Auth API to validate session
        # Note: Using custom get-session endpoint instead of built-in /api/session
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.better_auth_url}/api/auth/get-session",
                headers={
                    "Authorization": f"Bearer {session_token}",
                    "Cookie": f"better-auth.session_token={session_token}",
                },
                timeout=10.0,
                follow_redirects=True,  # Follow redirects if any
            )

            if response.status_code != 200:
                logger.warning(f"Session validation failed: {response.status_code}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired session token",
                )

            session_data = response.json()

            # Extract user_id from session response
            if not session_data or "user" not in session_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid session data",
                )

            user_id = session_data["user"]["id"]
            logger.info(f"Session validated for user_id: {user_id}")
            return user_id

    except HTTPException:
        raise
    except httpx.TimeoutException:
        logger.error("Better Auth API timeout")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session validation failed",
        )


async def auth_middleware(request: Request, credentials: HTTPAuthorizationCredentials):
    """
    FastAPI dependency for session authentication.

    Args:
        request: FastAPI request object
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        str: user_id from valid session

    Raises:
        HTTPException: If authentication fails
    """
    session_token = credentials.credentials
    user_id = await validate_session(session_token)

    # Attach user_id to request state for downstream use
    request.state.user_id = user_id

    return user_id


async def optional_auth_middleware(
    request: Request,
    credentials: HTTPAuthorizationCredentials = None
) -> str:
    """
    Optional authentication middleware for demo/development.

    Falls back to anonymous user if no credentials provided.

    WARNING: FOR DEVELOPMENT/DEMO ONLY!
    In production, use auth_middleware to require authentication.

    Args:
        request: FastAPI request object
        credentials: Optional HTTP Bearer credentials

    Returns:
        str: user_id (authenticated or anonymous)
    """
    if credentials:
        try:
            session_token = credentials.credentials
            user_id = await validate_session(session_token)
            request.state.user_id = user_id
            request.state.is_authenticated = True
            logger.info(f"Authenticated user: {user_id}")
            return user_id
        except HTTPException as e:
            logger.warning(f"Auth failed, falling back to anonymous: {e.detail}")

    # Fall back to anonymous user for demo
    anonymous_id = "anonymous_demo_user"
    request.state.user_id = anonymous_id
    request.state.is_authenticated = False
    logger.info("Using anonymous demo user (development mode)")
    return anonymous_id
