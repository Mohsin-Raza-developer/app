"""
Thread model - Represents a conversation thread.
"""

from datetime import datetime
from uuid import UUID
from sqlalchemy import Column, String, DateTime, ForeignKey, CheckConstraint, JSON
from sqlalchemy.types import Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Thread(Base):
    """
    Conversation thread model.

    Attributes:
        thread_id: Unique thread identifier (UUID)
        user_id: Owner of the thread (references Better Auth user table)
        title: Optional thread title (auto-generated from first message if NULL)
        thread_metadata: JSON column for ChatKit metadata (tags, custom fields)
        created_at: Thread creation timestamp
        updated_at: Last message timestamp (auto-updated by trigger)
    """

    __tablename__ = "threads"

    thread_id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=func.uuid(), # conceptual default, standard uuid4() usage preferred in app logic
        nullable=False,
    )
    user_id = Column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=True)
    thread_metadata = Column("metadata", JSON, nullable=False, server_default="{}")
    created_at = Column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    messages = relationship(
        "Message", back_populates="thread", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("created_at <= updated_at", name="chk_threads_timestamps"),
        CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="chk_threads_metadata_object"
        ),
    )

    def __repr__(self) -> str:
        return f"<Thread(thread_id={self.thread_id}, user_id={self.user_id}, title='{self.title}')>"
