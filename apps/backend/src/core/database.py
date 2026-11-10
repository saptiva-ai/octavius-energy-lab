"""
MongoDB database configuration using Motor and Beanie
"""

import os
from typing import Optional

import structlog
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.server_api import ServerApi

from .config import get_settings

logger = structlog.get_logger()


class Database:
    """MongoDB database manager"""

    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def validate_config(cls) -> None:
        """Validate MongoDB configuration before connecting"""
        settings = get_settings()

        # Check if MONGODB_URL is set
        if not settings.mongodb_url:
            logger.error("❌ MONGODB_URL not configured in environment")
            raise ValueError("MONGODB_URL environment variable is required")

        # Check for common misconfiguration: password mismatch
        mongodb_password_env = os.getenv("MONGODB_PASSWORD")
        mongodb_user_env = os.getenv("MONGODB_USER", "copilotos_user")

        if mongodb_password_env:
            logger.info(
                "✓ Environment variables detected",
                mongodb_user=mongodb_user_env,
                mongodb_password_set=bool(mongodb_password_env),
                password_length=(
                    len(mongodb_password_env) if mongodb_password_env else 0
                ),
            )

            # Verify password is in the connection URL
            if mongodb_password_env not in settings.mongodb_url:
                logger.warning(
                    "⚠️  MONGODB_PASSWORD mismatch detected",
                    warning="Environment variable MONGODB_PASSWORD differs from URL password",
                    hint="This may cause authentication failures. Ensure infra/.env matches docker-compose.yml",
                )
        else:
            logger.warning(
                "⚠️  MONGODB_PASSWORD not found in environment",
                hint="Password should be set in infra/.env file",
            )

    @classmethod
    async def connect_to_mongo(cls) -> None:
        """Create database connection"""
        settings = get_settings()

        # Validate configuration before attempting connection
        await cls.validate_config()

        logger.info("Connecting to MongoDB", url=settings.mongodb_url.split("@")[-1])

        cls.client = AsyncIOMotorClient(
            settings.mongodb_url,
            minPoolSize=settings.db_min_pool_size,
            maxPoolSize=settings.db_max_pool_size,
            connectTimeoutMS=settings.db_connect_timeout_ms,
            serverSelectionTimeoutMS=settings.db_server_selection_timeout_ms,
            maxIdleTimeMS=settings.db_max_idle_time_ms,
            server_api=ServerApi("1"),  # Use Stable API version 1
        )

        # Get database name from URL or use default
        db_name = settings.mongodb_url.split("/")[-1].split("?")[0]
        cls.database = cls.client[db_name]

        # Test connection with detailed error reporting
        try:
            await cls.client.admin.command("ping")
            logger.info("Successfully connected to MongoDB", database=db_name)

            # Get authentication status for verification
            try:
                conn_status = await cls.client.admin.command("connectionStatus")
                auth_users = conn_status.get("authInfo", {}).get(
                    "authenticatedUsers", []
                )
                logger.info(
                    "MongoDB authentication verified",
                    authenticated_users=auth_users,
                    database=db_name,
                )
            except Exception:
                # Non-critical, just skip detailed auth info
                pass

        except Exception as e:
            # Parse connection URL to extract details (without exposing password)
            mongodb_url = settings.mongodb_url

            # Extract connection details safely
            try:
                # Remove mongodb:// prefix
                url_without_prefix = mongodb_url.replace("mongodb://", "")

                # Check if URL has authentication
                if "@" in url_without_prefix:
                    credentials_part, host_part = url_without_prefix.split("@", 1)
                    username = credentials_part.split(":")[0]
                    host_and_db = host_part.split("?")[0]  # Remove query params
                else:
                    username = "not_specified"
                    host_and_db = url_without_prefix.split("?")[0]

                # Extract host and database
                if "/" in host_and_db:
                    host, db_from_url = host_and_db.split("/", 1)
                else:
                    host = host_and_db
                    db_from_url = "not_specified"

                # Extract authSource from query params
                auth_source = (
                    "admin" if "authSource=admin" in mongodb_url else "default"
                )

            except Exception:
                # If parsing fails, use safe defaults
                username = "parse_error"
                host = "parse_error"
                db_from_url = "parse_error"
                auth_source = "unknown"

            # Log comprehensive error information
            logger.error(
                "❌ MongoDB Connection Failed - AUTHENTICATION ERROR",
                error_type=type(e).__name__,
                error_message=str(e),
                error_code=getattr(e, "code", None),
                connection_details={
                    "username": username,
                    "host": host,
                    "database": db_from_url,
                    "auth_source": auth_source,
                    "using_srv": "mongodb+srv://" in mongodb_url,
                },
                troubleshooting_hints=[
                    "1. Check that MONGODB_PASSWORD in infra/.env matches docker-compose initialization",
                    "2. Verify MongoDB container initialized with same password",
                    "3. If password changed, recreate volumes: docker compose down -v",
                    "4. Check environment variables are loaded: docker compose config",
                    "5. Test direct connection: docker exec copilotos-mongodb mongosh -u <user> -p <pass>",
                ],
            )

            # Add specific hints based on error type
            if "Authentication failed" in str(e):
                logger.error(
                    "🔑 Authentication Failed - Password Mismatch Detected",
                    likely_cause="MONGODB_PASSWORD environment variable differs from MongoDB initialization password",
                    solution="Update infra/.env to match password in docker-compose.yml, then run: docker compose down -v && docker compose up -d",
                )
            elif "Could not connect" in str(e) or "connection" in str(e).lower():
                logger.error(
                    "🔌 Connection Failed - MongoDB Not Reachable",
                    likely_cause="MongoDB service not running or network issue",
                    solution="Check MongoDB status: docker compose ps mongodb",
                )

            raise

        # Initialize Beanie with document models
        from ..models import get_document_models

        await init_beanie(database=cls.database, document_models=get_document_models())
        logger.info("Beanie ODM initialized with document models")

    @classmethod
    async def close_mongo_connection(cls) -> None:
        """Close database connection"""
        if cls.client:
            logger.info("Closing MongoDB connection")
            cls.client.close()
            cls.client = None
            cls.database = None

    @classmethod
    async def ping(cls) -> bool:
        """Check database connection"""
        if not cls.client:
            return False
        try:
            await cls.client.admin.command("ping")
            return True
        except Exception as e:
            logger.warning("MongoDB ping failed", error=str(e))
            return False

    @classmethod
    def get_client(cls) -> Optional[AsyncIOMotorClient]:
        """Get MongoDB client instance"""
        return cls.client

    @classmethod
    def get_database(cls) -> Optional[AsyncIOMotorDatabase]:
        """Get database instance"""
        return cls.database


# Dependency for FastAPI
async def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency to get database instance"""
    if Database.database is None:
        raise RuntimeError("Database not initialized")
    return Database.database
