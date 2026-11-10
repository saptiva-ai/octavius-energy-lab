#!/usr/bin/env python3
"""
Migrate conversation timestamps for Progressive Commitment Pattern

This script backfills first_message_at and last_message_at for existing conversations
by querying the actual messages in the messages collection.

Progressive Commitment Pattern:
- Conversations should only persist if they have messages
- first_message_at = timestamp of first message
- last_message_at = timestamp of most recent message

Usage:
    python scripts/migrate-conversation-timestamps.py [--dry-run]
"""

import asyncio
import os
import sys
from datetime import datetime

# Add apps/api to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'api'))

from motor.motor_asyncio import AsyncIOMotorClient


async def migrate_timestamps(dry_run: bool = False):
    """Backfill first_message_at and last_message_at for conversations"""

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

    # Find all conversations without timestamp fields or with null timestamps
    conversations = await db['chat_sessions'].find({
        '$or': [
            {'first_message_at': {'$exists': False}},
            {'first_message_at': None},
            {'last_message_at': {'$exists': False}},
            {'last_message_at': None}
        ]
    }).to_list(None)

    if not conversations:
        print("✅ No conversations need migration! All timestamps are set.")
        return

    print(f"📊 Found {len(conversations)} conversation(s) needing timestamp migration")
    print("")

    # Separate conversations by message_count
    with_messages = [c for c in conversations if c.get('message_count', 0) > 0]
    empty = [c for c in conversations if c.get('message_count', 0) == 0]

    print(f"  📝 With messages: {len(with_messages)}")
    print(f"  🗑️  Empty (will be deleted): {len(empty)}")
    print("")

    if dry_run:
        print("🔒 DRY RUN MODE - No changes will be made")
        print("")
        print("Sample conversations to migrate:")
        for conv in with_messages[:5]:
            print(f"  - {conv['_id']}: {conv.get('title', 'Untitled')} ({conv.get('message_count', 0)} messages)")
        print("")
        print("Sample empty conversations to delete:")
        for conv in empty[:5]:
            print(f"  - {conv['_id']}: {conv.get('title', 'Untitled')}")
        return

    # Ask for confirmation
    response = input(f"⚠️  Migrate {len(with_messages)} conversation(s) and delete {len(empty)} empty one(s)? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print("❌ Aborted - no changes made")
        return

    print("")
    print("🔧 Migrating conversation timestamps...")
    print("")

    migrated_count = 0
    deleted_count = 0
    error_count = 0

    # Delete empty conversations (they shouldn't exist with progressive commitment)
    if empty:
        print("🗑️  Deleting empty conversations...")
        for conv in empty:
            try:
                result = await db['chat_sessions'].delete_one({'_id': conv['_id']})
                if result.deleted_count > 0:
                    print(f"  ✅ Deleted empty: {conv['_id']} ({conv.get('title', 'Untitled')})")
                    deleted_count += 1
                else:
                    print(f"  ⚠️  Not found: {conv['_id']}")
            except Exception as e:
                print(f"  ❌ Error deleting {conv['_id']}: {e}")
                error_count += 1
        print("")

    # Migrate conversations with messages
    print("📝 Backfilling timestamps for conversations with messages...")
    for conv in with_messages:
        try:
            # Get first message (oldest)
            first_message = await db['messages'].find_one(
                {'chat_id': conv['_id']},
                sort=[('created_at', 1)]  # Ascending - oldest first
            )

            # Get last message (newest)
            last_message = await db['messages'].find_one(
                {'chat_id': conv['_id']},
                sort=[('created_at', -1)]  # Descending - newest first
            )

            if not first_message or not last_message:
                # Conversation has message_count > 0 but no actual messages (inconsistent state)
                print(f"  ⚠️  Inconsistent: {conv['_id']} has message_count={conv.get('message_count')} but no messages in DB")
                # Delete this inconsistent conversation
                await db['chat_sessions'].delete_one({'_id': conv['_id']})
                print(f"     → Deleted inconsistent conversation")
                deleted_count += 1
                continue

            # Update conversation with timestamps
            result = await db['chat_sessions'].update_one(
                {'_id': conv['_id']},
                {
                    '$set': {
                        'first_message_at': first_message['created_at'],
                        'last_message_at': last_message['created_at'],
                        'updated_at': datetime.utcnow()
                    }
                }
            )

            if result.modified_count > 0:
                print(f"  ✅ Migrated: {conv['_id']} ({conv.get('title', 'Untitled')})")
                print(f"     → first_message_at: {first_message['created_at']}")
                print(f"     → last_message_at: {last_message['created_at']}")
                migrated_count += 1
            else:
                print(f"  ⚠️  No change: {conv['_id']}")

        except Exception as e:
            print(f"  ❌ Error migrating {conv['_id']}: {e}")
            error_count += 1

    print("")
    print(f"✅ Migration complete!")
    print(f"   📝 Migrated: {migrated_count}/{len(with_messages)}")
    print(f"   🗑️  Deleted: {deleted_count}/{len(empty) + (len(with_messages) - migrated_count)}")
    if error_count > 0:
        print(f"   ❌ Errors: {error_count}")
    print("")

    # Verify results
    remaining = await db['chat_sessions'].count_documents({
        '$or': [
            {'first_message_at': {'$exists': False}},
            {'first_message_at': None}
        ]
    })

    if remaining == 0:
        print("🎉 All conversations now have timestamps!")
    else:
        print(f"⚠️  {remaining} conversation(s) still need migration")

    client.close()


def main():
    """Main entry point"""
    dry_run = '--dry-run' in sys.argv

    print("=" * 70)
    print("  🔧 Conversation Timestamps Migration")
    print("  Progressive Commitment Pattern")
    print("=" * 70)
    print("")

    if dry_run:
        print("🔒 Running in DRY RUN mode - no changes will be made")
        print("")

    try:
        asyncio.run(migrate_timestamps(dry_run=dry_run))
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
