"""
MongoDB document models using Beanie ODM
"""

from typing import List, Type

from beanie import Document as BeanieDocument

from .artifact import Artifact
from .chat import ChatMessage, ChatSession
from .document import Document as DocumentModel
from .feedback import FeedbackRating, MessageFeedback
from .history import HistoryEvent, HistoryEventFactory, HistoryQuery
from .password_reset import PasswordResetToken
from .research import Evidence, ResearchSource
from .review_job import ReviewJob
from .system_settings import SystemSettings
from .task import DeepResearchTask, Task
from .user import User
from .validation_report import ValidationReport


# List of all document models for Beanie initialization
def get_document_models() -> List[Type[BeanieDocument]]:
    """Get all document models for Beanie initialization"""
    return [
        User,
        ChatSession,
        ChatMessage,
        Task,
        DeepResearchTask,
        ResearchSource,
        Evidence,
        SystemSettings,
        HistoryEvent,
        DocumentModel,
        ReviewJob,
        ValidationReport,
        PasswordResetToken,
        Artifact,
        MessageFeedback,
    ]


__all__ = [
    "User",
    "ChatSession",
    "ChatMessage",
    "Task",
    "DeepResearchTask",
    "ResearchSource",
    "Evidence",
    "SystemSettings",
    "HistoryEvent",
    "HistoryEventFactory",
    "HistoryQuery",
    "DocumentModel",
    "Artifact",
    "ReviewJob",
    "ValidationReport",
    "PasswordResetToken",
    "MessageFeedback",
    "FeedbackRating",
    "get_document_models",
]
