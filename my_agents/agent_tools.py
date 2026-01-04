"""
AI agent tools for textbook search.

Provides @function_tool decorated functions for OpenAI Agents SDK.
"""

from contextlib import AsyncExitStack
from qdrant_client import QdrantClient
import cohere
import os


class ToolContext:
    def __init__(self):
        self.stack = AsyncExitStack()
        self.qdrant = None
        self.cohere = None

    async def __aenter__(self):
        print("ENTER TOOL CONTEXT")

        self.qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.environ["QDRANT_API_KEY"],
        )

        self.cohere = cohere.Client(
            api_key=os.environ["COHERE_API_KEY"]
        )

        return self

    async def __aexit__(self, *args):
        print("EXIT TOOL CONTEXT")
        await self.stack.aclose()


from agents import function_tool
import asyncio


@function_tool
def search_knowledge_base(query: str) -> str:
    async def _run():
        async with ToolContext() as ctx:
            print(f"🔎 Query: {query}")

            # Embed query
            embedding = ctx.cohere.embed(
                texts=[query],
                model="embed-v4.0",
                input_type="search_query"
            ).embeddings[0]

            # Vector search
            results = ctx.qdrant.query_points(
                collection_name="robotics_textbook_v1",
                query=embedding,
                limit=5,
                score_threshold=0.4
            ).points

            if not results:
                return "No relevant content found."

            return "\n".join(
                f"- {r.payload.get('text','')}"
                for r in results
            )

    return asyncio.run(_run())


# from agents import function_tool
# from services.qdrant_service import qdrant_service
# import logging
# from uuid import uuid4
# import cohere

# logger = logging.getLogger(__name__)


# @function_tool
# async def search_textbook(query: str) -> str:
#     """
#     Search the Physical AI and Humanoid Robotics textbook using Cohere + Qdrant.
    
#     Logic: Query -> Cohere Embeddings (v4.0) -> Qdrant Search -> Results
#     """
#     try:
#         logger.info(f"search_textbook logic start for query: {query[:100]}...")

#         # 1. COHERE: Generate Embeddings using embed-v4.0
#         logger.info("Step 1: Sending query to Cohere for embedding using embed-v4.0...")
        
#         response = qdrant_service.cohere_client.embed(
#             texts=[query],
#             model="embed-v4.0",
#             input_type="search_query",
#             embedding_types=["float"]
#         )
        
#         # Access the float embeddings as per the new v4.0 response structure
#         query_vector = response.embeddings.float[0]
        
#         dim = len(query_vector)
#         logger.info(f"Step 1 Complete: Cohere returned {dim} dimensions.")

#         # 2. QDRANT: Search using Embeddings
#         logger.info(f"Step 2: Sending {dim} dimensions to Qdrant (Collection: {qdrant_service.collection_name})...")
        
#         search_result = qdrant_service.qdrant_client.query_points(
#             collection_name=qdrant_service.collection_name,
#             query=query_vector,
#             limit=5,
#             with_payload=True,
#         ).points

#         # 3. OUTPUT: Format Qdrant results
#         if not search_result:
#             logger.info("Step 3: No matches found in Qdrant.")
#             return "The Physical AI and Humanoid Robotics textbook does not cover this topic directly."

#         formatted_results = []
#         for i, hit in enumerate(search_result, 1):
#             # Qdrant structure handling
#             payload = hit.payload if hasattr(hit, 'payload') else hit.get('payload', {})
            
#             chapter = payload.get('chapter', 'Unknown')
#             section = payload.get('section', 'Unknown')
#             page = payload.get('page', 'N/A')
#             content = payload.get("text", "").strip()
            
#             # More explicit format for the AI brain
#             formatted_results.append(
#                 f"SOURCE {i}:\n"
#                 f"LOCATION: {chapter} > {section} (Page {page})\n"
#                 f"CONTENT: {content}\n"
#                 f"---"
#             )

#         final_output = "\n\n".join(formatted_results)
#         logger.info(f"Step 3 Complete: Returning {len(search_result)} sources to Agent.")
#         return final_output

#     except Exception as e:
#         logger.error(f"search_textbook Tool Error: {str(e)}")
#         # Check if it's a dimension mismatch error to guide the user
#         if "Vector dimension error" in str(e):
#             # Safe access to query_vector if it exists
#             v_len = len(query_vector) if 'query_vector' in locals() else "unknown"
#             return f"Error: Qdrant expected 1536 dimensions but Cohere gave {v_len}. Please ensure the embedding model matches the collection."
#         return f"I encountered an issue while searching the textbook: {str(e)}. Please try again."
