"""
ChatKit Session API endpoints.

Provides session management for ChatKit frontend clients.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import logging
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional

from middleware import auth_middleware, optional_auth_middleware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chatkit", tags=["ChatKit Session"])

# In-memory session store (for production, use Redis)
# Format: {client_secret: {user_id: str, expires_at: datetime}}
_session_store = {}


def cleanup_expired_sessions():
    """Remove expired sessions from store."""
    now = datetime.utcnow()
    expired = [k for k, v in _session_store.items() if v["expires_at"] < now]
    for key in expired:
        del _session_store[key]


def generate_client_secret(user_id: str, ttl_hours: int = 24) -> str:
    """
    Generate a client secret for ChatKit session.

    Args:
        user_id: User identifier
        ttl_hours: Time-to-live in hours

    Returns:
        str: Client secret token
    """
    # Cleanup old sessions
    cleanup_expired_sessions()

    # Generate secure random token
    client_secret = f"cs_{secrets.token_urlsafe(32)}"

    # Store session
    _session_store[client_secret] = {
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(hours=ttl_hours),
    }

    logger.info(f"Generated client secret for user {user_id}")
    return client_secret


def validate_client_secret(client_secret: str) -> Optional[str]:
    """
    Validate a client secret and return associated user_id.

    Args:
        client_secret: Client secret token

    Returns:
        Optional[str]: User ID if valid, None otherwise
    """
    cleanup_expired_sessions()

    session = _session_store.get(client_secret)
    if not session:
        return None

    if session["expires_at"] < datetime.utcnow():
        del _session_store[client_secret]
        return None

    return session["user_id"]


@router.post("/session")
async def create_session(user_id: str = Depends(optional_auth_middleware)):
    """
    Create a new ChatKit client session.

    This endpoint generates a client_secret that the ChatKit frontend
    can use to authenticate API requests.

    The client_secret is valid for 24 hours.

    Args:
        user_id: User ID from auth middleware

    Returns:
        dict: Contains client_secret and metadata

    Example Response:
        {
            "client_secret": "cs_abc123...",
            "expires_in": 86400,
            "user_id": "user_123"
        }
    """
    try:
        # Generate client secret (24 hour TTL)
        client_secret = generate_client_secret(user_id, ttl_hours=24)

        return JSONResponse(
            status_code=200,
            content={
                "client_secret": client_secret,
                "expires_in": 86400,  # 24 hours in seconds
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        logger.error(f"Error creating ChatKit session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to create ChatKit session"
        )


@router.post("/session/refresh")
async def refresh_session(
    client_secret: str,
    user_id: str = Depends(auth_middleware)
):
    """
    Refresh an existing ChatKit session.

    Validates the current client_secret and issues a new one if valid.

    Args:
        client_secret: Current client secret
        user_id: User ID from auth middleware

    Returns:
        dict: New client_secret and metadata
    """
    try:
        # Validate current session
        session_user_id = validate_client_secret(client_secret)

        if not session_user_id or session_user_id != user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired client secret"
            )

        # Delete old session
        del _session_store[client_secret]

        # Generate new client secret
        new_client_secret = generate_client_secret(user_id, ttl_hours=24)

        return JSONResponse(
            status_code=200,
            content={
                "client_secret": new_client_secret,
                "expires_in": 86400,
                "user_id": user_id,
                "refreshed_at": datetime.utcnow().isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing ChatKit session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh ChatKit session"
        )


@router.delete("/session")
async def delete_session(
    client_secret: str,
    user_id: str = Depends(auth_middleware)
):
    """
    Delete a ChatKit session (logout).

    Args:
        client_secret: Client secret to invalidate
        user_id: User ID from auth middleware

    Returns:
        dict: Confirmation message
    """
    try:
        # Validate session belongs to user
        session_user_id = validate_client_secret(client_secret)

        if not session_user_id or session_user_id != user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired client secret"
            )

        # Delete session
        del _session_store[client_secret]

        logger.info(f"Deleted ChatKit session for user {user_id}")

        return JSONResponse(
            status_code=200,
            content={
                "message": "Session deleted successfully",
                "user_id": user_id,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ChatKit session: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to delete ChatKit session"
        )


@router.get("/session/info")
async def get_session_info(user_id: str = Depends(auth_middleware)):
    """
    Get information about active sessions for the current user.

    Args:
        user_id: User ID from auth middleware

    Returns:
        dict: Session information
    """
    try:
        cleanup_expired_sessions()

        # Find all active sessions for this user
        active_sessions = [
            {
                "client_secret": secret[:10] + "...",  # Truncated for security
                "created_at": session["created_at"].isoformat(),
                "expires_at": session["expires_at"].isoformat(),
            }
            for secret, session in _session_store.items()
            if session["user_id"] == user_id
        ]

        return JSONResponse(
            status_code=200,
            content={
                "user_id": user_id,
                "active_sessions": len(active_sessions),
                "sessions": active_sessions,
            },
        )

    except Exception as e:
        logger.error(f"Error getting session info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get session info"
        )
