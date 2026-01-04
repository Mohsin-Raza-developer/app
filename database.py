"""
Database connection and session management.

Sets up async SQLAlchemy engine with connection pooling for PostgreSQL.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from config import settings

# Shared Base class for all models
Base = declarative_base()

# Create async engine with connection pooling
# Optimized for Neon serverless database
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "debug",  # Log SQL queries in debug mode
    pool_size=5,  # Smaller pool for serverless (Neon auto-scales)
    max_overflow=10,  # +10 overflow connections
    pool_timeout=30,  # 30s wait for connection
    pool_recycle=300,  # Recycle connections after 5 mins (Neon idle timeout)
    pool_pre_ping=True,  # Verify connection health before use
    connect_args={
        "timeout": 10,  # Connection timeout 10s
        "command_timeout": 10,  # Query timeout 10s
    },
)

# Create async session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """
    Dependency for FastAPI routes to get database session.

    Yields:
        AsyncSession: Database session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Initialize database connection.

    Called at application startup to verify database connectivity.
    """
    async with engine.connect() as conn:
        # Test connection (no transaction needed for health check)
        await conn.execute(text("SELECT 1"))
        # Connection is automatically closed when context exits


async def close_db():
    """
    Close database connection.

    Called at application shutdown to cleanup resources.
    """
    await engine.dispose()
