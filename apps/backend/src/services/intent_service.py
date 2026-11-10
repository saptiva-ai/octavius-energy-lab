"""Intent classification service used by the API layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

try:  # pragma: no cover - optional dependency during tests
    import structlog

    logger = structlog.get_logger(__name__)
except ModuleNotFoundError:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

# Import telemetry for advanced monitoring
try:
    from ..core.telemetry import telemetry, track_endpoint
except ImportError:
    # Fallback for environments without telemetry
    def track_endpoint(name=None):
        def decorator(func):
            return func

        return decorator

    class MockTelemetry:
        def track_intent_classification(self, *args, **kwargs):
            pass

    telemetry = MockTelemetry()


class IntentLabel(str, Enum):
    GREETING = "Greeting"
    CHIT_CHAT = "ChitChat"
    COMMAND = "Command"
    RESEARCHABLE = "Researchable"
    AMBIGUOUS = "Ambiguous"
    MULTI_TOPIC = "MultiTopic"


@dataclass
class IntentPrediction:
    intent: IntentLabel
    confidence: float
    reasons: List[str]
    model: str = "heuristic"


GREETING_PATTERN = re.compile(
    r"^(hola|hey|buen[oa]s|qué tal|buenas tardes|buenos días)(?!\w)", re.IGNORECASE
)
QUESTION_PATTERN = re.compile(
    r"(\?|\b(qué|como|cómo|por qué|por que|cuando|cuándo|donde|dónde|cuál|cual)\b)",
    re.IGNORECASE,
)
COMMAND_PATTERN = re.compile(
    r"\b(configura|establece|crea|actualiza|ejecuta|borra|elimina|lanza|genera)\b",
    re.IGNORECASE,
)
YEAR_PATTERN = re.compile(r"\b20\d{2}\b")
REGION_PATTERN = re.compile(
    r"\b(latam|méxico|mx|europa|ee\.?uu\.?|usa|apac|emea|colombia|perú|chile|argentina)\b",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)
RESEARCH_KEYWORDS = re.compile(
    r"\b(impacto|comparativa|tendencia|riesgo|mercado|benchmark|pronóstico|forecast|análisis)\b",
    re.IGNORECASE,
)


@dataclass
class HeuristicSignal:
    """Single heuristic signal used to build the prediction."""

    label: IntentLabel
    score: float
    reason: str


class IntentClassifier:
    """Simple intent classifier with heuristic core and fallback hook."""

    MIN_CONFIDENCE = 0.35

    def __init__(self) -> None:
        if hasattr(logger, "bind"):
            self.logger = logger.bind(service="intent_classifier")
        else:  # pragma: no cover - fallback for plain logging.Logger
            self.logger = logger

    @track_endpoint("intent_classification")
    async def classify(self, text: str) -> IntentPrediction:
        """Classify the given text using heuristics; placeholder for heavier fallback."""

        heuristics = self._run_heuristics(text)
        if heuristics:
            # Pick the best scoring label. If multiple share score, prefer RESEARCHABLE > AMBIGUOUS > others.
            heuristics.sort(
                key=lambda signal: (signal.score, self._label_priority(signal.label)),
                reverse=True,
            )
            best = heuristics[0]
            confidence = max(min(best.score, 1.0), self.MIN_CONFIDENCE)
            reasons = [
                signal.reason for signal in heuristics if signal.label == best.label
            ][:3]

            # Track intent classification metrics
            result = IntentPrediction(
                intent=best.label, confidence=confidence, reasons=reasons
            )
            telemetry.track_intent_classification(
                intent_type=result.intent.value,
                confidence=result.confidence,
                method="heuristic",
            )

            if hasattr(self.logger, "info"):
                self.logger.info(
                    "Intent classification completed",
                    intent=result.intent.value,
                    confidence=result.confidence,
                    method="heuristic",
                    text_length=len(text),
                    heuristic_signals=len(heuristics),
                )

            return result

        # Fallback to ambiguous if no heuristic triggered. Could plug an LLM here later.
        result = IntentPrediction(
            intent=IntentLabel.AMBIGUOUS,
            confidence=self.MIN_CONFIDENCE,
            reasons=["No heuristic match"],
        )

        # Track fallback case
        telemetry.track_intent_classification(
            intent_type=result.intent.value,
            confidence=result.confidence,
            method="fallback",
        )

        if hasattr(self.logger, "debug"):
            self.logger.debug(
                "No heuristics matched, defaulting to Ambiguous",
                text=text,
                text_length=len(text),
                intent=result.intent.value,
                confidence=result.confidence,
            )

        return result

    def _run_heuristics(self, text: str) -> List[HeuristicSignal]:
        text_stripped = text.strip()
        lowered = text_stripped.lower()
        signals: List[HeuristicSignal] = []

        if not text_stripped:
            return [
                HeuristicSignal(IntentLabel.GREETING, 0.6, "Mensaje vacío o whitespace")
            ]  # guard

        if GREETING_PATTERN.search(lowered):
            signals.append(
                HeuristicSignal(IntentLabel.GREETING, 0.85, "Coincide con saludo")
            )

        if COMMAND_PATTERN.search(lowered):
            signals.append(
                HeuristicSignal(IntentLabel.COMMAND, 0.75, "Contiene verbo imperativo")
            )

        if QUESTION_PATTERN.search(text_stripped):
            signals.append(
                HeuristicSignal(IntentLabel.RESEARCHABLE, 0.8, "Pregunta detectada")
            )

        constraint_score, constraint_reasons = self._constraint_score(text_stripped)
        if constraint_score >= 2:
            signals.append(
                HeuristicSignal(
                    IntentLabel.RESEARCHABLE,
                    0.9,
                    f"Coincidencias de contexto: {', '.join(constraint_reasons)}",
                )
            )
        elif constraint_score == 1:
            signals.append(
                HeuristicSignal(
                    IntentLabel.AMBIGUOUS,
                    0.6,
                    f"Sólo un indicio de contexto: {', '.join(constraint_reasons)}",
                )
            )

        if self._looks_multi_topic(text_stripped):
            signals.append(
                HeuristicSignal(
                    IntentLabel.MULTI_TOPIC, 0.55, "Múltiples temas detectados"
                )
            )

        if not signals and len(text_stripped.split()) <= 4:
            signals.append(
                HeuristicSignal(
                    IntentLabel.CHIT_CHAT, 0.45, "Mensaje muy corto sin mayor contexto"
                )
            )

        return signals

    def _constraint_score(self, text: str) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []

        for pattern, label in [
            (YEAR_PATTERN, "años"),
            (REGION_PATTERN, "regiones"),
            (URL_PATTERN, "URL"),
            (RESEARCH_KEYWORDS, "palabras clave de investigación"),
        ]:
            if pattern.search(text):
                score += 1
                reasons.append(label)

        return score, reasons

    def _looks_multi_topic(self, text: str) -> bool:
        separators = [" y ", " & ", " vs ", ","]
        match_count = sum(1 for sep in separators if sep in text.lower())
        question_marks = text.count("?")
        return match_count >= 2 or question_marks >= 2

    @staticmethod
    def _label_priority(label: IntentLabel) -> int:
        priority_order = [
            IntentLabel.RESEARCHABLE,
            IntentLabel.AMBIGUOUS,
            IntentLabel.MULTI_TOPIC,
            IntentLabel.COMMAND,
            IntentLabel.GREETING,
            IntentLabel.CHIT_CHAT,
        ]
        try:
            return len(priority_order) - priority_order.index(label)
        except ValueError:
            return 0


@track_endpoint("intent_classification_convenience")
async def classify_intent(text: str) -> IntentPrediction:
    """Convenience function for one-off intent classification."""

    classifier = IntentClassifier()
    result = await classifier.classify(text)

    # Additional telemetry for convenience function usage
    if hasattr(logger, "info"):
        logger.info(
            "Convenience intent classification completed",
            intent=result.intent.value,
            confidence=result.confidence,
            text_length=len(text),
        )

    return result
