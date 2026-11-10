"""
Artifact Service for managing user-generated artifacts.

Generic, domain-agnostic CRUD operations for artifacts including:
- Charts (visualizations)
- Markdown documents
- Code snippets
- Graph diagrams
"""

from typing import Any, Dict, List, Optional

from structlog import get_logger

from src.models.artifact import Artifact, ArtifactType

logger = get_logger(__name__)


class ArtifactService:
    """Service for managing artifacts across the application."""

    async def create_chart_artifact(
        self,
        user_id: str,
        session_id: str,
        chart_data: Dict[str, Any],
        title: Optional[str] = None,
    ) -> Artifact:
        """
        Create a generic chart artifact and persist it.

        Args:
            user_id: Owner user ID
            session_id: Associated chat session ID
            chart_data: Chart payload (plotly_config, metadata, etc.)
            title: Optional custom title

        Returns:
            Persisted Artifact instance
        """
        artifact = Artifact.create_chart(
            user_id=user_id,
            session_id=session_id,
            chart_data=chart_data,
            title=title,
        )

        await artifact.insert()

        logger.info(
            "chart_artifact_created",
            artifact_id=artifact.id,
            session_id=session_id,
            user_id=user_id,
        )

        return artifact

    async def get_charts_by_session(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[Artifact]:
        """
        Get all chart artifacts for a chat session, ordered by most recent.

        Args:
            session_id: Chat session ID
            limit: Maximum number of charts to return (default 10)

        Returns:
            List of Artifact instances, newest first
        """
        charts = (
            await Artifact.find(
                Artifact.chat_session_id == session_id,
                Artifact.type == ArtifactType.CHART,
            )
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )

        logger.debug(
            "fetched_charts_by_session",
            session_id=session_id,
            count=len(charts),
            limit=limit,
        )

        return charts

    async def get_latest_chart_in_session(
        self,
        session_id: str,
    ) -> Optional[Artifact]:
        """
        Get the most recent chart artifact in a session.

        Args:
            session_id: Chat session ID

        Returns:
            Latest Artifact or None if no charts exist
        """
        charts = await self.get_charts_by_session(session_id, limit=1)
        return charts[0] if charts else None

    async def get_artifact_by_id(
        self,
        artifact_id: str,
    ) -> Optional[Artifact]:
        """
        Get a single artifact by ID.

        Args:
            artifact_id: Unique artifact ID

        Returns:
            Artifact instance or None if not found
        """
        artifact = await Artifact.get(artifact_id)

        if artifact:
            logger.debug(
                "fetched_artifact_by_id",
                artifact_id=artifact_id,
                type=artifact.type,
            )
        else:
            logger.warning(
                "artifact_not_found",
                artifact_id=artifact_id,
            )

        return artifact

    async def get_artifacts_by_user(
        self,
        user_id: str,
        artifact_type: Optional[ArtifactType] = None,
        limit: int = 20,
    ) -> List[Artifact]:
        """
        Get all artifacts for a user, optionally filtered by type.

        Args:
            user_id: User ID
            artifact_type: Optional type filter (CHART, MARKDOWN, etc.)
            limit: Maximum number of artifacts to return

        Returns:
            List of Artifact instances, newest first
        """
        query = {"user_id": user_id}
        if artifact_type:
            query["type"] = artifact_type

        artifacts = (
            await Artifact.find(query).sort("-created_at").limit(limit).to_list()
        )

        logger.debug(
            "fetched_artifacts_by_user",
            user_id=user_id,
            artifact_type=artifact_type,
            count=len(artifacts),
        )

        return artifacts

    async def delete_artifact(
        self,
        artifact_id: str,
        user_id: str,
    ) -> bool:
        """
        Delete an artifact (with ownership check).

        Args:
            artifact_id: Artifact ID to delete
            user_id: User ID (for ownership verification)

        Returns:
            True if deleted, False if not found or unauthorized
        """
        artifact = await Artifact.get(artifact_id)

        if not artifact:
            logger.warning("artifact_not_found_for_delete", artifact_id=artifact_id)
            return False

        if artifact.user_id != user_id:
            logger.warning(
                "unauthorized_artifact_delete",
                artifact_id=artifact_id,
                user_id=user_id,
                owner_id=artifact.user_id,
            )
            return False

        await artifact.delete()

        logger.info(
            "artifact_deleted",
            artifact_id=artifact_id,
            user_id=user_id,
            type=artifact.type,
        )

        return True

    def to_response(self, artifact: Artifact) -> Dict[str, Any]:
        """
        Convert Artifact model to a lightweight response dict.

        Args:
            artifact: Artifact instance

        Returns:
            Dict with core artifact fields
        """
        return {
            "artifact_id": artifact.id,
            "title": artifact.title,
            "type": artifact.type.value,
            "created_at": artifact.created_at.isoformat(),
            "session_id": artifact.chat_session_id or "",
        }


# Singleton instance for dependency injection
_artifact_service_instance: Optional[ArtifactService] = None


def get_artifact_service() -> ArtifactService:
    """
    Get singleton ArtifactService instance.

    Returns:
        ArtifactService singleton
    """
    global _artifact_service_instance
    if _artifact_service_instance is None:
        _artifact_service_instance = ArtifactService()
    return _artifact_service_instance
