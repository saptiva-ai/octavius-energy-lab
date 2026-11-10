"""Pydantic models for intent classification API."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class IntentLabel(str, Enum):
    """Supported intent labels returned by the classifier."""

    GREETING = "Greeting"
    CHIT_CHAT = "ChitChat"
    COMMAND = "Command"
    RESEARCHABLE = "Researchable"
    AMBIGUOUS = "Ambiguous"
    MULTI_TOPIC = "MultiTopic"


class IntentRequest(BaseModel):
    """Request body for the intent classification endpoint."""

    text: str = Field(
        ...,
        min_length=1,
        description="Utterance to classify",
        json_schema_extra={"strip_whitespace": True},
    )


class IntentPrediction(BaseModel):
    """Prediction payload describing the detected intent."""

    intent: IntentLabel = Field(..., description="Predicted intent label")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Classifier confidence score"
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Human readable hints that justify the prediction",
    )
    model: str = Field(
        "heuristic",
        description="Identifier of the classifier that produced the prediction",
    )


class IntentResponse(BaseModel):
    """API response for intent classification."""

    intent: IntentLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)
    model: str = Field("heuristic", description="Classifier identifier")
    fallback_used: bool = Field(
        False, description="Whether the heavier fallback classifier was executed"
    )
    raw_intent: Optional[str] = Field(
        None, description="Raw value returned by fallback classifier, if any"
    )
