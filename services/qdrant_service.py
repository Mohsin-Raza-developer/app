# """
# Qdrant vector search service.

# Handles semantic search over robotics textbook embeddings using Cohere.
# """

# from qdrant_client import QdrantClient
# from qdrant_client.models import Filter, FieldCondition, MatchValue, SearchRequest
# import cohere
# from typing import List, Dict, Any
# import logging

# from config import settings

# logger = logging.getLogger(__name__)


# import cohere
# from qdrant_client import QdrantClient
# from typing import List, Dict, Any
# import logging

# from config import settings

# logger = logging.getLogger(__name__)


# class QdrantService:
#     """
#     Service for searching robotics textbook content in Qdrant vector database.
#     Logic: User Query -> Cohere Embeddings -> Qdrant Search.
#     """

#     def __init__(self):
#         """Initialize clients."""
#         try:
#             self.qdrant_client = QdrantClient(
#                 url=settings.qdrant_url,
#                 api_key=settings.qdrant_api_key,
#             )
#             # Initialize Cohere Client
#             self.cohere_client = cohere.Client(api_key=settings.cohere_api_key)
#             self.collection_name = settings.qdrant_collection_name

#             logger.info(
#                 f"QdrantService initialized with collection: {self.collection_name}"
#             )
#         except Exception as e:
#             logger.error(f"Error during QdrantService init: {e}")

#     async def search(
#         self,
#         query: str,
#         limit: int = 5,
#         score_threshold: float = 0.7,
#     ) -> List[Dict[str, Any]]:
#         """
#         Step 1: Send query to Cohere to get embeddings.
#         Step 2: Use embeddings to search Qdrant.
#         """
#         try:
#             # Step 1: Cohere Embeddings
#             logger.debug(f"Sending query to Cohere for embedding: {query[:100]}...")
            
#             # Using the stable embed-english-v3.0 model
#             # Note: If your Qdrant requires 1536, we might need to check model compatibility.
#             response = self.cohere_client.embed(
#                 texts=[query],
#                 model="embed-english-v3.0",
#                 input_type="search_query",
#             )
#             query_vector = response.embeddings[0]
            
#             dim = len(query_vector)
#             logger.info(f"Cohere returned embedding with dimension: {dim}")

#             # Step 2: Qdrant Search
#             search_result = self.qdrant_client.search(
#                 collection_name=self.collection_name,
#                 query_vector=query_vector,
#                 limit=limit,
#                 score_threshold=score_threshold,
#                 with_payload=True,
#             )

#             # Step 3: Return Results
#             results = []
#             for hit in search_result:
#                 result = {
#                     "content": hit.payload.get("text", ""),
#                     "chapter": hit.payload.get("chapter", "Unknown"),
#                     "section": hit.payload.get("section", "Unknown"),
#                     "page": hit.payload.get("page", 0),
#                     "score": hit.score,
#                 }
#                 results.append(result)

#             return results

#         except Exception as e:
#             logger.error(f"Qdrant search error: {e}")
#             # If dimension error occurs, we will know from this log
#             raise Exception(f"Vector search failed: {str(e)}")

#             # Format results with citation metadata
#             results = []
#             for hit in search_result:
#                 result = {
#                     "content": hit.payload.get("text", ""),
#                     "chapter": hit.payload.get("chapter", "Unknown"),
#                     "section": hit.payload.get("section", "Unknown"),
#                     "page": hit.payload.get("page", 0),
#                     "score": hit.score,
#                 }
#                 results.append(result)

#             logger.info(
#                 f"Found {len(results)} results for query (score >= {score_threshold})"
#             )
#             return results

#         except Exception as e:
#             logger.error(f"Qdrant search error: {e}")
#             raise Exception(f"Vector search failed: {str(e)}")


# # Singleton instance for dependency injection
# qdrant_service = QdrantService()
