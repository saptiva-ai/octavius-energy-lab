"""
Research document models
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from beanie import Document, Indexed
from pydantic import Field


class SourceType(str, Enum):
    """Source type enumeration"""

    WEB = "web"
    ACADEMIC = "academic"
    NEWS = "news"
    SOCIAL = "social"
    OTHER = "other"


class SupportLevel(str, Enum):
    """Evidence support level enumeration"""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class ResearchSource(Document):
    """Research source document model"""

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    task_id: Indexed(str) = Field(..., description="Associated task ID")
    url: str = Field(..., description="Source URL")
    title: str = Field(..., description="Source title")
    excerpt: str = Field(..., description="Source excerpt")
    content: Optional[str] = Field(None, description="Full content if available")

    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score")
    credibility_score: float = Field(
        ..., ge=0.0, le=1.0, description="Credibility score"
    )

    publication_date: Optional[datetime] = Field(None, description="Publication date")
    author: Optional[str] = Field(None, description="Author")
    domain: str = Field(..., description="Source domain")
    source_type: SourceType = Field(..., description="Source type")

    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    class Settings:
        name = "research_sources"
        indexes = [
            "task_id",
            "url",
            "domain",
            "source_type",
            "relevance_score",
            "credibility_score",
            "created_at",
        ]

    def __str__(self) -> str:
        return f"ResearchSource(id={self.id}, url={self.url}, relevance={self.relevance_score})"


class Evidence(Document):
    """Evidence document model"""

    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")
    task_id: Indexed(str) = Field(..., description="Associated task ID")
    claim: str = Field(..., description="Evidence claim")
    support_level: SupportLevel = Field(..., description="Support level")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")

    source_ids: List[str] = Field(
        default_factory=list, description="Associated source IDs"
    )
    quotes: List[str] = Field(default_factory=list, description="Supporting quotes")

    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update timestamp"
    )

    class Settings:
        name = "evidence"
        indexes = [
            "task_id",
            "support_level",
            "confidence",
            "created_at",
        ]

    def __str__(self) -> str:
        return f"Evidence(id={self.id}, claim={self.claim[:50]}..., support={self.support_level})"
