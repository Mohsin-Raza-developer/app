"""
Robotics AI Agent with textbook search capabilities.

Uses OpenAI Agents SDK with Google Gemini 2.0 Flash model.
"""

from agents import Agent, set_default_openai_client
from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from my_agents.agent_tools import search_knowledge_base
from config import settings
import logging

logger = logging.getLogger(__name__)


class RoboticsAgent:
    """
    AI agent specialized in answering questions about Physical AI and Humanoid Robotics.

    The agent uses:
    - Google Gemini 2.0 Flash model via OpenAI-compatible endpoint
    - search_textbook tool for retrieving relevant textbook content
    - OpenAIChatCompletionsModel to force compatibility with Gemini
    """

    def __init__(self):
        """Initialize the robotics agent with tools and configuration."""

        # Create external client for Gemini
        external_client = AsyncOpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )

        # Force Chat Completions API (Crucial for Gemini support)
        MODEL = OpenAIChatCompletionsModel(
            model="gemini-2.5-flash",
            openai_client=external_client
        )

        # Configure global client for other SDK operations
        set_default_openai_client(external_client, use_for_tracing=False)
        
        logger.info(f"Configured Robotics Agent with Gemini model forced to Chat Completions.")

        # Agent instructions
        instructions = """You are an expert AI assistant specializing in Physical AI and Humanoid Robotics.
Your primary goal is to help users understand complex robotics concepts, perform research using the textbook, and write code.

**Response Structure (Mandatory):**

1.  **Direct Answer**: Start with a concise, direct answer to the user's question.
2.  **Key Concepts**: Use bullet points to break down the explanation into core principles.
3.  **Detailed Explanation**: Provide meaningful technical depth. Use Markdown headers (###) to separate sections.
4.  **Code Examples**: If relevant, provide Python or C++ code in fenced code blocks.
5.  **Citations**: If you use the `search_textbook` tool, integrate citations seamlessly.

**Tone**: Professional, academic, yet accessible.
"""

        # Initialize Agent with the forced model object (Required for Gemini compatibility)
        self.agent = Agent(
            name="Robotics Expert",
            instructions=instructions,
            tools=[search_knowledge_base],
            model=MODEL,
        )

        logger.info(
            f"RoboticsAgent initialized with model: {settings.gemini_model}"
        )

    def get_agent(self) -> Agent:
        """
        Get the underlying OpenAI Agent instance.

        Returns:
            Agent: OpenAI Agents SDK Agent instance
        """
        return self.agent


# Singleton instance for dependency injection
robotics_agent = RoboticsAgent()
