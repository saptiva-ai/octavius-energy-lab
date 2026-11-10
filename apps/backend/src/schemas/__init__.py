"""
Pydantic schemas for Copilot OS API
"""

from .auth import AuthRequest, AuthResponse, TokenRefresh
from .chat import ChatMessage, ChatRequest, ChatResponse, ChatSession
from .common import ApiError, ApiResponse, PaginatedResponse
from .health import HealthStatus, ServiceStatus
from .intent import IntentLabel, IntentPrediction, IntentRequest, IntentResponse
from .research import (
    DeepResearchParams,
    DeepResearchRequest,
    DeepResearchResponse,
    DeepResearchResult,
    Evidence,
    ResearchMetrics,
    ResearchSource,
    TaskStatus,
)
from .settings import (
    SaptivaKeyDeleteResponse,
    SaptivaKeyStatus,
    SaptivaKeyUpdateRequest,
    SaptivaKeyUpdateResponse,
)
from .user import User, UserPreferences, UserUpdate

__all__ = [
    # Auth
    "AuthRequest",
    "AuthResponse",
    "TokenRefresh",
    # Chat
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ChatSession",
    # Health
    "HealthStatus",
    "ServiceStatus",
    # Intent
    "IntentRequest",
    "IntentResponse",
    "IntentLabel",
    "IntentPrediction",
    # Research
    "DeepResearchRequest",
    "DeepResearchResponse",
    "DeepResearchParams",
    "DeepResearchResult",
    "TaskStatus",
    "ResearchSource",
    "Evidence",
    "ResearchMetrics",
    # Common
    "ApiResponse",
    "PaginatedResponse",
    "ApiError",
    # User
    "User",
    "UserPreferences",
    "UserUpdate",
    # Settings
    "SaptivaKeyStatus",
    "SaptivaKeyUpdateRequest",
    "SaptivaKeyUpdateResponse",
    "SaptivaKeyDeleteResponse",
]
