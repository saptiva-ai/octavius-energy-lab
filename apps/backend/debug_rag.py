"""
Debug script to check RAG workflow status
"""
import asyncio
from src.models.chat import ChatSession
from src.core.redis_cache import get_redis_cache
from src.core.database import init_db
import structlog

logger = structlog.get_logger(__name__)


async def check_rag_status():
    """Check RAG document processing status"""

    # Initialize database
    await init_db()

    # Get recent sessions
    sessions = await ChatSession.find().sort("-created_at").limit(5).to_list()

    print(f"\n{'='*80}")
    print(f"RAG Status Check - Last 5 Sessions")
    print(f"{'='*80}\n")

    for session in sessions:
        print(f"Session ID: {session.id}")
        print(f"Created: {session.created_at}")
        print(f"Documents: {len(session.documents)}")

        if session.documents:
            print(f"\n  Document Details:")
            for doc in session.documents:
                print(f"    - {doc.name}")
                print(f"      Doc ID: {doc.doc_id}")
                print(f"      Status: {doc.status.value}")
                print(f"      Segments: {doc.segments_count}")
                print(f"      Error: {doc.error or 'None'}")

                # Check Redis cache
                cache = await get_redis_cache()
                cache_key = f"doc_segments:{doc.doc_id}"
                cached_segments = await cache.get(cache_key)

                if cached_segments:
                    print(f"      ✅ Redis Cache: {len(cached_segments)} segments found")
                else:
                    print(f"      ❌ Redis Cache: No segments found")

        print(f"\n{'-'*80}\n")


if __name__ == "__main__":
    asyncio.run(check_rag_status())
