"""
Weaviate Vector Database Service for RAG (v5 Architecture)

Architecture Decision Record (ADR):
-----------------------------------
1. **Single Collection Strategy**: One collection "RAG_Documents" with metadata filtering.
   - Weaviate "Class" equivalent to Qdrant "Collection".
   - Tenant isolation via 'session_id' filter.

2. **Hybrid Search (Alpha)**:
   - Weaviate supports hybrid search out-of-the-box (Sparse BM25 + Dense Vector).
   - Alpha=0.7 (70% Vector, 30% BM25) proved optimal in v4.5 benchmarks.

3. **Adaptive Retrieval (Agentic)**:
   - If initial search yields low confidence, automatically reformulate query using synonyms.
   - Based on 'benchmark_weaviate_v5.py' findings (90% recall).

4. **Payload Schema**:
   - session_id: text (index filterable)
   - document_id: text
   - chunk_id: int
   - text: text (searchable)
   - page: int
   - created_at: number (for TTL)
"""

import os
import re
import time
import unicodedata
import uuid
from typing import Any, Dict, List, Optional

import structlog
import weaviate
from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter, MetadataQuery

logger = structlog.get_logger(__name__)


class WeaviateService:
    """
    Service for managing RAG vectors in Weaviate.
    Replaces QdrantService with v5 architecture features.
    """

    def __init__(self):
        """
        Initialize Weaviate client.

        Env vars:
        - WEAVIATE_URL: URL of Weaviate instance (e.g. http://weaviate:8080 or https://xxx.weaviate.cloud)
        - WEAVIATE_API_KEY: API key for authentication (optional, required for cloud)
        - WEAVIATE_GRPC_PORT: gRPC port (optional, defaults based on scheme)
        - RAG_COLLECTION_NAME: Default "RAG_Documents"
        """
        self.url = os.getenv("WEAVIATE_URL", "http://weaviate:8080")
        self.api_key = os.getenv("WEAVIATE_API_KEY")  # Optional, for cloud instances
        self.collection_name = os.getenv("RAG_COLLECTION_NAME", "RAG_Documents")

        # Parse host/port/scheme from URL for connect_to_custom
        try:
            from urllib.parse import urlparse

            parsed = urlparse(self.url)
            self.host = parsed.hostname or "weaviate"
            self.scheme = parsed.scheme or "http"

            # Determine if secure connection based on scheme
            self.http_secure = self.scheme == "https"
            self.grpc_secure = self.http_secure  # gRPC follows HTTP security

            # Port defaults: 443 for HTTPS, 8080 for HTTP
            default_port = 443 if self.http_secure else 8080
            self.port = parsed.port or default_port

            # gRPC port: use env var if provided, otherwise default to 50051
            # NOTE: Weaviate SDK requires http.port != grpc.port when using same host
            # Cloud instances typically use HTTPS:443 + gRPC:50051
            grpc_env = os.getenv("WEAVIATE_GRPC_PORT")
            if grpc_env:
                self.grpc_port = int(grpc_env)
            else:
                # Always use 50051 for gRPC (Weaviate default)
                # Even for cloud instances - they support gRPC on 50051
                self.grpc_port = 50051

        except Exception as e:
            logger.warning("Failed to parse WEAVIATE_URL, using defaults", error=str(e))
            self.host = "weaviate"
            self.port = 8080
            self.grpc_port = 50051
            self.http_secure = False
            self.grpc_secure = False
            self.scheme = "http"

        self.client = None
        self._connect()

    def _connect(self):
        """Establish connection to Weaviate"""
        try:
            # Build connection parameters
            import weaviate.classes.init as weaviate_init

            # Configure authentication if API key is provided
            auth_config = None
            if self.api_key:
                auth_config = weaviate_init.Auth.api_key(self.api_key)

            # Detect Weaviate Cloud instances and use appropriate connector
            is_cloud = ".weaviate.cloud" in self.host.lower()

            if is_cloud:
                # Use connect_to_weaviate_cloud for cloud instances
                # This helper handles gRPC multiplexing on port 443 correctly
                logger.info(
                    "Detected Weaviate Cloud instance, using cloud connector",
                    cluster_url=self.host,
                )
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=self.host,  # Hostname without scheme
                    auth_credentials=auth_config,
                    skip_init_checks=True,
                )
                logger.info(
                    "Weaviate Cloud connected",
                    cluster_url=self.host,
                    authenticated=bool(self.api_key),
                )
            else:
                # Use connect_to_custom for self-hosted/local instances
                self.client = weaviate.connect_to_custom(
                    http_host=self.host,
                    http_port=self.port,
                    http_secure=self.http_secure,
                    grpc_host=self.host,
                    grpc_port=self.grpc_port,
                    grpc_secure=self.grpc_secure,
                    auth_credentials=auth_config,
                    skip_init_checks=True,
                )
                logger.info(
                    "Weaviate connected (custom)",
                    host=self.host,
                    port=self.port,
                    grpc_port=self.grpc_port,
                    secure=self.http_secure,
                    authenticated=bool(self.api_key),
                )
        except Exception as e:
            logger.error("Failed to connect to Weaviate", error=str(e), exc_info=True)
            # Don't raise here, allow retry in ensure_collection or health_check

    def ensure_collection(self) -> None:
        """Ensure the RAG collection exists with correct schema."""
        if not self.client.is_connected():
            self._connect()

        try:
            if self.client.collections.exists(self.collection_name):
                logger.info(
                    "Weaviate collection exists", collection=self.collection_name
                )
                return

            # Create collection
            logger.info("Creating Weaviate collection", collection=self.collection_name)
            self.client.collections.create(
                name=self.collection_name,
                properties=[
                    Property(
                        name="session_id", data_type=DataType.TEXT
                    ),  # For filtering
                    Property(name="document_id", data_type=DataType.TEXT),
                    Property(name="chunk_id", data_type=DataType.INT),
                    Property(name="text", data_type=DataType.TEXT),  # For hybrid search
                    Property(name="page", data_type=DataType.INT),
                    Property(name="created_at", data_type=DataType.NUMBER),  # For TTL
                    # Metadata stored as json-string or individual props?
                    # Weaviate is strict schema. Storing metadata as TEXT (json) is flexible.
                    Property(name="metadata_json", data_type=DataType.TEXT),
                ],
                # Configure vectorizer to none (we bring our own embeddings)
                vectorizer_config=Configure.Vectorizer.none(),
            )
            logger.info("Weaviate collection created")

        except Exception as e:
            logger.error("Failed to ensure Weaviate collection", error=str(e))
            raise RuntimeError(f"Weaviate setup failed: {e}")

    def health_check(self) -> Dict[str, Any]:
        """Check Weaviate health."""
        if not self.client:
            self._connect()

        try:
            if not self.client.is_connected():
                return {"status": "unhealthy", "error": "Client not connected"}

            ready = self.client.is_ready()
            if not ready:
                return {"status": "unhealthy", "error": "Weaviate not ready"}

            exists = self.client.collections.exists(self.collection_name)
            count = 0
            if exists:
                col = self.client.collections.get(self.collection_name)
                # Aggregate count is expensive in Weaviate, approximate or skip
                # Using simple object count iterator or meta query
                response = col.aggregate.over_all(total_count=True)
                count = response.total_count

            return {
                "status": "healthy",
                "collection_exists": exists,
                "points_count": count,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def upsert_chunks(
        self,
        session_id: str,
        document_id: str,
        chunks: List[Dict[str, Any]],
    ) -> int:
        """
        Insert chunks into Weaviate.
        """
        if not self.client.is_connected():
            self._connect()

        collection = self.client.collections.get(self.collection_name)
        current_time = time.time()

        try:
            with collection.batch.dynamic() as batch:
                for chunk in chunks:
                    # Deterministic UUID
                    unique_string = f"{document_id}_{chunk['chunk_id']}"
                    obj_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_string))

                    # Metadata to JSON string for flexibility
                    import json

                    meta_json = json.dumps(chunk.get("metadata", {}))

                    batch.add_object(
                        uuid=obj_uuid,
                        properties={
                            "session_id": session_id,
                            "document_id": document_id,
                            "chunk_id": chunk["chunk_id"],
                            "text": chunk["text"],
                            "page": chunk.get("page", 0),
                            "created_at": current_time,
                            "metadata_json": meta_json,
                        },
                        vector=chunk["embedding"],  # Ensure this is a list of floats
                    )

            # Check for batch errors
            if collection.batch.failed_objects:
                logger.error(
                    "Weaviate batch errors", errors=collection.batch.failed_objects
                )
                raise RuntimeError("Batch insertion failed")

            logger.info("Chunks upserted to Weaviate", count=len(chunks))
            return len(chunks)

        except Exception as e:
            logger.error("Failed to upsert chunks", error=str(e))
            raise

    def _normalize_text(self, text: str) -> str:
        text = text.lower()
        text = unicodedata.normalize("NFD", text)
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return re.sub(r"\s+", " ", text).strip()

    def _augment_query(self, query: str) -> List[str]:
        """Generate query variations using Ontology Terms from Weaviate."""
        if not self.client.is_connected():
            self._connect()

        query_lower = self._normalize_text(query)
        queries = [query]

        try:
            # Check if Ontology_Term collection exists
            if not self.client.collections.exists("Ontology_Term"):
                return queries

            ontology = self.client.collections.get("Ontology_Term")

            # Hybrid search to find relevant terms in the query
            response = ontology.query.hybrid(
                query=query, limit=5, return_properties=["term_name", "synonyms"]
            )

            for obj in response.objects:
                term_name = obj.properties.get("term_name")
                synonyms = obj.properties.get("synonyms", [])

                if term_name and self._normalize_text(term_name) in query_lower:
                    # If term found in query, add its synonyms as variations
                    for syn in synonyms[:2]:  # Top 2 synonyms
                        if not syn:
                            continue
                        # Regex replace ignore case
                        new_q = re.sub(
                            re.escape(term_name), syn, query, flags=re.IGNORECASE
                        )
                        if new_q != query and new_q not in queries:
                            queries.append(new_q)

        except Exception as e:
            logger.warning("Failed to augment query from Ontology", error=str(e))

        return queries[:3]  # Limit variations

    def search(
        self,
        session_id: str,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: float = 0.60,
        query_text: Optional[str] = None,  # Needed for hybrid/adaptive
    ) -> List[Dict[str, Any]]:
        """
        Adaptive Semantic Search.

        If query_text is provided, uses Hybrid Search + Adaptive Reformulation.
        If only query_vector is provided, falls back to standard Vector Search.
        """
        if not self.client.is_connected():
            self._connect()

        collection = self.client.collections.get(self.collection_name)

        # Build filter
        session_filter = Filter.by_property("session_id").equal(session_id)

        # Strategy:
        # 1. Try Hybrid Search with original query
        # 2. If max score < threshold, try augmented queries

        queries_to_try = [query_text] if query_text else []

        # If we have text, generate variations up front
        if query_text:
            queries_to_try = self._augment_query(query_text)

        best_results = []
        best_max_score = -1.0

        # If no text provided, we can only do 1 vector search
        if not queries_to_try:
            queries_to_try = [None]

        for q_text in queries_to_try:
            try:
                # Use Hybrid if text available, else Near Vector
                if q_text:
                    # Hybrid: alpha=0.7 (70% vector, 30% keyword)
                    response = collection.query.hybrid(
                        query=q_text,
                        vector=query_vector,
                        alpha=0.7,
                        limit=top_k,
                        filters=session_filter,
                        return_metadata=MetadataQuery(score=True, distance=True),
                    )
                else:
                    response = collection.query.near_vector(
                        near_vector=query_vector,
                        limit=top_k,
                        filters=session_filter,
                        return_metadata=MetadataQuery(distance=True),
                    )

                # Process results
                current_results = []
                current_max = -1.0

                import json

                for obj in response.objects:
                    # Normalize score
                    # Hybrid score is arbitrary, usually >0. NearVector distance [0,2] -> similarity [0,1]
                    score = 0.0
                    if obj.metadata.score is not None:
                        score = obj.metadata.score  # Hybrid score
                    elif obj.metadata.distance is not None:
                        score = (
                            1 - obj.metadata.distance
                        )  # Cosine similarity assumption

                    if score > current_max:
                        current_max = score

                    # Parse metadata
                    meta = {}
                    if obj.properties.get("metadata_json"):
                        try:
                            meta = json.loads(obj.properties["metadata_json"])
                        except:
                            pass

                    current_results.append(
                        {
                            "document_id": obj.properties["document_id"],
                            "chunk_id": obj.properties["chunk_id"],
                            "text": obj.properties["text"],
                            "page": obj.properties["page"],
                            "score": score,
                            "metadata": meta,
                        }
                    )

                # If this attempt is better, keep it
                # Note: Comparing Hybrid scores across different text queries is tricky
                # but roughly indicates relevance.
                if current_max > best_max_score:
                    best_max_score = current_max
                    best_results = current_results

                # Early exit if we found a very good match
                if best_max_score > 0.75:
                    break

            except Exception as e:
                logger.error(
                    "Weaviate search attempt failed", query=q_text, error=str(e)
                )
                continue

        # Log retrieval stats
        logger.info(
            "Weaviate search completed",
            session_id=session_id,
            results=len(best_results),
            best_score=best_max_score,
            attempts=len(queries_to_try),
        )

        return best_results

    def delete_session(self, session_id: str) -> int:
        """Delete all chunks for a session."""
        if not self.client.is_connected():
            self._connect()

        collection = self.client.collections.get(self.collection_name)
        try:
            # Batch delete
            result = collection.data.delete_many(
                where=Filter.by_property("session_id").equal(session_id)
            )
            logger.info(
                "Session deleted", session_id=session_id, count=result.successful
            )
            return result.successful
        except Exception as e:
            logger.error("Failed to delete session", error=str(e))
            raise

    def cleanup_expired_sessions(self, ttl_hours: int = 24) -> int:
        """Delete old chunks."""
        if not self.client.is_connected():
            self._connect()

        collection = self.client.collections.get(self.collection_name)
        cutoff = time.time() - (ttl_hours * 3600)

        try:
            result = collection.data.delete_many(
                where=Filter.by_property("created_at").less_than(cutoff)
            )
            logger.info("Expired chunks cleaned", count=result.successful)
            return result.successful
        except Exception as e:
            logger.error("Cleanup failed", error=str(e))
            return 0

    def resolve_ambiguous_term(
        self,
        term: str,
        context_metric: Optional[str] = None,
        min_similarity: float = 0.65,
    ) -> Optional[tuple]:
        """
        Resolve an ambiguous term using context category.

        Strategy:
        1. Search for candidates in Ontology_Term
        2. If single candidate → no ambiguity, return it
        3. If multiple candidates → use context_metric's category to select
        4. If no context or no match → return None (requires HARD_ASK)

        Args:
            term: Ambiguous term (e.g., "capitalización")
            context_metric: Metric from context (e.g., "metric_a") to infer category
            min_similarity: Minimum similarity threshold

        Returns:
            Tuple (linked_field, category) if resolved, None otherwise

        Examples:
            >>> service.resolve_ambiguous_term("term_x", context_metric="metric_a")
            ("linked_field", "category")  # Resolved via context

            >>> service.resolve_ambiguous_term("term_x", context_metric=None)
            None  # Cannot resolve without context
        """
        if not self.client.is_connected():
            self._connect()

        try:
            # Check if Ontology_Term collection exists
            if not self.client.collections.exists("Ontology_Term"):
                logger.debug("resolve_ambiguous.no_ontology")
                return None

            ontology = self.client.collections.get("Ontology_Term")

            # 1. Search for candidates matching the ambiguous term
            response = ontology.query.hybrid(
                query=term,
                limit=5,
                return_properties=["term_name", "linked_field", "category", "synonyms"],
            )

            candidates = response.objects
            if not candidates:
                logger.debug("resolve_ambiguous.no_candidates", term=term)
                return None

            # 2. Single candidate → no ambiguity
            if len(candidates) == 1:
                c = candidates[0].properties
                result = (c.get("linked_field", c.get("term_name")), c.get("category"))
                logger.info(
                    "resolve_ambiguous.single_candidate",
                    term=term,
                    resolved_to=result[0],
                )
                return result

            # 3. Multiple candidates → need context to disambiguate
            if not context_metric:
                logger.info(
                    "resolve_ambiguous.multiple_no_context",
                    term=term,
                    candidates=[c.properties.get("linked_field") for c in candidates],
                )
                return None

            # 4. Get context metric's category
            context_response = ontology.query.hybrid(
                query=context_metric,
                limit=1,
                return_properties=["term_name", "category"],
            )

            if not context_response.objects:
                logger.debug(
                    "resolve_ambiguous.context_not_found",
                    context_metric=context_metric,
                )
                return None

            context_category = context_response.objects[0].properties.get("category")

            # 5. Select candidate matching context category
            for candidate in candidates:
                props = candidate.properties
                if props.get("category") == context_category:
                    result = (
                        props.get("linked_field", props.get("term_name")),
                        props.get("category"),
                    )
                    logger.info(
                        "resolve_ambiguous.resolved_by_category",
                        term=term,
                        resolved_to=result[0],
                        category=context_category,
                    )
                    return result

            # 6. No candidate matches context category
            logger.info(
                "resolve_ambiguous.category_mismatch",
                term=term,
                context_category=context_category,
                candidate_categories=[c.properties.get("category") for c in candidates],
            )
            return None

        except Exception as e:
            logger.warning("resolve_ambiguous.error", error=str(e), term=term)
            return None

    def get_term_category(self, metric: str) -> Optional[str]:
        """
        Get the category of a metric from the ontology.

        Useful for determining the semantic domain of context.

        Args:
            metric: Metric name (e.g., "metric_a", "metric_b")

        Returns:
            Category (e.g., "category_a", "category_b") or None
        """
        if not self.client.is_connected():
            self._connect()

        try:
            if not self.client.collections.exists("Ontology_Term"):
                return None

            ontology = self.client.collections.get("Ontology_Term")

            response = ontology.query.hybrid(
                query=metric,
                limit=1,
                return_properties=["term_name", "category"],
            )

            if response.objects:
                category = response.objects[0].properties.get("category")
                logger.debug(
                    "get_term_category.found",
                    metric=metric,
                    category=category,
                )
                return category

            return None

        except Exception as e:
            logger.warning("get_term_category.error", error=str(e), metric=metric)
            return None


# Singleton
_weaviate_service: Optional[WeaviateService] = None


def get_weaviate_service() -> WeaviateService:
    global _weaviate_service
    if _weaviate_service is None:
        _weaviate_service = WeaviateService()
    return _weaviate_service
