"""
CORS middleware configuration.

Configures Cross-Origin Resource Sharing for frontend integration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
import logging

logger = logging.getLogger(__name__)


def setup_cors(app: FastAPI):
    """
    Setup CORS middleware for the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    origins = settings.cors_origins_list

    logger.info(f"Configuring CORS with origins: {origins}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],  # Allow all HTTP methods
        allow_headers=["*"],  # Allow all headers
        expose_headers=["*"],  # Expose all headers to frontend
    )
