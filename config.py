"""
Application configuration using Pydantic Settings.

Loads all environment variables required for the chatbot backend.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database Configuration
    database_url: str = Field(..., env="DATABASE_URL")
    better_auth_database_url: str = Field(..., env="BETTER_AUTH_DATABASE_URL")

    # Better Auth API Configuration
    better_auth_url: str = Field(..., env="BETTER_AUTH_URL")
    better_auth_secret: str = Field(..., env="BETTER_AUTH_SECRET")

    # Qdrant Vector Database
    qdrant_url: str = Field(..., env="QDRANT_URL")
    qdrant_api_key: str = Field(..., env="QDRANT_API_KEY")
    qdrant_collection_name: str = Field(
        default="robotics_textbook_v1", env="QDRANT_COLLECTION_NAME"
    )

    # Google Gemini AI
    gemini_api_key: str = Field(..., env="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", env="GEMINI_MODEL")

    # OpenAI-Compatible Endpoint (for Gemini)
    openai_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        env="OPENAI_BASE_URL",
    )
    # Use Gemini API key for OpenAI-compatible endpoint
    @property
    def openai_api_key(self) -> str:
        """Returns Gemini API key for OpenAI-compatible endpoint."""
        return self.gemini_api_key

    # Cohere Embeddings
    cohere_api_key: str = Field(..., env="COHERE_API_KEY")

    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    reload: bool = Field(default=False, env="RELOAD")
    log_level: str = Field(default="info", env="LOG_LEVEL")

    # Security
    cors_origins: str = Field(
        env="CORS_ORIGINS"
    )  # Comma-separated
    rate_limit_per_minute: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra env vars (like NEXT_PUBLIC_API_BASE_URL)

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings = Settings()
