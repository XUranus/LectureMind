"""
Vector store abstraction using ChromaDB for lecture knowledge retrieval.

Provides semantic search over lecture content (transcript sentences,
knowledge points, section summaries) using sentence-transformers embeddings.

Usage:
    from api.vector_store import get_vector_store

    store = get_vector_store()
    store.upsert(id="kp-1", text="Gradient descent...", metadata={...})
    results = store.query("What is backpropagation?", video_id="uuid")
"""

import os
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger('LectureMind')

# Default configuration (overridden by Django settings / env var CHROMA_PERSIST_DIR)
DEFAULT_PERSIST_DIR = "./media/chromadb"
DEFAULT_COLLECTION_NAME = "lecture_knowledge"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def _default_chroma_dir() -> str:
    """Return ChromaDB persist dir from Django settings if available, else env/fallback."""
    try:
        from django.conf import settings
        return getattr(settings, 'CHROMA_PERSIST_DIR', '') or DEFAULT_PERSIST_DIR
    except Exception:
        return os.environ.get('CHROMA_PERSIST_DIR', DEFAULT_PERSIST_DIR)


class VectorStore:
    """
    ChromaDB-backed vector store for lecture content retrieval.

    Stores and retrieves text documents with dense vector embeddings,
    supporting filtering by video_id and content type.
    """

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        self.persist_dir = persist_dir or _default_chroma_dir()
        self.collection_name = collection_name or DEFAULT_COLLECTION_NAME
        self.embedding_model_name = embedding_model or DEFAULT_EMBEDDING_MODEL

        self._client = None
        self._collection = None
        self._encoder = None
        self._initialized = False

    def _ensure_initialized(self):
        """Lazy initialization to avoid import errors at module load time."""
        if self._initialized:
            return

        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise RuntimeError(
                "chromadb package not installed. "
                "Install with: pip install chromadb"
            )

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise RuntimeError(
                "sentence-transformers package not installed. "
                "Install with: pip install sentence-transformers"
            )

        # Create persist directory
        os.makedirs(self.persist_dir, exist_ok=True)

        # Initialize ChromaDB persistent client
        self._client = chromadb.PersistentClient(path=self.persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        # Initialize embedding model
        self._encoder = SentenceTransformer(
            self.embedding_model_name, device="cpu"
        )

        self._initialized = True
        logger.info(
            f"VectorStore initialized: persist_dir={self.persist_dir}, "
            f"collection={self.collection_name}, "
            f"embedding_model={self.embedding_model_name}, "
            f"existing_count={self._collection.count()}"
        )

    def upsert(
        self,
        id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> None:
        """
        Insert or update a document in the vector store.

        Args:
            id: Unique document identifier.
            text: Document text to embed and store.
            metadata: Metadata dict (must contain string/int/float values only).
                      Recommended keys: video_id, type, title, begin_time, end_time.
        """
        self._ensure_initialized()

        # Encode text to embedding
        embedding = self._encoder.encode(text).tolist()

        # ChromaDB requires metadata values to be str, int, float, or bool
        clean_metadata = {}
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                clean_metadata[k] = v
            elif v is None:
                clean_metadata[k] = ""
            else:
                clean_metadata[k] = str(v)

        self._collection.upsert(
            ids=[id],
            embeddings=[embedding],
            metadatas=[clean_metadata],
            documents=[text],
        )

    def upsert_batch(
        self,
        ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """
        Batch insert/update documents.

        Args:
            ids: List of unique identifiers.
            texts: List of document texts.
            metadatas: List of metadata dicts.
            batch_size: Number of documents per batch.

        Returns:
            Total number of documents upserted.
        """
        self._ensure_initialized()

        total = len(ids)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_texts = texts[start:end]
            batch_ids = ids[start:end]
            batch_metas = metadatas[start:end]

            # Encode batch
            embeddings = self._encoder.encode(batch_texts).tolist()

            # Clean metadata
            clean_metas = []
            for meta in batch_metas:
                clean = {}
                for k, v in meta.items():
                    if isinstance(v, (str, int, float, bool)):
                        clean[k] = v
                    elif v is None:
                        clean[k] = ""
                    else:
                        clean[k] = str(v)
                clean_metas.append(clean)

            self._collection.upsert(
                ids=batch_ids,
                embeddings=embeddings,
                metadatas=clean_metas,
                documents=batch_texts,
            )
            logger.debug(f"Upserted batch {start}-{end} of {total}")

        return total

    def query(
        self,
        query_text: str,
        video_id: Optional[str] = None,
        content_type: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over stored documents.

        Args:
            query_text: Natural language query.
            video_id: Optional filter to scope results to a specific video.
            content_type: Optional filter by content type
                         (e.g., "transcript", "knowledge_point", "section", "summary").
            top_k: Maximum number of results.

        Returns:
            List of result dicts, each containing:
                - id: Document ID
                - text: Document text
                - metadata: Original metadata
                - distance: Cosine distance (lower = more similar)
                - relevance: Cosine similarity score (higher = more similar)
        """
        self._ensure_initialized()

        # Build embedding for query
        query_embedding = self._encoder.encode(query_text).tolist()

        # Build where filter
        where_filter = None
        conditions = []
        if video_id:
            conditions.append({"video_id": video_id})
        if content_type:
            conditions.append({"type": content_type})

        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        # Query ChromaDB
        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self._collection.count() or top_k),
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"Vector store query failed: {e}")
            return []

        # Format results
        formatted = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else 0.0
                formatted.append({
                    "id": doc_id,
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": distance,
                    "relevance": 1.0 - distance,  # cosine distance to similarity
                })

        return formatted

    def delete_by_video(self, video_id: str) -> None:
        """
        Delete all documents for a specific video.
        Useful for cleanup when a video is deleted or reprocessed.
        """
        self._ensure_initialized()

        try:
            self._collection.delete(where={"video_id": video_id})
            logger.info(f"Deleted all vector store entries for video {video_id}")
        except Exception as e:
            logger.error(f"Failed to delete entries for video {video_id}: {e}")

    def count(self, video_id: Optional[str] = None) -> int:
        """Get document count, optionally filtered by video_id."""
        self._ensure_initialized()

        if video_id:
            try:
                results = self._collection.get(
                    where={"video_id": video_id},
                    include=[],
                )
                return len(results["ids"]) if results["ids"] else 0
            except Exception:
                return 0
        return self._collection.count()

    def reset(self) -> None:
        """Delete all documents from the collection."""
        self._ensure_initialized()
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("Vector store collection reset (all documents deleted)")


# Module-level singleton
_default_store: Optional[VectorStore] = None


def get_vector_store(**kwargs) -> VectorStore:
    """
    Get the default vector store singleton, or create one with custom settings.
    """
    global _default_store
    if kwargs:
        return VectorStore(**kwargs)
    if _default_store is None:
        _default_store = VectorStore()
    return _default_store
