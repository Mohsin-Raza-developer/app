"""
ChatKit server implementation for robotics chatbot.

Extends ChatKitServer with AI agent integration and streaming responses.
"""

from chatkit.server import ChatKitServer
from chatkit.types import ThreadMetadata, ThreadStreamEvent, UserMessageItem, ErrorEvent
from chatkit.agents import stream_agent_response, AgentContext
from agents import Runner, InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered
from typing import AsyncIterator, Optional, Dict
import logging

from chatkit_server.postgres_store import PostgresStore, postgres_store
from my_agents.robotics_agent import robotics_agent

logger = logging.getLogger(__name__)


class RoboticsChatbotServer(ChatKitServer):
    """
    ChatKit server for Physical AI and Humanoid Robotics chatbot.

    Integrates:
    - PostgreSQL persistence via PostgresStore
    - OpenAI Agents SDK with Gemini 2.0 Flash model
    - Textbook search tool for RAG-based responses
    - SSE streaming for real-time responses
    """
    def __init__(self, store: PostgresStore):
        """
        Initialize the ChatKit server.

        Args:
            store: PostgresStore instance for persistence
        """
        super().__init__(store=store)
        self.agent = robotics_agent.get_agent()
        logger.info("RoboticsChatbotServer initialized")

    async def respond(
        self,
        thread: ThreadMetadata,
        input: UserMessageItem | None,
        context: Dict,
    ) -> AsyncIterator[ThreadStreamEvent]:
        """
        Generate streaming response to user message.

        This method is called by ChatKit when a user sends a message.
        It runs the AI agent with the search_textbook tool and streams
        events back to the client.

        Args:
            thread: Thread metadata containing conversation context
            input: User's input message (or None for new thread)
            context: Request context (contains user_id from auth middleware)

        Yields:
            ThreadStreamEvent: SSE events for streaming response
        """
        try:
            # Log request
            user_id = context.get("user_id", "unknown")
            logger.info(f"Processing message for user {user_id}, thread {thread.id}")

            # Validate input message
            if not input:
                logger.warning("No input message provided in respond()")
                yield ErrorEvent(
                    message="No message received",
                    allow_retry=False,
                )
                return

            # Extract message content from UserMessageItem
            # UserMessageItem has content as a list of content blocks
            message_content = ""
            if hasattr(input, "content") and input.content:
                # Extract text from content blocks
                for content_block in input.content:
                    if hasattr(content_block, "text"):
                        message_content += content_block.text

            # T048: Input validation
            if not message_content or not message_content.strip():
                logger.warning("Empty message content received")
                yield ErrorEvent(
                    message="Message content cannot be empty",
                    allow_retry=False,
                )
                return

            if len(message_content) > 100000:
                logger.warning(f"Message too long: {len(message_content)} chars")
                yield ErrorEvent(
                    message="Message content exceeds maximum length of 100,000 characters",
                    allow_retry=False,
                )
                return

            # Load previous thread items to provide context history
            # We load the last 20 items to give the agent conversation history
            items_page = await self.store.load_thread_items(
                thread.id,
                after=None,
                limit=20,
                order="asc",
                context=context,
            )
            
            # Add the current user message to the list of items if it's not already saved
            # (ChatKit usually saves it before calling respond, but just in case)
            thread_items = items_page.data
            
            # DEBUG: Log loaded history
            logger.info(f"[LOADED HISTORY] Thread {thread.id} has {len(thread_items)} items")
            for idx, item in enumerate(thread_items):
                role = getattr(item, 'role', 'unknown')
                item_id = getattr(item, 'id', 'no-id')
                logger.info(f"  [{idx}] {role} - ID: {item_id}")
            
            # Convert ChatKit thread items to Agent input format
            # This handles text, attachments, and tool calls automatically
            from chatkit.agents import simple_to_agent_input
            agent_inputs = await simple_to_agent_input(thread_items)

            logger.debug(f"Running agent with {len(agent_inputs)} items of history")

            # Create agent context
            agent_context = AgentContext(
                thread=thread,
                store=self.store,
                request_context=context,
            )

            # Run agent with streaming and full history
            # The agent will use the search_textbook tool automatically
            result = Runner.run_streamed(
                self.agent,
                input=agent_inputs,
                context=agent_context
            )

            # Stream agent response events with guardrail handling
            try:
                async for event in stream_agent_response(agent_context, result):
                    yield event
            except InputGuardrailTripwireTriggered:
                logger.warning("Input guardrail triggered")
                yield ErrorEvent(
                    message="We blocked that message for safety.",
                    allow_retry=False,
                )
                return
            except OutputGuardrailTripwireTriggered:
                logger.warning("Output guardrail triggered")
                yield ErrorEvent(
                    message="The assistant response was blocked.",
                    allow_retry=False,
                )
                return

            logger.info(f"[SUCCESS] Completed response for thread {thread.id}")

        except Exception as e:
            logger.error(f"[CRITICAL ERROR] in respond(): {e}", exc_info=True)
            logger.error(f"[ERROR] Error type: {type(e).__name__}")
            logger.error(f"[ERROR] Error details: {str(e)}")
            import traceback
            logger.error(f"[ERROR] Full traceback:\n{traceback.format_exc()}")

            # Simple user-friendly error messages
            error_str = str(e).lower()

            # Quota exceeded errors
            if "quota" in error_str or "insufficient_quota" in error_str:
                yield ErrorEvent(
                    message="AI quota exceeded. Please try again later.",
                    allow_retry=False,
                )
            # Rate limit errors
            elif "rate limit" in error_str or "429" in error_str:
                yield ErrorEvent(
                    message="Too many requests. Please wait a moment.",
                    allow_retry=True,
                )
            # Network/timeout errors
            elif "timeout" in error_str or "connection" in error_str:
                yield ErrorEvent(
                    message="Network error. Please check your connection.",
                    allow_retry=True,
                )
            # Generic error (fallback)
            else:
                yield ErrorEvent(
                    message="Something went wrong. Please try again.",
                    allow_retry=True,
                )


# Singleton instance for dependency injection
robotics_chatbot_server = RoboticsChatbotServer(store=postgres_store)
