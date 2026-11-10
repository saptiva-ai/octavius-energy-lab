#!/usr/bin/env python3
"""
Migration: Add TTL and compound indexes for bank_chart artifacts support.

This migration:
1. Creates TTL index on expires_at field for automatic cleanup
2. Creates compound index on (chat_session_id, created_at) for efficient queries
3. Validates existing bank_chart artifacts (if any)

Run:
    python scripts/migrations/add_bank_chart_ttl_indexes.py

Rollback:
    python scripts/migrations/add_bank_chart_ttl_indexes.py --rollback
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "apps" / "backend"))

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

from src.core.config import get_settings


async def create_indexes(db):
    """Create new indexes for bank_chart artifact support."""
    artifacts = db["artifacts"]

    print("📊 Creating indexes for bank_chart artifacts...")

    # 1. TTL index for automatic cleanup (expires after expires_at timestamp)
    try:
        await artifacts.create_index(
            [("expires_at", ASCENDING)],
            name="expires_at_ttl",
            expireAfterSeconds=0,  # Expire immediately when expires_at is reached
        )
        print("✅ Created TTL index on 'expires_at' field")
    except OperationFailure as e:
        if "already exists" in str(e):
            print("⚠️  TTL index 'expires_at_ttl' already exists")
        else:
            raise

    # 2. Compound index for efficient session queries (most recent first)
    try:
        await artifacts.create_index(
            [("chat_session_id", ASCENDING), ("created_at", DESCENDING)],
            name="session_created_desc",
        )
        print("✅ Created compound index on (chat_session_id, created_at)")
    except OperationFailure as e:
        if "already exists" in str(e):
            print("⚠️  Compound index 'session_created_desc' already exists")
        else:
            raise

    # 3. Validate existing bank_chart artifacts
    bank_chart_count = await artifacts.count_documents({"type": "bank_chart"})
    print(f"📈 Found {bank_chart_count} existing bank_chart artifacts")

    if bank_chart_count > 0:
        # Sample one to validate structure
        sample = await artifacts.find_one({"type": "bank_chart"})
        if sample:
            has_expires_at = "expires_at" in sample
            has_plotly_config = (
                isinstance(sample.get("content"), dict)
                and "plotly_config" in sample.get("content", {})
            )

            print(f"   - Sample artifact ID: {sample.get('_id')}")
            print(f"   - Has expires_at: {has_expires_at}")
            print(f"   - Has plotly_config: {has_plotly_config}")

            if not has_expires_at:
                print("⚠️  WARNING: Existing artifacts missing expires_at field")
                print("   Consider backfilling with: expires_at = created_at + 30 days")

    print("\n🎉 Migration completed successfully!")


async def rollback_indexes(db):
    """Rollback: Drop created indexes."""
    artifacts = db["artifacts"]

    print("🔄 Rolling back bank_chart indexes...")

    try:
        await artifacts.drop_index("expires_at_ttl")
        print("✅ Dropped TTL index 'expires_at_ttl'")
    except OperationFailure as e:
        print(f"⚠️  Could not drop TTL index: {e}")

    try:
        await artifacts.drop_index("session_created_desc")
        print("✅ Dropped compound index 'session_created_desc'")
    except OperationFailure as e:
        print(f"⚠️  Could not drop compound index: {e}")

    print("\n🔙 Rollback completed!")


async def main():
    """Main migration entry point."""
    settings = get_settings()

    # Parse command line args
    is_rollback = "--rollback" in sys.argv

    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_name = settings.MONGODB_URL.split("/")[-1].split("?")[0]
    db = client[db_name]

    print(f"🔌 Connected to MongoDB: {db_name}")
    print(f"📦 Collection: artifacts")
    print()

    try:
        if is_rollback:
            await rollback_indexes(db)
        else:
            await create_indexes(db)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
