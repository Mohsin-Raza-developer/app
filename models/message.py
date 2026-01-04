"""
Message model - Represents a single message in a conversation thread.
"""

from datetime import datetime
from uuid import UUID
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.types import Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Message(Base):
    """
    Message model.

    Attributes:
        message_id: Unique message identifier (UUID)
        thread_id: Parent thread (references threads table)
        role: Message sender role ('user' or 'assistant')
        content: Message text content (1-100,000 characters)
        sequence_number: Message order within thread (1-indexed, unique per thread)
        created_at: Message creation timestamp
    """

    __tablename__ = "messages"

    message_id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=func.uuid(),
        nullable=False,
    )
    thread_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("threads.thread_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    created_at = Column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    thread = relationship("Thread", back_populates="messages")

    # Constraints
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="chk_messages_role"),
        CheckConstraint(
            "LENGTH(content) > 0 AND LENGTH(content) <= 100000",
            name="chk_messages_content_length",
        ),
        CheckConstraint("sequence_number >= 1", name="chk_messages_sequence_positive"),
        UniqueConstraint("thread_id", "sequence_number", name="uq_messages_thread_sequence"),
    )

    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(message_id={self.message_id}, thread_id={self.thread_id}, role='{self.role}', seq={self.sequence_number})>"
