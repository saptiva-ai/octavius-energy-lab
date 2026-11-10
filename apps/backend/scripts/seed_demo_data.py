"""Seed demo data for Copilot OS API.

Creates a default demo user that can be used for local testing.
"""

import asyncio
import sys
import structlog
from pathlib import Path

# Add src to path before importing local modules
CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# Local imports after path setup
from core.database import Database  # noqa: E402
from core.exceptions import ConflictError  # noqa: E402
from schemas.user import UserCreate  # noqa: E402
from services.auth_service import register_user  # noqa: E402

logger = structlog.get_logger(__name__)

DEMO_USER = UserCreate(
    username="demo_admin",
    email="demo@saptiva.ai",
    password="ChangeMe123!",
)


async def seed_demo_user() -> None:
    await Database.connect_to_mongo()
    try:
        auth_response = await register_user(DEMO_USER)
        logger.info(
            "Demo user created",
            username=auth_response.user.username,
            email=auth_response.user.email,
        )
        print("✅ Demo user created successfully")
        print(f"   Username: {auth_response.user.username}")
        print(f"   Email:    {auth_response.user.email}")
        print("   Password: ChangeMe123!")
    except ConflictError:
        logger.info("Demo user already exists", username=DEMO_USER.username)
        print("ℹ️  Demo user already exists. Skipping creation.")
    finally:
        await Database.close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(seed_demo_user())
