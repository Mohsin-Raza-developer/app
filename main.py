"""
FastAPI application entry point.

Initializes the chatbot backend with ChatKit server integration.
"""

from fastapi import FastAPI, Request, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse
from contextlib import asynccontextmanager
import logging
from chatkit.server import StreamingResult
from sqlalchemy import text

from config import settings
from database import init_db, close_db
from middleware import setup_cors, auth_middleware, optional_auth_middleware, rate_limit_middleware
from middleware.logging import logging_middleware
from middleware.security import security_headers_middleware
from chatkit_server.chatkit_server import robotics_chatbot_server
from routers import chatkit_session
import signal
import sys

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server_debug.log", mode="a", encoding="utf-8")
    ],
    force=True
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting chatbot backend...")
    try:
        await init_db()
        logger.info("Database connection initialized")
    except Exception as e:
        # Log warning but don't crash - Neon serverless may be cold starting
        logger.warning(f"Database connection test failed (Neon cold start?): {e}")
        logger.info("Server will start anyway - database will connect on first request")

    yield

    # Shutdown
    logger.info("Shutting down chatbot backend...")
    try:
        await close_db()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Create FastAPI application
app = FastAPI(
    title="Physical AI Humanoid Robotics Chatbot",
    description="ChatKit-integrated backend for robotics textbook Q&A with RAG",
    version="1.0.0",
    lifespan=lifespan,
)

# Setup middleware
setup_cors(app)
app.middleware("http")(logging_middleware)
app.middleware("http")(security_headers_middleware)

# Include routers
app.include_router(chatkit_session.router)

# Graceful shutdown handler
def handle_shutdown_signal(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    logger.info(f"Received shutdown signal ({signum}), initiating graceful shutdown...")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_shutdown_signal)
signal.signal(signal.SIGINT, handle_shutdown_signal)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for uncaught errors.

    Returns ChatKit-compatible error format.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later.",
            "type": "server_error"
        },
    )

# Apply rate limiting to protected routes
# Note: Rate limit middleware depends on auth middleware setting request.state.user_id


@app.get("/health")
async def health_check():
    """
    Enhanced health check endpoint.

    Checks:
    - Database connection
    - Qdrant connection
    - Service status

    Returns:
        dict: Service status with component health
    """
    from database import engine
    from services.qdrant_service import qdrant_service

    health_status = {
        "status": "healthy",
        "service": "chatbot-backend",
        "version": "1.0.0",
        "components": {}
    }

    # Check database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    # Check Qdrant
    try:
        qdrant_service.qdrant_client.get_collections()
        health_status["components"]["qdrant"] = "healthy"
    except Exception as e:
        health_status["components"]["qdrant"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"

    return health_status


@app.get("/")
async def root():
    """
    Root endpoint.

    Returns:
        dict: Welcome message
    """
    return {
        "message": "Physical AI Humanoid Robotics Chatbot API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/chatkit")
async def chatkit_info():
    """
    ChatKit endpoint info (GET).

    Returns basic information about the ChatKit service.
    Used by ChatKit client for service discovery.
    """
    return {
        "service": "chatkit",
        "version": "1.0.0",
        "protocol": "chatkit-v1",
        "ready": True,
    }


@app.post("/chatkit")
async def chatkit_endpoint(request: Request):
    """
    ChatKit protocol endpoint.

    Handles all ChatKit operations:
    - thread.create: Create new conversation thread
    - message.create: Send message and get streaming AI response
    - threads.list: List user's conversation threads
    - thread.delete: Delete a thread

    Authentication is optional (demo mode).
    Rate limited to 60 requests/minute per user.

    Returns:
        StreamingResponse: SSE stream for message.create
        JSONResponse: JSON for other operations
    """
    # Handle MANDATORY authentication - NO anonymous access allowed
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning("Missing Authorization header - login required")
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Please login to use the chatbot. Authentication is required.",
                "type": "authentication_required"
            },
        )

    # Validate session token
    try:
        from middleware.auth import validate_session
        session_token = auth_header.replace("Bearer ", "")
        user_id = await validate_session(session_token)
        request.state.user_id = user_id
        request.state.is_authenticated = True
        logger.info(f"✅ Authenticated user: {user_id}")
    except Exception as e:
        logger.error(f"❌ Authentication failed: {e}")
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Invalid or expired session. Please login again.",
                "type": "authentication_failed"
            },
        )

    # Apply rate limiting
    await rate_limit_middleware(request)

    # Process ChatKit request
    try:
        body = await request.body()

        # Log request body for debugging
        try:
            import json
            body_json = json.loads(body)
            request_type = body_json.get("type", "unknown")
            logger.info(f"[ChatKit Request] type={request_type}, user={user_id}")

            # Log thread ID for thread operations
            if request_type in ["threads.get", "threads.run", "threads.delete"]:
                thread_id = body_json.get("params", {}).get("threadId") or body_json.get("threadId")
                logger.info(f"   Thread ID: {thread_id}")
        except:
            pass

        # Add user_id to request context for ChatKit server
        context = {"user_id": user_id}

        # Process request through ChatKit server
        result = await robotics_chatbot_server.process(body, context)

        # Check if streaming response
        

        if isinstance(result, StreamingResult):
            # Return SSE stream for real-time AI responses
            return StreamingResponse(
                result,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )
        else:
            # Return JSON response
            return Response(
                content=result.json,
                media_type="application/json",
            )

    except Exception as e:
        logger.error(f"ChatKit endpoint error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(e),
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.log_level == "info",
    )
