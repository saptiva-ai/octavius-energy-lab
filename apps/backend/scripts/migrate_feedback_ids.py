"""Migrate existing feedback to add incremental FDBK-XXXX IDs.

This script:
1. Finds all feedback entries without a feedback_id
2. Assigns incremental IDs (FDBK-0001, FDBK-0002, etc.) in chronological order
3. Updates the counter collection to track the last used sequence number

Run with:
    cd apps/backend && python scripts/migrate_feedback_ids.py

Or via Docker:
    docker compose exec backend python scripts/migrate_feedback_ids.py
"""

import asyncio
import sys
from pathlib import Path

import structlog

# Add src to path before importing local modules
CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# Local imports after path setup
from core.database import Database  # noqa: E402
from models.feedback import FeedbackStatus, MessageFeedback  # noqa: E402

logger = structlog.get_logger(__name__)


async def migrate_feedback_ids() -> None:
    """Assign incremental FDBK-XXXX IDs to all existing feedback."""
    await Database.connect_to_mongo()

    try:
        db = Database.get_database()
        if db is None:
            raise RuntimeError("Database not initialized")

        # Get all feedback sorted by created_at (oldest first)
        feedbacks = (
            await MessageFeedback.find(
                MessageFeedback.feedback_id == None  # noqa: E711
            )
            .sort("+created_at")
            .to_list()
        )

        if not feedbacks:
            print("No feedback entries without feedback_id found.")
            logger.info("Migration complete - no entries to migrate")
            return

        print(f"Found {len(feedbacks)} feedback entries to migrate...")
        logger.info("Starting migration", count=len(feedbacks))

        # Get current counter value (or start from 0)
        counters = db.counters
        counter_doc = await counters.find_one({"_id": "feedback_id"})
        start_seq = counter_doc["seq"] if counter_doc else 0

        print(f"Starting sequence: {start_seq}")

        # Assign IDs
        migrated = 0
        for i, fb in enumerate(feedbacks, start=1):
            seq = start_seq + i
            new_feedback_id = f"FDBK-{seq:04d}"

            # Update feedback document
            fb.feedback_id = new_feedback_id

            # Set status to NEW if not already set (for tracking)
            if fb.status is None:
                fb.status = FeedbackStatus.NEW

            await fb.save()
            migrated += 1

            if migrated % 100 == 0:
                print(f"  Migrated {migrated}/{len(feedbacks)}...")

        # Update counter to the new max value
        final_seq = start_seq + len(feedbacks)
        await counters.update_one(
            {"_id": "feedback_id"},
            {"$set": {"seq": final_seq}},
            upsert=True,
        )

        print(f"Migration complete!")
        print(f"  - Migrated: {migrated} feedback entries")
        print(f"  - ID range: FDBK-{start_seq + 1:04d} to FDBK-{final_seq:04d}")
        print(f"  - Counter updated to: {final_seq}")

        logger.info(
            "Migration complete",
            migrated=migrated,
            start_seq=start_seq + 1,
            end_seq=final_seq,
        )

    finally:
        await Database.close_mongo_connection()


async def show_stats() -> None:
    """Show current feedback ID statistics."""
    await Database.connect_to_mongo()

    try:
        db = Database.get_database()
        if db is None:
            raise RuntimeError("Database not initialized")

        # Count feedback with and without IDs
        total = await MessageFeedback.count()
        with_id = await MessageFeedback.find(
            MessageFeedback.feedback_id != None  # noqa: E711
        ).count()
        without_id = await MessageFeedback.find(
            MessageFeedback.feedback_id == None  # noqa: E711
        ).count()

        # Get counter value
        counters = db.counters
        counter_doc = await counters.find_one({"_id": "feedback_id"})
        current_seq = counter_doc["seq"] if counter_doc else 0

        print("Feedback ID Statistics:")
        print(f"  - Total feedback: {total}")
        print(f"  - With FDBK ID: {with_id}")
        print(f"  - Without FDBK ID: {without_id}")
        print(f"  - Counter sequence: {current_seq}")

    finally:
        await Database.close_mongo_connection()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stats":
        asyncio.run(show_stats())
    else:
        asyncio.run(migrate_feedback_ids())
