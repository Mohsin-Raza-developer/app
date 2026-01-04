"""
PostgreSQL implementation of ChatKit Store interface.

Implements thread and message persistence using SQLAlchemy async models.
"""

from chatkit.store import Store
from chatkit.types import (
    ThreadMetadata, 
    ThreadItem, 
    Page, 
    UserMessageItem, 
    AssistantMessageItem,
    UserMessageTextContent,
    AssistantMessageContent
)
from typing import Optional, List, Any
from uuid import uuid4, UUID
from datetime import datetime, timezone
import logging
import json

from database import AsyncSessionLocal
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models.thread import Thread
from models.message import Message

logger = logging.getLogger(__name__)


class PostgresStore(Store):
    """
    ChatKit Store implementation using PostgreSQL.

    Stores threads and messages in PostgreSQL tables via SQLAlchemy ORM.
    """

    def generate_thread_id(self, context: dict) -> str:
        """
        Generate a unique thread ID.

        Args:
            context: Request context (contains user_id and other request data)

        Returns:
            str: UUID4 string
        """
        return str(uuid4())

    def generate_item_id(self, item_type: str, thread: ThreadMetadata, context: dict) -> str:
        """
        Generate a unique item ID for a thread item.

        Args:
            item_type: Type of item being created (e.g., "message", "sdk_hidden_context")
            thread: Thread metadata
            context: Request context (contains user_id and other request data)

        Returns:
            str: UUID4 string
        """
        # item_type could be used for prefixing or partitioning if needed
        # For now, just return a UUID
        return str(uuid4())

    async def load_thread(self, thread_id: str, user_id: Optional[str] = None, context: Optional[Any] = None) -> Optional[ThreadMetadata]:
        """
        Load thread metadata by ID with authorization check.

        Args:
            thread_id: Thread identifier
            user_id: Optional user_id for authorization (if provided, verifies ownership)
            context: Optional request context (for ChatKit SDK compatibility)

        Returns:
            ThreadMetadata or None if not found or unauthorized
        """
        try:
            logger.info(f"[LOAD_THREAD] Loading thread metadata: {thread_id}, user_id={user_id}")

            async with AsyncSessionLocal() as session:
                query = select(Thread).where(Thread.thread_id == thread_id)

                # Authorization check: verify thread belongs to user
                if user_id:
                    query = query.where(Thread.user_id == user_id)

                result = await session.execute(query)
                thread = result.scalar_one_or_none()

                if not thread:
                    if user_id:
                        logger.warning(f"[LOAD_THREAD] Thread {thread_id} not found or unauthorized for user {user_id}")
                    else:
                        logger.warning(f"[LOAD_THREAD] Thread {thread_id} not found")
                    return None

                logger.info(f"[LOAD_THREAD] Successfully loaded thread {thread_id}, title={thread.title}")

                return ThreadMetadata(
                    id=str(thread.thread_id),
                    created_at=thread.created_at,
                    metadata=thread.thread_metadata or {},
                )

        except Exception as e:
            logger.error(f"[LOAD_THREAD] Error loading thread {thread_id}: {e}")
            return None

    async def save_thread(self, thread: ThreadMetadata, context: Optional[Any] = None) -> None:
        """
        Save or update thread metadata.

        Args:
            thread: ThreadMetadata to save
            context: Optional request context (for ChatKit SDK compatibility)
        """
        try:
            async with AsyncSessionLocal() as session:
                # Check if thread exists
                result = await session.execute(
                    select(Thread).where(Thread.thread_id == thread.id)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing thread
                    existing.thread_metadata = thread.metadata
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new thread
                    # Extract user_id from metadata or context
                    user_id = thread.metadata.get("user_id")
                    if not user_id and context:
                        # Try to get user_id from context (set by main.py endpoint)
                        user_id = context.get("user_id")

                    if not user_id:
                        raise ValueError("user_id required in thread metadata or context")

                    # Add user_id to metadata for consistency
                    thread.metadata["user_id"] = user_id

                    new_thread = Thread(
                        thread_id=thread.id,  # Pass string/UUID directly
                        user_id=user_id,      # Pass string/UUID directly
                        title=thread.metadata.get("title"),
                        thread_metadata=thread.metadata,
                        created_at=thread.created_at.replace(tzinfo=None) if thread.created_at.tzinfo else thread.created_at,
                        updated_at=datetime.utcnow(),
                    )
                    session.add(new_thread)
                
                await session.commit()
                logger.debug(f"Saved thread {thread.id} for user {user_id}")

        except Exception as e:
            logger.error(f"Error saving thread {thread.id}: {e}")
            raise

    async def delete_thread(self, thread_id: str, user_id: Optional[str] = None, context: Optional[Any] = None) -> None:
        """
        Delete a thread and all its messages with authorization check.

        Args:
            thread_id: Thread identifier
            user_id: Optional user_id for authorization (if provided, verifies ownership before deletion)
            context: Optional request context (for ChatKit SDK compatibility)

        Raises:
            PermissionError: If user_id is provided and thread doesn't belong to user
        """
        try:
            async with AsyncSessionLocal() as session:
                # Authorization check: verify thread belongs to user before deletion
                if user_id:
                    result = await session.execute(
                        select(Thread).where(
                            Thread.thread_id == thread_id,
                            Thread.user_id == user_id,
                        )
                    )
                    thread = result.scalar_one_or_none()
                    if not thread:
                        logger.warning(f"Thread {thread_id} not found or unauthorized for user {user_id}")
                        raise PermissionError(f"Thread {thread_id} not found or access denied")

                await session.execute(
                    delete(Thread).where(Thread.thread_id == thread_id)
                )
                await session.commit()
                logger.info(f"Deleted thread {thread_id}")

        except PermissionError:
            raise
        except Exception as e:
            logger.error(f"Error deleting thread {thread_id}: {e}")
            raise

    async def load_threads(
        self, user_id: Optional[str] = None, limit: int = 20, after: Optional[str] = None, order: str = "desc", context: Optional[Any] = None
    ) -> Page[ThreadMetadata]:
        """
        Load threads for a user with pagination.

        Args:
            user_id: User identifier (optional, extracted from context if not provided)
            limit: Maximum threads to return
            after: Cursor for pagination (thread_id to start after)
            order: Sort order - "asc" or "desc" (default: "desc")
            context: Optional request context (for ChatKit SDK compatibility)

        Returns:
            Page of ThreadMetadata with pagination info
        """
        try:
            # Extract user_id from context if not provided
            if user_id is None and context is not None:
                user_id = context.get("user_id") if isinstance(context, dict) else getattr(context, "user_id", None)

            if not user_id:
                logger.error("load_threads called without user_id")
                return Page(items=[], next_cursor=None)

            async with AsyncSessionLocal() as session:
                # Determine sort order
                order_by = Thread.updated_at.desc() if order == "desc" else Thread.updated_at.asc()

                query = (
                    select(Thread)
                    .where(Thread.user_id == user_id)
                    .order_by(order_by)
                    .limit(limit + 1)  # +1 to check if there's more
                )

                if after:
                    # Get the updated_at timestamp of the after thread
                    after_result = await session.execute(
                        select(Thread.updated_at).where(
                            Thread.thread_id == after
                        )
                    )
                    after_timestamp = after_result.scalar_one_or_none()
                    if after_timestamp:
                        # Apply appropriate filter based on sort order
                        if order == "desc":
                            query = query.where(Thread.updated_at < after_timestamp)
                        else:
                            query = query.where(Thread.updated_at > after_timestamp)

                result = await session.execute(query)
                threads = result.scalars().all()

                # Check if there are more threads
                has_more = len(threads) > limit
                if has_more:
                    threads = threads[:limit]

                items = [
                    ThreadMetadata(
                        id=str(t.thread_id),
                        created_at=t.created_at,
                        metadata=t.thread_metadata or {},
                    )
                    for t in threads
                ]

                # Next cursor is the last thread's ID
                next_cursor = str(threads[-1].thread_id) if has_more and threads else None

                return Page(items=items, next_cursor=next_cursor)

        except Exception as e:
            logger.error(f"Error loading threads for user {user_id}: {e}")
            return Page(items=[], next_cursor=None)

    async def add_thread_item(self, thread_id: str, item: ThreadItem, context: Optional[Any] = None) -> None:
        """
        Add a message item to a thread.

        Args:
            thread_id: Thread identifier
            item: ThreadItem to add (message)
            context: Optional request context (for ChatKit SDK compatibility)
        """
        try:
            async with AsyncSessionLocal() as session:
                # Get current message count for sequence number
                result = await session.execute(
                    select(Message.sequence_number)
                    .where(Message.thread_id == thread_id)
                    .order_by(Message.sequence_number.desc())
                    .limit(1)
                )
                last_seq = result.scalar_one_or_none()
                next_seq = (last_seq + 1) if last_seq else 1

                # Extract role safely based on instance type first
                if isinstance(item, AssistantMessageItem):
                    role = "assistant"
                elif isinstance(item, UserMessageItem):
                    role = "user"
                else:
                    role = getattr(item, "role", "user")
                
                # Extract text content properly
                extracted_content = ""
                raw_content = getattr(item, "content", "")
                
                if isinstance(raw_content, str):
                    extracted_content = raw_content
                elif isinstance(raw_content, list):
                    for block in raw_content:
                        if hasattr(block, "text"):
                            extracted_content += block.text
                        elif isinstance(block, dict) and "text" in block:
                             extracted_content += block["text"]
                
                if not extracted_content:
                    # Fallback for widgets or other items without text
                    extracted_content = str(raw_content) if raw_content else "Attribute content missing"

                # Create message
                # Handle fake IDs from Agents SDK stream
                final_item_id = item.id
                if final_item_id == "__fake_id__":
                    final_item_id = str(uuid4())
                
                message = Message(
                    message_id=final_item_id, # Assume string or UUID compatible
                    thread_id=thread_id,      # Assume string or UUID compatible
                    role=role,
                    content=extracted_content,
                    sequence_number=next_seq,
                )
                session.add(message)

                # Auto-generate thread title from first user message if title is NULL
                if next_seq == 1 and role == "user":
                    thread_result = await session.execute(
                        select(Thread).where(Thread.thread_id == thread_id)
                    )
                    thread = thread_result.scalar_one_or_none()
                    if thread and not thread.title:
                        # Truncate content to 50 characters for title
                        title = extracted_content[:50].strip()
                        if len(extracted_content) > 50:
                            title += "..."
                        thread.title = title
                        logger.debug(f"Auto-generated thread title: {title}")

                await session.commit()

                logger.info(f"[SAVED MESSAGE] Thread {thread_id}, Role: {role}, Seq: {next_seq}, ID: {message.message_id}")
                logger.debug(f"   Content preview: {extracted_content[:100]}...")


        except Exception as e:
            logger.error(f"Error adding item to thread {thread_id}: {e}")
            raise

    async def load_thread_items(
        self, thread_id: str, limit: int = 100, after: Optional[str] = None, order: str = "asc", context: Optional[Any] = None
    ) -> Page[ThreadItem]:
        """
        Load messages from a thread.

        Args:
            thread_id: Thread identifier
            limit: Maximum messages to return
            after: Message ID to start after (for pagination)
            order: Sort order (asc/desc)
            context: Optional request context (for ChatKit SDK compatibility)

        Returns:
            Page of ThreadItem objects
        """
        try:
            logger.info(f"[LOAD_THREAD_ITEMS] Loading items for thread {thread_id}, limit={limit}, after={after}, order={order}")

            # Ensure limit is an integer
            limit = limit if limit is not None else 100

            async with AsyncSessionLocal() as session:
                # Determine sort order
                # ChatKit usually requests history in 'asc' order (oldest first)
                order_by = Message.sequence_number.asc() if order == "asc" else Message.sequence_number.desc()

                query = (
                    select(Message)
                    .where(Message.thread_id == thread_id)
                    .order_by(order_by)
                    .limit(limit + 1)
                )

                if after:
                    # FIXED: Handle both sequence number (int) and message_id (UUID string)
                    after_seq = None

                    # Check if after is numeric (sequence number) or string (message_id)
                    if isinstance(after, int):
                        # Direct sequence number passed
                        after_seq = after
                    else:
                        # Try to convert to int (sequence number as string)
                        try:
                            after_seq = int(after)
                        except (ValueError, TypeError):
                            # It's a message_id (UUID string), look up sequence number
                            after_result = await session.execute(
                                select(Message.sequence_number).where(
                                    Message.message_id == after
                                )
                            )
                            after_seq = after_result.scalar_one_or_none()

                    # Apply pagination filter
                    if after_seq:
                        if order == "asc":
                            query = query.where(Message.sequence_number > after_seq)
                        else:
                            query = query.where(Message.sequence_number < after_seq)

                result = await session.execute(query)
                messages = result.scalars().all()

                has_more = len(messages) > limit
                if has_more:
                    messages = messages[:limit]

                logger.info(f"[LOAD_THREAD_ITEMS] Found {len(messages)} messages for thread {thread_id}")

                items: List[ThreadItem] = []
                for idx, msg in enumerate(messages):
                    # Convert DB Message to ChatKit ThreadItem
                    if msg.role == "user":
                        items.append(UserMessageItem(
                            id=str(msg.message_id),
                            thread_id=str(msg.thread_id),
                            created_at=msg.created_at,
                            content=[UserMessageTextContent(text=msg.content)],
                            inference_options={}
                        ))
                    elif msg.role == "assistant":
                        items.append(AssistantMessageItem(
                            id=str(msg.message_id),
                            thread_id=str(msg.thread_id),
                            created_at=msg.created_at,
                            content=[AssistantMessageContent(text=msg.content)]
                        ))
                    # Note: ClientToolCallItem etc. would need special handling if stored in DB

                    # Log each message
                    content_preview = msg.content[:100] if msg.content else ""
                    logger.info(f"  [{idx}] seq={msg.sequence_number}, role={msg.role}, id={msg.message_id}, content={content_preview}...")

                next_after = str(messages[-1].message_id) if has_more and messages else None

                logger.info(f"[LOAD_THREAD_ITEMS] Returning {len(items)} items, has_more={has_more}, next_after={next_after}")

                return Page(data=items, has_more=has_more, after=next_after)

        except Exception as e:
            logger.error(f"[LOAD_THREAD_ITEMS] Error loading items from thread {thread_id}: {e}", exc_info=True)
            return Page(data=[], has_more=False)

    async def save_item(self, thread_id: str, item: ThreadItem, context: Optional[Any] = None) -> None:
        """
        Save or update a thread item (UPSERT operation).

        ChatKit calls this method when items are completed during streaming.
        This method should:
        1. Check if item exists (by item_id)
        2. If exists → UPDATE it
        3. If not exists → INSERT it

        Args:
            thread_id: Thread identifier
            item: ThreadItem to save
            context: Optional request context (for ChatKit SDK compatibility)
        """
        try:
            async with AsyncSessionLocal() as session:
                # Extract role safely based on instance type first
                if isinstance(item, AssistantMessageItem):
                    role = "assistant"
                elif isinstance(item, UserMessageItem):
                    role = "user"
                else:
                    role = getattr(item, "role", "user")

                # Extract text content properly
                extracted_content = ""
                raw_content = getattr(item, "content", "")

                if isinstance(raw_content, str):
                    extracted_content = raw_content
                elif isinstance(raw_content, list):
                    for block in raw_content:
                        if hasattr(block, "text"):
                            extracted_content += block.text
                        elif isinstance(block, dict) and "text" in block:
                            extracted_content += block["text"]

                if not extracted_content:
                    extracted_content = str(raw_content) if raw_content else "No content"

                # Handle fake IDs from Agents SDK stream
                final_item_id = item.id
                if final_item_id == "__fake_id__":
                    final_item_id = str(uuid4())

                # Check if message already exists (UPDATE case)
                existing_result = await session.execute(
                    select(Message).where(
                        Message.thread_id == thread_id,
                        Message.message_id == final_item_id
                    )
                )
                existing_message = existing_result.scalar_one_or_none()

                if existing_message:
                    # UPDATE existing message
                    existing_message.content = extracted_content
                    existing_message.role = role
                    logger.info(f"📝 UPDATED MESSAGE: Thread {thread_id}, Role: {role}, ID: {final_item_id}")
                    logger.debug(f"   Updated content: {extracted_content[:100]}...")
                else:
                    # INSERT new message
                    # Get current message count for sequence number
                    result = await session.execute(
                        select(Message.sequence_number)
                        .where(Message.thread_id == thread_id)
                        .order_by(Message.sequence_number.desc())
                        .limit(1)
                    )
                    last_seq = result.scalar_one_or_none()
                    next_seq = (last_seq + 1) if last_seq else 1

                    message = Message(
                        message_id=final_item_id,
                        thread_id=thread_id,
                        role=role,
                        content=extracted_content,
                        sequence_number=next_seq,
                    )
                    session.add(message)

                    logger.info(f"[INSERTED MESSAGE] Thread {thread_id}, Role: {role}, Seq: {next_seq}, ID: {final_item_id}")
                    logger.debug(f"   Content: {extracted_content[:100]}...")

                await session.commit()

        except Exception as e:
            logger.error(f"Error in save_item for thread {thread_id}: {e}")
            raise

    async def load_item(self, thread_id: str, item_id: str, context: Optional[Any] = None) -> Optional[ThreadItem]:
        """
        Load a specific thread item by ID.

        Args:
            thread_id: Thread identifier
            item_id: Item (message) identifier
            context: Optional request context (for ChatKit SDK compatibility)

        Returns:
            ThreadItem or None if not found
        """
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Message).where(
                        Message.thread_id == thread_id,
                        Message.message_id == item_id,
                    )
                )
                message = result.scalar_one_or_none()

                if not message:
                    return None

                # Convert to ThreadItem
                if message.role == "user":
                    return UserMessageItem(
                        id=str(message.message_id),
                        thread_id=str(message.thread_id),
                        created_at=message.created_at,
                        content=[UserMessageTextContent(text=message.content)],
                        inference_options={}
                    )
                elif message.role == "assistant":
                     return AssistantMessageItem(
                        id=str(message.message_id),
                        thread_id=str(message.thread_id),
                        created_at=message.created_at,
                        content=[AssistantMessageContent(text=message.content)]
                    )
                return None

        except Exception as e:
            logger.error(f"Error loading item {item_id} from thread {thread_id}: {e}")
            return None

    async def delete_thread_item(self, thread_id: str, item_id: str, context: Optional[Any] = None) -> None:
        """
        Delete a specific message from a thread.

        Args:
            thread_id: Thread identifier
            item_id: Item (message) identifier to delete
            context: Optional request context (for ChatKit SDK compatibility)
        """
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(Message).where(
                        Message.thread_id == thread_id,
                        Message.message_id == item_id,
                    )
                )
                await session.commit()
                logger.debug(f"Deleted message {item_id} from thread {thread_id}")

        except Exception as e:
            logger.error(f"Error deleting item {item_id} from thread {thread_id}: {e}")
            raise

    async def save_attachment(self, thread_id: str, attachment: dict) -> None:
        """
        Save attachment metadata (placeholder - not implemented).

        This chatbot doesn't support file attachments yet.
        Attachments would be stored in Cloudflare R2 with metadata in database.

        Args:
            thread_id: Thread identifier
            attachment: Attachment metadata
        """
        logger.warning(f"save_attachment called but not implemented for thread {thread_id}")
        pass

    async def load_attachment(self, thread_id: str, attachment_id: str) -> Optional[dict]:
        """
        Load attachment metadata (placeholder - not implemented).

        This chatbot doesn't support file attachments yet.

        Args:
            thread_id: Thread identifier
            attachment_id: Attachment identifier

        Returns:
            None (not implemented)
        """
        logger.warning(f"load_attachment called but not implemented for thread {thread_id}")
        return None

    async def delete_attachment(self, thread_id: str, attachment_id: str) -> None:
        """
        Delete attachment (placeholder - not implemented).

        This chatbot doesn't support file attachments yet.

        Args:
            thread_id: Thread identifier
            attachment_id: Attachment identifier
        """
        logger.warning(f"delete_attachment called but not implemented for thread {thread_id}")
        pass


# Singleton instance for dependency injection
postgres_store = PostgresStore()
