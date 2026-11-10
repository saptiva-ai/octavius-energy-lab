#!/usr/bin/env python3
"""
Create Demo User Script

Creates a demo user for testing purposes.
Credentials: demo@example.com / Demo1234
"""

import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.hash import argon2
from uuid import uuid4
from datetime import datetime
import os

async def create_demo_user():
    # Get MongoDB connection from environment
    # Inside container, use MONGODB_URL; locally use MONGODB_URI
    mongo_uri = os.getenv("MONGODB_URL") or os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
    db_name = os.getenv("MONGODB_DATABASE") or os.getenv("MONGODB_DB_NAME", "octavios")

    try:
        client = AsyncIOMotorClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # Verify connection
        await client.admin.command('ping')
        db = client[db_name]
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}", file=sys.stderr)
        print(f"   Connection string: {mongo_uri}", file=sys.stderr)
        sys.exit(1)

    # Demo user credentials
    email = "demo@example.com"
    username = "demo"
    password = "Demo1234"
    password_hash = argon2.hash(password)

    try:
        # Check if user already exists
        existing_user = await db.users.find_one({"email": email})

        if existing_user:
            print(f"✅ Demo user already exists: {email}")
            print(f"   Username: {username}")
            print(f"   Password: {password}")
            # Update password in case it changed
            await db.users.update_one(
                {"email": email},
                {"$set": {"password_hash": password_hash, "updated_at": datetime.utcnow()}}
            )
            print(f"   ✅ Password updated")
            return

        # Create demo user with correct Beanie schema
        user_id = str(uuid4())
        now = datetime.utcnow()
        user_doc = {
            "_id": user_id,
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "last_login": None,
            "preferences": {
                "theme": "auto",
                "language": "en",
                "default_model": "SAPTIVA_CORTEX",
                "chat_settings": {}
            }
        }

        result = await db.users.insert_one(user_doc)

        print(f"✅ Demo user created successfully!")
        print(f"   Email: {email}")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        print(f"   User ID: {result.inserted_id}")
    except Exception as e:
        print(f"❌ Error creating demo user: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(create_demo_user())
