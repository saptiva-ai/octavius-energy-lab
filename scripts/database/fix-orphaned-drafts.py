#!/usr/bin/env python3
"""
Fix orphaned draft conversations

This script finds draft conversations with messages (message_count > 0)
and transitions them to ACTIVE state. This fixes the bug where drafts
didn't properly transition on first message.

P0-BE-UNIQ-EMPTY: Maintains the invariant that only empty drafts exist.

Usage:
    python scripts/fix-orphaned-drafts.py [--dry-run]
"""

import asyncio
import os
import sys
from datetime import datetime

# Add apps/api to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'api'))

from motor.motor_asyncio import AsyncIOMotorClient


async def fix_orphaned_drafts(dry_run: bool = False):
    """Find and fix orphaned draft conversations"""

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

    # Find all drafts with messages
    orphaned_drafts = await db['chat_sessions'].find({
        'state': 'draft',
        'message_count': {'$gt': 0}
    }).to_list(None)

    if not orphaned_drafts:
        print("✅ No orphaned drafts found! Database is clean.")
        return

    print(f"📊 Found {len(orphaned_drafts)} orphaned draft(s) with messages:")
    print("")

    for draft in orphaned_drafts:
        print(f"  📝 Draft ID: {draft['_id']}")
        print(f"     User:     {draft.get('user_id', 'unknown')}")
        print(f"     Messages: {draft.get('message_count', 0)}")
        print(f"     Title:    {draft.get('title', 'Untitled')}")
        print(f"     Created:  {draft.get('created_at', 'unknown')}")
        print("")

    if dry_run:
        print("🔒 DRY RUN MODE - No changes made")
        print("   Run without --dry-run to apply fixes")
        return

    # Ask for confirmation
    response = input(f"⚠️  Transition {len(orphaned_drafts)} draft(s) to ACTIVE state? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print("❌ Aborted - no changes made")
        return

    print("")
    print("🔧 Fixing orphaned drafts...")

    # Fix each orphaned draft
    fixed_count = 0
    for draft in orphaned_drafts:
        try:
            result = await db['chat_sessions'].update_one(
                {'_id': draft['_id']},
                {
                    '$set': {
                        'state': 'active',
                        'updated_at': datetime.utcnow()
                    }
                }
            )

            if result.modified_count > 0:
                print(f"  ✅ Fixed: {draft['_id']} ({draft.get('title', 'Untitled')})")
                fixed_count += 1
            else:
                print(f"  ⚠️  No change: {draft['_id']}")
        except Exception as e:
            print(f"  ❌ Error fixing {draft['_id']}: {e}")

    print("")
    print(f"✅ Successfully fixed {fixed_count}/{len(orphaned_drafts)} draft(s)")
    print("")

    # Verify results
    remaining_orphaned = await db['chat_sessions'].count_documents({
        'state': 'draft',
        'message_count': {'$gt': 0}
    })

    if remaining_orphaned == 0:
        print("🎉 All orphaned drafts have been fixed!")
    else:
        print(f"⚠️  {remaining_orphaned} orphaned draft(s) still remain")

    client.close()


def main():
    """Main entry point"""
    dry_run = '--dry-run' in sys.argv

    print("=" * 70)
    print("  🔧 Fix Orphaned Drafts Script")
    print("=" * 70)
    print("")

    if dry_run:
        print("🔒 Running in DRY RUN mode - no changes will be made")
        print("")

    try:
        asyncio.run(fix_orphaned_drafts(dry_run=dry_run))
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
