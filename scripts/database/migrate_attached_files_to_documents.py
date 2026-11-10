#!/usr/bin/env python3
"""
Migration script: attached_file_ids → documents

Converts legacy List[str] to structured DocumentState objects.

Usage:
    python scripts/migrate_attached_files_to_documents.py --dry-run
    python scripts/migrate_attached_files_to_documents.py --execute
"""

import asyncio
import argparse
import sys
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
import structlog

# Add parent directory to path for imports
sys.path.insert(0, '/app')

from src.core.config import get_settings
from src.models.chat import ChatSession
from src.models.document import Document
from src.models.document_state import DocumentState, ProcessingStatus

logger = structlog.get_logger()


async def migrate_session(session: ChatSession, dry_run: bool = True) -> dict:
    """Migrate a single session's attached_file_ids to documents"""

    stats = {
        "session_id": session.id,
        "legacy_count": len(session.attached_file_ids),
        "migrated_count": 0,
        "failed_count": 0,
        "already_migrated": len(session.documents) > 0
    }

    # Skip if already has documents field populated
    if session.documents:
        print(f"⏭️  Session {session.id[:8]} already migrated ({len(session.documents)} docs)")
        return stats

    # Skip empty sessions
    if not session.attached_file_ids:
        print(f"⏭️  Session {session.id[:8]} has no attached files")
        return stats

    print(f"🔄 Migrating session {session.id[:8]} with {len(session.attached_file_ids)} files...")

    # Convert each file_id to DocumentState
    for file_id in session.attached_file_ids:
        try:
            # Try to fetch document metadata from Document collection
            doc = await Document.get(file_id)

            if doc:
                # Safely get metadata
                pages = None
                if hasattr(doc, 'metadata') and doc.metadata:
                    pages = doc.metadata.get("pages")

                doc_state = DocumentState(
                    doc_id=file_id,
                    name=doc.filename,
                    pages=pages,
                    size_bytes=getattr(doc, 'size_bytes', None),
                    mimetype=getattr(doc, 'content_type', None),
                    status=ProcessingStatus.READY,  # Assume legacy docs are processed
                    segments_count=1,  # Assume at least 1 segment
                    indexed_at=getattr(doc, 'created_at', datetime.utcnow()),
                    created_at=getattr(doc, 'created_at', datetime.utcnow())
                )
            else:
                # Document not found - create minimal DocumentState
                print(f"  ⚠️  Document {file_id[:8]} not found, creating minimal state")
                doc_state = DocumentState(
                    doc_id=file_id,
                    name=f"document_{file_id[:8]}",
                    status=ProcessingStatus.READY,
                    created_at=datetime.utcnow()
                )

            session.documents.append(doc_state)
            stats["migrated_count"] += 1

        except Exception as e:
            print(f"  ❌ Failed to migrate {file_id[:8]}: {e}")
            stats["failed_count"] += 1

    # Save changes
    if not dry_run:
        await session.save()
        print(f"✅ Migrated {stats['migrated_count']} documents for session {session.id[:8]}")
    else:
        print(f"🔍 [DRY RUN] Would migrate {stats['migrated_count']} documents")

    return stats


async def migrate_all_sessions(dry_run: bool = True):
    """Migrate all sessions with attached_file_ids"""

    settings = get_settings()

    # Initialize Beanie
    client = AsyncIOMotorClient(settings.mongodb_url)
    # Extract database name from URL (default: octavios)
    import re
    match = re.search(r'/([^/\?]+)(\?|$)', settings.mongodb_url)
    db_name = match.group(1) if match else 'octavios'

    await init_beanie(
        database=client[db_name],
        document_models=[ChatSession, Document]
    )

    # Find all sessions with attached files
    sessions = await ChatSession.find(
        {"attached_file_ids": {"$exists": True, "$ne": []}}
    ).to_list()

    print(f"\n📊 Found {len(sessions)} sessions with attached files\n")

    total_stats = {
        "total_sessions": len(sessions),
        "migrated": 0,
        "failed": 0,
        "skipped": 0,
        "total_docs_migrated": 0,
        "total_docs_failed": 0
    }

    for session in sessions:
        stats = await migrate_session(session, dry_run=dry_run)

        if stats["already_migrated"]:
            total_stats["skipped"] += 1
        elif stats["migrated_count"] > 0:
            total_stats["migrated"] += 1
            total_stats["total_docs_migrated"] += stats["migrated_count"]

        total_stats["total_docs_failed"] += stats["failed_count"]

    # Summary
    print("\n" + "="*60)
    print("📈 MIGRATION SUMMARY")
    print("="*60)
    print(f"Total sessions: {total_stats['total_sessions']}")
    print(f"✅ Migrated: {total_stats['migrated']} sessions")
    print(f"   └─ Documents migrated: {total_stats['total_docs_migrated']}")
    print(f"⏭️  Skipped (already migrated): {total_stats['skipped']}")
    print(f"❌ Failed documents: {total_stats['total_docs_failed']}")
    print("="*60)

    if dry_run:
        print("\n⚠️  This was a DRY RUN. Run with --execute to apply changes.")
    else:
        print("\n✅ Migration complete!")

    # Validation query
    if not dry_run:
        print("\n🔍 Validation:")
        migrated_count = await ChatSession.find(
            {"documents.0": {"$exists": True}}
        ).count()
        print(f"Sessions with documents field: {migrated_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate attached_file_ids to documents")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute migration (default is dry-run)"
    )

    args = parser.parse_args()

    asyncio.run(migrate_all_sessions(dry_run=not args.execute))
