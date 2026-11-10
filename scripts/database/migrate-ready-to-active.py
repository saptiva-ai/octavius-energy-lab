#!/usr/bin/env python3
"""
Migrate conversations with 'ready' state to 'active' state

This script fixes the breaking change from the old state model (ready/active)
to the new Progressive Commitment model (draft/active/creating/error).

All 'ready' conversations should become 'active' since they contain messages.

Usage:
    python scripts/migrate-ready-to-active.py [--dry-run]
"""

import asyncio
import os
import sys
from datetime import datetime

# Add apps/api to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'api'))

from motor.motor_asyncio import AsyncIOMotorClient


async def migrate_ready_to_active(dry_run: bool = False):
    """Migrate all 'ready' state conversations to 'active'"""

    # Get MongoDB connection from environment
    mongodb_url = os.getenv('MONGODB_URL')
    if not mongodb_url:
        print("❌ Error: MONGODB_URL not set in environment")
        sys.exit(1)

    # Connect to MongoDB
    client = AsyncIOMotorClient(mongodb_url)
    db_name = mongodb_url.split('/')[-1].split('?')[0]
    db = client[db_name]

    print(f"🔍 Connected to database: {db_name}")
    print("")

    # Find all conversations with 'ready' state
    ready_sessions = await db['chat_sessions'].find({
        'state': 'ready'
    }).to_list(None)

    if not ready_sessions:
        print("✅ No 'ready' state conversations found! Database is up to date.")
        return

    print(f"📊 Found {len(ready_sessions)} conversation(s) with 'ready' state:")
    print("")

    for session in ready_sessions:
        print(f"  📝 Session ID: {session['_id']}")
        print(f"     User:     {session.get('user_id', 'unknown')}")
        print(f"     Messages: {session.get('message_count', 0)}")
        print(f"     Title:    {session.get('title', 'Untitled')}")
        print(f"     Created:  {session.get('created_at', 'unknown')}")
        print("")

    if dry_run:
        print("🔒 DRY RUN MODE - No changes made")
        print("   Run without --dry-run to apply migration")
        return

    # Ask for confirmation
    response = input(f"⚠️  Migrate {len(ready_sessions)} conversation(s) from 'ready' to 'active'? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print("❌ Aborted - no changes made")
        return

    print("")
    print("🔧 Migrating conversations...")

    # Migrate each conversation
    migrated_count = 0
    for session in ready_sessions:
        try:
            result = await db['chat_sessions'].update_one(
                {'_id': session['_id']},
                {
                    '$set': {
                        'state': 'active',
                        'updated_at': datetime.utcnow()
                    }
                }
            )

            if result.modified_count > 0:
                print(f"  ✅ Migrated: {session['_id']} ({session.get('title', 'Untitled')})")
                migrated_count += 1
            else:
                print(f"  ⚠️  No change: {session['_id']}")
        except Exception as e:
            print(f"  ❌ Error migrating {session['_id']}: {e}")

    print("")
    print(f"✅ Successfully migrated {migrated_count}/{len(ready_sessions)} conversation(s)")
    print("")

    # Verify results
    remaining_ready = await db['chat_sessions'].count_documents({
        'state': 'ready'
    })

    if remaining_ready == 0:
        print("🎉 All 'ready' conversations have been migrated to 'active'!")
    else:
        print(f"⚠️  {remaining_ready} 'ready' conversation(s) still remain")

    client.close()


def main():
    """Main entry point"""
    dry_run = '--dry-run' in sys.argv

    print("=" * 70)
    print("  🔧 Migrate 'ready' → 'active' State")
    print("=" * 70)
    print("")

    if dry_run:
        print("🔒 Running in DRY RUN mode - no changes will be made")
        print("")

    try:
        asyncio.run(migrate_ready_to_active(dry_run=dry_run))
    except KeyboardInterrupt:
        print("")
        print("❌ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
