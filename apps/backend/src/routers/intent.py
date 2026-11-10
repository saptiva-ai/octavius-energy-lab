"""HTTP endpoints for intent classification."""

from fastapi import APIRouter, Depends, HTTPException, status

from ..schemas.intent import IntentRequest, IntentResponse
from ..services.intent_service import IntentClassifier

router = APIRouter()


def get_intent_classifier() -> IntentClassifier:
    return IntentClassifier()


@router.post("/intent", response_model=IntentResponse, tags=["intent"])
async def classify_intent_endpoint(
    payload: IntentRequest,
    classifier: IntentClassifier = Depends(get_intent_classifier),
) -> IntentResponse:
    """Return the predicted intent for the provided text."""

    try:
        prediction = await classifier.classify(payload.text)
        return IntentResponse(
            intent=prediction.intent,
            confidence=prediction.confidence,
            reasons=prediction.reasons,
            model=prediction.model,
            fallback_used=False,
            raw_intent=None,
        )
    except Exception as error:  # pragma: no cover - defensive safeguard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to classify intent",
        ) from error
